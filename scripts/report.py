"""Render the assignment's report tables using real run evidence only."""
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
PENDING = 'не измерено'


def esc(value):
    return str(value).replace('|', '\\|').replace('\n', ' ')


def table(headers, rows):
    return '\n'.join([
        '| ' + ' | '.join(headers) + ' |',
        '| ' + ' | '.join('---' for _ in headers) + ' |',
        *['| ' + ' | '.join(esc(c) for c in row) + ' |' for row in rows],
    ])


def make_report(state=None, run_dir=None):
    s = state or {}
    done = s.get('status') == 'completed'
    scale = s.get('scale', 'sf1')
    author = s.get('author', 'УКАЗАТЬ ФИО КАК В VK EDUCATION через --author')
    run_id = s.get('run_id')
    evidence = f'results/{run_id}' if run_id else 'results/<идентификатор прогона>'
    inventory = {r['table']: r for r in s.get('inventory', [])}
    benchmarks = s.get('benchmark', [])
    evolution = s.get('evolution', {})
    bi = s.get('bi', {})

    def metric(name, field):
        value = inventory.get(name, {}).get(field)
        return f'{value:.6f}' if isinstance(value, float) else value if value is not None else PENDING

    lines = [
        '# Отчёт по практической работе №1\n\n'
        '**Развертывание локального Lakehouse, ELT и бенчмарк форматов и сжатия. Вариант 1 — Q3 Shipping Priority.**\n',
        (f'Статус: **фактический прогон завершён**, `{run_id}`. Числа ниже получены этим прогоном.\n' if done else
         f'Статус: **{esc(s.get("status", "проект подготовлен; фактический прогон ещё не выполнен"))}**. '
         'Неизмеренные значения обозначены явно. Этот файл нужно дополнить результатами команды из README перед сдачей.\n'),
    ]
    if s.get('error'):
        lines.append('Причина остановки: ' + esc(s['error']) + '\n')
    if s.get('execution_environment'):
        lines.append('Среда фактического выполнения: **' + esc(s['execution_environment']) + '**.\n')
    if s.get('workflow_run_url'):
        lines.append('Подтверждение запуска: [GitHub Actions](' + s['workflow_run_url'] + ').\n')
    lines += [
        '## 1. Вариант и масштаб\n',
        table(['Поле', 'Значение'], [
            ['ФИО как в VK Education', author], ['Вариант', '1 — Q3 Shipping Priority'],
            ['Масштаб', scale],
            ['Почему такой масштаб', f'{scale} задаётся одним параметром для всех запросов. '
             + ('sf1 даёт 150 000 клиентов, 1 500 000 заказов и 6 001 215 строк lineitem; это паспортные количества TPC-H, а не замеры данного запуска. '
                if scale == 'sf1' else 'Фактические количества записаны в инвентаризации. ')
             + 'Объём позволяет сравнить чтение и запись на локальном стенде. Для очень коротких запросов влияние накладных расходов нужно учитывать; масштаб можно увеличить при достаточных ресурсах.'],
        ]),
        '\n## 2. Сервисы и обоснование выбора\n',
        ('Запущенные контейнеры подтверждены в `' + evidence + '/docker-ps.txt`. '
         'Одноразовые minio-init и lakekeeper-migrate после успеха имеют состояние Exited (0).\n' if done else
         'Ниже описана конфигурация проекта. Поднятые сервисы необходимо подтвердить фактическим `docker compose ps -a`; автоматически это сохраняется при запуске.\n'),
        table(['Сервис', 'Роль', 'Почему выбран'], [
            ['MinIO', 'S3-совместимое объектное хранилище файлов данных и Iceberg-метаданных',
             'Позволяет локально проверить S3 API без облачного аккаунта. Закреплена доступная архивная сборка bitnamilegacy/minio:2025.4.22 с клиентом mc. Обычная папка не проверяла бы S3-доступ; HDFS потребовал бы больше сервисов.'],
            ['PostgreSQL', 'Служебная БД Lakekeeper',
             'Хранит состояние каталога в постоянном томе и поддерживает транзакции. Это не БД с фактами TPC-H: строки таблиц лежат в MinIO.'],
            ['Lakekeeper', 'Iceberg REST Catalog',
             'Открытая реализация стандартного REST API позволяет не привязывать таблицы к одному движку. Для этой работы не нужен отдельный Hive Metastore.'],
            ['Trino', 'Генерация TPC-H, SQL ELT, запись и чтение Iceberg',
             'Один движок даёт и источник tpch, и Iceberg-коннектор. Не требуется отдельный генератор dbgen или Spark-кластер для пакетного преобразования SQL.'],
            ['Apache Superset', 'BI-клиент к Bronze и Gold через Trino',
             'Имеет SQL Lab и таблицы на дашборде. Для SQL-задачи он проще дополнительного вычислительного движка. Файлы не копируются в отдельное аналитическое хранилище.'],
            ['minio-init, lakekeeper-migrate', 'Одноразовая подготовка бакета и миграций БД',
             'Порядок зависимостей исключает старт каталога до появления бакета и схемы PostgreSQL.'],
        ]),
        '\n### Скрипты развертывания\n\n'
        'Полная конфигурация — [`docker-compose.yml`](docker-compose.yml), настройки — `config/`. '
        'Все образы закреплены тегами; фактические идентификаторы образов сохраняются в `state.json`.\n\n'
        '```bash\n'
        '# Создать БД, бакет и каталог, запустить SQL-движок\n'
        'docker compose up -d --wait --wait-timeout 300 postgres minio lakekeeper trino\n'
        '# Полный запуск также выполнит bootstrap Lakekeeper, создаст warehouse lab, ELT и бенчмарк\n'
        f'python3 scripts/lakehouse.py run --author "ФИО как в VK Education" --scale {scale}\n'
        '# BI поднимается автоматически после бенчмарка\n'
        'docker compose --profile bi ps -a\n'
        '```\n\n'
        'Пароли в compose — локальные учебные значения; HTTP-порты опубликованы только на 127.0.0.1. '
        'Для простоты локального стенда Trino использует явные S3-ключи, STS выключен. '
        'Superset хранит только свою конфигурацию в SQLite в отдельном Docker-томе.\n',
        '## 3. Разбор Q3\n',
        table(['Таблица TPC-H', 'Нужные колонки', 'Использование'], [
            ['customer', 'custkey, mktsegment', 'custkey — джойн с orders; mktsegment — фильтр BUILDING.'],
            ['orders', 'orderkey, custkey, orderdate, shippriority', 'custkey и orderkey — джойны; orderdate < 1995-03-15; orderdate и shippriority — группировка и вывод.'],
            ['lineitem', 'orderkey, extendedprice, discount, shipdate; дополнительно linenumber', 'orderkey — джойн и группировка; extendedprice × (1 − discount) — выручка; shipdate > 1995-03-15. linenumber вместе с orderkey нужен для проверки уникальности строки факта.'],
        ]),
        '\nИмена колонок используются без `c_`, `o_`, `l_`. Условия дат строгие: сама дата 15 марта исключена. '
        'Выручка считается по подходящим строкам заказа, а не по всем строкам отобранного заказа. '
        'В сортировку добавлены orderdate и orderkey после revenue для стабильности при равной выручке.\n',
        '## 4. Медальон\n\n'
        'Iceberg — формат таблицы с метаданными и снапшотами; PARQUET/ORC — форматы файлов данных. '
        'Размер в отчёте — сумма `file_size_in_bytes` текущих data-файлов из `"table$files" WHERE content = 0`, '
        'делённая на 1 000 000, то есть десятичные МБ. Метаданные, старые снапшоты и демонстрационные/benchmark-таблицы '
        'в размер основного Bronze не включаются. `SHOW STATS` не используется как размер файлов.\n',
        '### Bronze\n',
        table(['Таблица', 'Оставленные колонки', 'Строк', 'Вес МБ', 'Формат', 'Сжатие', 'Партиции', 'Обоснование'], [
            ['bronze.customer', 'custkey, mktsegment', metric('bronze.customer', 'rows'), metric('bronze.customer', 'MB'), 'PARQUET', 'ZSTD', 'нет', 'Сырой проекционный снимок без изменения значений. Колончатый формат читает только нужные поля; ZSTD выбран как исходная конфигурация до результатов теста. Небольшую таблицу не дроблю на партиции.'],
            ['bronze.orders', 'orderkey, custkey, orderdate, shippriority', metric('bronze.orders', 'rows'), metric('bronze.orders', 'MB'), 'PARQUET', 'ZSTD', 'нет', 'Сохраняю ключи, дату и приоритет в исходных типах. На локальном sf1 партиции добавили бы файлы; отдельного эксперимента по партиционированию в работе нет.'],
            ['bronze.lineitem', 'orderkey, linenumber, extendedprice, discount, shipdate', metric('bronze.lineitem', 'rows'), metric('bronze.lineitem', 'MB'), 'PARQUET', 'ZSTD', 'нет', 'Оставляю поля Q3 и ключ строки. Для честного сравнения кодеков у всех копий одинаковый набор колонок и отсутствие партиций.'],
        ]),
        '\n### Silver\n',
        table(['Таблица', 'Колонки', 'Строк', 'Вес МБ', 'Формат', 'Сжатие', 'Партиции', 'Обоснование'], [
            ['silver.q3_lines', 'orderkey, linenumber, custkey, mktsegment, orderdate, shipdate, shippriority, extendedprice, discount, net_revenue', metric('silver.q3_lines', 'rows'), metric('silver.q3_lines', 'MB'), 'PARQUET', 'ZSTD', 'нет', 'Нормализую segment через upper(trim()), проверяю ключи, NULL, цены и discount ∈ [0,1]. Привожу денежные поля к DECIMAL, обогащаю строку атрибутами клиента/заказа и net_revenue. После фильтров Q3 таблица мала; партиции не обоснованы измерением.'],
            ['silver.rejected_rows', 'source_table, row_id, reason', metric('silver.rejected_rows', 'rows'), metric('silver.rejected_rows', 'MB'), 'PARQUET', 'ZSTD', 'нет', 'Некорректные значения фиксируются отдельно. Для штатного TPC-H ожидается 0 строк, но фактическое число берётся из проверки. Дубликаты и нарушенные внешние ключи приводят к остановке проверки.'],
        ]),
        '\nЦена `DECIMAL(15,2)`, скидка `DECIMAL(4,2)`, выражение '
        '`extendedprice * (DECIMAL \'1.00\' - discount)` сохраняет 4 знака после запятой. '
        'Это устраняет накопление двоичной ошибки при суммировании. В исходном TPC-H цены и скидки уже имеют '
        'соответствующую точность; очистка не должна менять результат на корректном наборе.\n',
        '### Gold\n',
        table(['Таблица', 'Колонки', 'Строк', 'Вес МБ', 'Формат', 'Сжатие', 'Партиции', 'Обоснование'], [
            ['gold.q3_shipping_priority', 'orderkey, revenue, orderdate, shippriority', metric('gold.q3_shipping_priority', 'rows'), metric('gold.q3_shipping_priority', 'MB'), 'PARQUET', 'ZSTD', 'нет', 'Сумма net_revenue по заказу и top 10. Единый формат упрощает сопровождение; для 10 строк накладные расходы файла важнее возможной экономии от кодека. Партиционирование дало бы лишние мелкие файлы.'],
        ]),
        '\nGold — физическая таблица CTAS. Порядок хранения строк не гарантируется: BI и контрольный SELECT '
        'явно повторяют ORDER BY. Подробные SQL находятся в `sql/10_…`–`sql/40_q3.sql`.\n',
        '## 5. Тесты производительности\n\n'
        'Измеряется Q3 непосредственно над тремя таблицами каждого benchmark-Bronze, а не чтение готового Gold. '
        'Сравниваются PARQUET/GZIP, PARQUET/ZSTD и ORC/ZSTD. Это разделяет сравнение кодеков внутри Parquet '
        'и форматов при одинаковом ZSTD. Утверждений обо всех комбинациях кодеков и форматов тест не делает.\n\n'
        f'Методика: один координатор Trino, последовательные задания, без одновременных BI-запросов; '
        f'прогрев всех вариантов записи; {s.get("write_repeats", 3)} повторных создания каждой тройки таблиц; '
        f'один прогрев Q3 для каждой пары и {s.get("query_repeats", 5)} измерений Q3. '
        'Порядок пар перемешан с seed=42 в каждом раунде. Перед записью таблицы пересоздаются; DROP и проверки '
        'не входят во время CTAS. Для каждой записи сравниваются count и независимый от порядка checksum всех сохранённых полей '
        'с tpch; каждый результат Q3 сверяется с источником.\n\n'
        'Основное время — `elapsedTimeMillis` финального ответа HTTP Trino: полное серверное время, включая '
        'очередь и планирование. Дополнительно сохраняется wall time клиента от отправки SQL до получения всех страниц. '
        'Время записи Bronze — сумма трёх CTAS в раунде; итог — медиана этих сумм. Время записи включает генерацию '
        'tpch, сериализацию, передачу в MinIO и commit каталога, поэтому это ELT-бенчмарк, а не чистое CPU-время кодека.\n\n'
        'Используется прогретый режим. Кэши ОС и MinIO принудительно не очищаются, холодный диск не имитируется. '
        'Файловый кэш Trino дополнительно не включён. Планы и статистика могут зависеть от формата; '
        'вывод относится к этому стенду. Размер и число файлов записываются для каждого раунда отдельно.\n',
    ]
    if benchmarks:
        rows = []
        for r in benchmarks:
            rows.append([r['format'], r['codec'], f"{r['query_elapsed_median_s']:.3f}",
                f"{r['query_elapsed_min_s']:.3f}–{r['query_elapsed_max_s']:.3f}",
                f"{r['write_elapsed_median_s']:.3f}", f"{r['size_MB_median']:.3f}", r['data_files_final']])
    else:
        rows = [[fmt, codec, PENDING, PENDING, PENDING, PENDING, PENDING]
                for fmt, codec in [('PARQUET', 'GZIP'), ('PARQUET', 'ZSTD'), ('ORC', 'ZSTD')]]
    lines.append(table(['Формат Bronze', 'Сжатие', 'Q3 медиана с', 'Q3 min–max с', 'Запись медиана с', 'Bronze медиана МБ', 'Файлов в последнем раунде'], rows))
    if benchmarks:
        fastest = min(benchmarks, key=lambda r: r['query_elapsed_median_s'])
        smallest = min(benchmarks, key=lambda r: r['size_MB_median'])
        gzip = next(r for r in benchmarks if r['format']=='PARQUET' and r['codec']=='GZIP')
        zstd = next(r for r in benchmarks if r['format']=='PARQUET' and r['codec']=='ZSTD')
        saving = (1 - zstd['size_MB_median']/gzip['size_MB_median'])*100 if gzip['size_MB_median'] else 0
        ratio = gzip['query_elapsed_median_s']/zstd['query_elapsed_median_s'] if zstd['query_elapsed_median_s'] else 0
        lines.append(f'\nПо медиане быстрее Q3 на **{fastest["format"]}/{fastest["codec"]}**; '
                     f'меньше места занимает **{smallest["format"]}/{smallest["codec"]}**. '
                     f'PARQUET/ZSTD относительно PARQUET/GZIP: изменение размера со знаком экономии **{saving:+.2f}%**, '
                     f'отношение времени GZIP/ZSTD **{ratio:.3f}** (>1 означает меньшую медиану ZSTD). '
                     'Min–max и стандартное отклонение в CSV помогают увидеть разброс. Это описательные измерения; '
                     'при близких значениях нельзя объявлять статистически доказанное преимущество. '
                     'Основной медальон сохраняет заранее выбранный ZSTD; результаты не подменяются этим выбором.\n')
    else:
        lines.append('\nВывод о победителе будет сформирован из измерений. До запуска нельзя утверждать, что GZIP, ZSTD или ORC быстрее именно на этом компьютере.\n')
    lines += [
        f'\nСырые замеры: `{evidence}/write_runs.csv`, `size_runs.csv`, `query_runs.csv`; '
        f'сводка — `benchmark_summary.csv`; query_id, SQL и полные статистики — `queries.jsonl`. '
        'Параметры CPU/RAM Docker и хоста, версия Python и идентификаторы образов — `state.json`.\n',
        '## 6. Осмысление и инструменты\n\n### 6.1. Понять и объяснить\n',
        table(['Вопрос', 'Ответ'], [
            ['Зачем большие данные и lakehouse вместо обычной БД/хранилища?',
             'При росте объёма нужны недорогое хранение истории и независимое масштабирование вычислений. В этом проекте файлы в S3 доступны через открытый формат таблицы, а SQL-движок подключается отдельно. Iceberg добавляет атомарные изменения, схему и снапшоты поверх файлов. Для небольшого OLTP с частыми одиночными изменениями обычная PostgreSQL проще; локальный sf1 служит учебной моделью, а не доказательством необходимости lakehouse для любого бизнеса.'],
            ['Schema evolution на Silver: что произошло?',
             (f'На копии silver.evolution_demo ({evolution["restored_rows"]} строк) выполнены ADD COLUMN quality_note VARCHAR и RENAME COLUMN quality_note TO dq_note. '
              'Для старых строк новое поле NULL. Список путей и размеров data-файлов до и после совпал: изменились метаданные схемы, не файлы данных. '
              f'Подтверждение: {evidence}/evolution_restore.json.' if evolution else
              'Автоматизирован опыт на небольшой копии silver.evolution_demo: ADD COLUMN quality_note VARCHAR, затем RENAME COLUMN quality_note TO dq_note. Проверяется NULL у старых строк и неизменность путей/размеров data-файлов. До запуска это ожидаемое поведение, а не наблюдавшийся результат.')],
            ['Восстановление из снапшота и time travel',
             (f'Сохранён snapshot_id={evolution["snapshot_id"]}, удалены строки только демонстрационной копии. FOR VERSION AS OF прочитал прежнее количество строк, rollback_to_snapshot восстановил {evolution["restored_rows"]} строк; проверена также контрольная сумма. Скрипт с настоящим id: {evidence}/restore.sql.' if evolution else
              'Код сохраняет реальный snapshot_id, удаляет строки только демонстрационной таблицы, читает старый снапшот через FOR VERSION AS OF и выполняет rollback_to_snapshot. Затем сравнивает число строк и checksum. Сам ID и доказательство появятся после запуска.')],
        ]),
        '\nПример механики восстановления (SNAPSHOT_ID нужно заменить значением из `$history`; '
        'готовый `results/<run>/restore.sql` содержит реальный ID):\n\n'
        '```sql\n'
        'SELECT snapshot_id\nFROM iceberg.silver."evolution_demo$history"\nORDER BY made_current_at DESC LIMIT 1;\n'
        '-- После подстановки одного и того же сохранённого ID:\n'
        'SELECT count(*) FROM iceberg.silver.evolution_demo FOR VERSION AS OF SNAPSHOT_ID;\n'
        'ALTER TABLE iceberg.silver.evolution_demo EXECUTE rollback_to_snapshot(SNAPSHOT_ID);\n'
        '```\n\n'
        'Time travel читает историческую версию без смены текущего состояния. Rollback меняет текущий снапшот. '
        'Опыт не проверяет откат схемы и не восстанавливает весь warehouse. Снапшоты не заменяют резервную копию: '
        'если удалить необходимые файлы из MinIO или очистить историю, восстановление этой версии станет невозможно.\n',
        '### 6.2. Инструмент к Lakehouse\n',
        table(['Инструмент', 'Почему выбран'], [['Apache Superset 4.1.2',
            'SQL Lab позволяет показать именно Bronze; дашборд отдельно показывает Bronze preview и Gold top 10. '
            'Используется Trino SQLAlchemy driver, запросы читают существующие Iceberg-таблицы через каталог.']]),
        '\nРазвертывание: `config/superset/Dockerfile`, `start.sh`, `create_admin.py`, `register.py` и сервис '
        '`superset` в compose. URI подключения внутри Docker: `trino://bi@trino:8080/iceberg`.\n\n'
        'Действия в консоли, выполняемые общим скриптом после запуска BI:\n\n'
        '```bash\n'
        'docker compose --profile bi up -d --build --wait --wait-timeout 600 superset\n'
        '# EVIDENCE_RUN_ID содержит идентификатор из results/latest.json\n'
        'docker compose exec -T -e EVIDENCE_RUN_ID=ИДЕНТИФИКАТОР superset python /app/pythonpath/register.py\n'
        '```\n',
        (f'\nФактический доступ из BI-контейнера: **{bi["bronze_lineitem_rows"]}** строк Bronze lineitem; '
         f'10 примеров строк и выполненные SQL сохранены в `{evidence}/bi_proof.json`. '
         'Это консольное подтверждение соединения. Скриншот UI этим кодом не создаётся.\n' if bi else
         '\nФактическое подключение пока не подтверждено. Успешный `register.py` сохранит bi_proof.json с count(*) и 10 строками Bronze из BI-контейнера.\n'),
        '\nДля просмотра в UI: открыть http://localhost:8088, войти `admin` / `admin-local`, '
        'в SQL → SQL Lab выбрать `Lakehouse Trino`, выполнить `sql/50_bi.sql` по одному запросу. '
        'Дашборд: http://localhost:8088/superset/dashboard/q3-lakehouse/. '
        'Для сдачи можно приложить собственный скриншот SQL Lab и дашборда; консольное доказательство уже собирается автоматически.\n',
        '## 7. Выводы\n\n'
        'Медальон разделяет исходный проекционный снимок Bronze, проверенный факт Silver и компактную витрину Gold. '
        'Открытые таблицы Iceberg связывают SQL с файлами в объектном хранилище и позволяют изменять схему без обязательной перезаписи данных. '
        + (f'На данном стенде минимальная медиана Q3 получена для {fastest["format"]}/{fastest["codec"]}, '
           f'а минимальный размер — для {smallest["format"]}/{smallest["codec"]}. ' if benchmarks else
           'Победитель по скорости и размеру определяется только после фактического бенчмарка. ')
        + 'Польза сжатия оценивается вместе с затратами записи, разбросом времени и накладными расходами мелких файлов. '
        'Для локального Q3 простой набор непартиционированных таблиц уменьшает сложность, а необходимость партиционирования при росте масштаба требует отдельного опыта.\n',
        '## Проверка корректности и материалы\n\n'
        'Проверки: совпадение count/checksum Bronze с источником, уникальность ключей, внешние ключи, '
        'отсутствие отклонённых строк штатного TPC-H, предикаты Silver, 10 строк Gold, равенство ранжированных ключей/дат/приоритетов '
        'с Q3 на tpch. Для выручки DECIMAL против DOUBLE допускается абсолютная погрешность 0.0001; '
        'разная длина top 10 или разные ключи считаются ошибкой. Каждая benchmark-копия и каждый повтор Q3 также проверяются.\n',
    ]
    if s.get('checks'):
        lines.append(table(['Проверка', 'Результат'], [[r['check'], 'PASS' if r['passed'] else 'FAIL'] for r in s['checks']]))
    lines += [
        f'\nДоказательства прогона: `{evidence}/`. В отчёт не подставляются примерные секунды или размеры. '
        'Если прогон остановлен, причина записывается и статус не меняется на «завершён».\n',
        '\nИсточники технических решений:\n\n'
        '- [Trino Iceberg: свойства таблиц, $files, schema evolution, time travel](https://trino.io/docs/current/connector/iceberg.html)\n'
        '- [Trino: Iceberg REST Catalog](https://trino.io/docs/current/object-storage/metastores.html#rest-catalog)\n'
        '- [Trino: S3 и MinIO](https://trino.io/docs/current/object-storage/file-system-s3.html)\n'
        '- [Trino: генератор TPC-H](https://trino.io/docs/current/connector/tpch.html)\n'
        '- [Lakekeeper 0.9: bootstrap](https://docs.lakekeeper.io/docs/0.9.x/bootstrap/)\n'
        '- [Lakekeeper 0.9: подключение движков](https://docs.lakekeeper.io/docs/0.9.x/engines/)\n'
        '- [Lakekeeper v0.9.0: OpenAPI Management](https://github.com/lakekeeper/lakekeeper/blob/v0.9.0/docs/docs/api/management-open-api.yaml)\n'
        '- [Superset: Trino](https://superset.apache.org/user-docs/databases/supported/trino/)\n',
    ]
    text = '\n'.join(lines)
    (ROOT / 'report.md').write_text(text, encoding='utf-8')
    if run_dir:
        (Path(run_dir) / 'report.md').write_text(text, encoding='utf-8')
    return text


if __name__ == '__main__':
    make_report()
