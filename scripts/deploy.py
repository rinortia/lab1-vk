#!/usr/bin/env python3
"""Deploy the local stack and initialize its Lakekeeper warehouse."""
import json
import sys
from urllib.error import HTTPError, URLError

from lakehouse import Trino, bootstrap, compose, doctor


def main():
    try:
        print('Проверка Docker и Compose…', flush=True)
        doctor()
        compose('config', '--quiet')

        print('Запуск PostgreSQL, MinIO и Lakekeeper…', flush=True)
        compose('up', '-d', '--wait', '--wait-timeout', '300',
                'postgres', 'minio', 'lakekeeper')

        print('Инициализация каталога и warehouse lab…', flush=True)
        catalog = bootstrap()
        print(json.dumps(catalog, ensure_ascii=False, indent=2), flush=True)

        print('Запуск Trino и проверка SQL…', flush=True)
        compose('up', '-d', '--wait', '--wait-timeout', '300', 'trino')
        result = Trino().query('SELECT 1 AS ready', 'deployment_check')
        if result['rows'] != [[1]]:
            raise RuntimeError('Trino readiness query returned an unexpected result')

        print('Сборка и запуск Superset…', flush=True)
        compose('--profile', 'bi', 'up', '-d', '--build', '--wait',
                '--wait-timeout', '600', 'superset')
        compose('--profile', 'bi', 'ps', '-a')
        print('Сервисы развернуты. Superset: http://localhost:8088')
        print('Учебный вход Superset: admin / admin-local')
        print('Для загрузки Bronze, построения Gold и регистрации datasets выполните команду run из README.')
    except (RuntimeError, OSError, ValueError, HTTPError, URLError) as exc:
        print(f'ОШИБКА: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
