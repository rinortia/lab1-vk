"""Register Bronze and Gold datasets, build a dashboard, read Bronze in the BI container."""
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine, text
from superset.app import create_app
from superset import db

URI = 'trino://bi@trino:8080/iceberg'
app = create_app()
with app.app_context():
    # Superset model imports access current_app during module initialization.
    from superset.models.core import Database
    from superset.connectors.sqla.models import SqlaTable
    from superset.models.slice import Slice
    from superset.models.dashboard import Dashboard

    database = db.session.query(Database).filter_by(database_name='Lakehouse Trino').one_or_none()
    if database is None:
        database = Database(database_name='Lakehouse Trino', sqlalchemy_uri=URI,
                            expose_in_sqllab=True, allow_ctas=False, allow_cvas=False)
        db.session.add(database)
        db.session.commit()
    charts = []
    for schema, name, columns, title in [
        ('bronze', 'lineitem', ['orderkey', 'linenumber', 'extendedprice', 'discount', 'shipdate'], 'Bronze lineitem preview'),
        ('gold', 'q3_shipping_priority', ['orderkey', 'revenue', 'orderdate', 'shippriority'], 'Q3 Shipping Priority Top 10'),
    ]:
        dataset = db.session.query(SqlaTable).filter_by(
            database_id=database.id, schema=schema, table_name=name).one_or_none()
        if dataset is None:
            dataset = SqlaTable(database=database, schema=schema, table_name=name)
            db.session.add(dataset)
            db.session.commit()
        dataset.fetch_metadata()
        chart = db.session.query(Slice).filter_by(slice_name=title).one_or_none()
        if chart is None:
            chart = Slice(slice_name=title, datasource_id=dataset.id, datasource_type='table', viz_type='table')
            db.session.add(chart)
        params = {
            'viz_type': 'table', 'datasource': f'{dataset.id}__table', 'query_mode': 'raw',
            'all_columns': columns, 'row_limit': 10, 'server_pagination': False,
            'order_by_cols': [json.dumps(['revenue', False])] if schema == 'gold' else
                             [json.dumps(['orderkey', True]), json.dumps(['linenumber', True])],
            'adhoc_filters': [], 'time_range': 'No filter',
        }
        chart.params = json.dumps(params)
        chart.query_context = json.dumps({
            'datasource': {'id': dataset.id, 'type': 'table'}, 'force': False,
            'queries': [{
                'filters': [], 'extras': {'having': '', 'where': ''},
                'columns': columns, 'metrics': [],
                'orderby': [['revenue', False]] if schema == 'gold' else
                           [['orderkey', True], ['linenumber', True]],
                'row_limit': 10, 'order_desc': schema == 'gold',
            }],
            'form_data': params, 'result_format': 'json', 'result_type': 'full',
        })
        db.session.commit()
        charts.append(chart)
    dashboard = db.session.query(Dashboard).filter_by(slug='q3-lakehouse').one_or_none()
    if dashboard is None:
        dashboard = Dashboard(dashboard_title='Local Lakehouse Q3', slug='q3-lakehouse', published=True)
        db.session.add(dashboard)
    dashboard.slices = charts
    positions = {
        'DASHBOARD_VERSION_KEY': 'v2',
        'ROOT_ID': {'id': 'ROOT_ID', 'type': 'ROOT', 'children': ['GRID_ID']},
        'GRID_ID': {'id': 'GRID_ID', 'type': 'GRID', 'children': ['ROW-0', 'ROW-1'], 'parents': ['ROOT_ID']},
        'HEADER_ID': {'id': 'HEADER_ID', 'type': 'HEADER', 'meta': {'text': 'Local Lakehouse Q3'}},
    }
    for i, chart in enumerate(charts):
        row_id, chart_id = f'ROW-{i}', f'CHART-{chart.id}'
        positions[row_id] = {'id': row_id, 'type': 'ROW', 'children': [chart_id],
            'parents': ['ROOT_ID', 'GRID_ID'], 'meta': {'background': 'BACKGROUND_TRANSPARENT'}}
        positions[chart_id] = {'id': chart_id, 'type': 'CHART', 'children': [],
            'parents': ['ROOT_ID', 'GRID_ID', row_id],
            'meta': {'chartId': chart.id, 'sliceName': chart.slice_name, 'width': 12, 'height': 50}}
    dashboard.position_json = json.dumps(positions)
    db.session.commit()

    # Execute via the same SQLAlchemy URI as the registered Superset database.
    engine = create_engine(URI)
    with engine.connect() as connection:
        counts_sql = 'SELECT count(*) FROM iceberg.bronze.lineitem'
        count = int(connection.execute(text(counts_sql)).scalar())
        preview_sql = ('SELECT orderkey, linenumber, extendedprice, discount, shipdate '
                       'FROM iceberg.bronze.lineitem ORDER BY orderkey, linenumber LIMIT 10')
        result = connection.execute(text(preview_sql))
        preview = [dict(row._mapping) for row in result]
    evidence = {
        'at_utc': datetime.now(timezone.utc).isoformat(), 'tool': 'Apache Superset 4.1.2',
        'database_name': database.database_name, 'sqlalchemy_uri': URI,
        'executed_from': 'superset container using SQLAlchemy Trino driver',
        'sql': [counts_sql, preview_sql], 'bronze_lineitem_rows': count, 'preview': preview,
        'dashboard_path': '/superset/dashboard/q3-lakehouse/',
        'dashboard_id': dashboard.id, 'chart_ids': [c.id for c in charts],
        'ui_screenshot_attached': False,
    }
    run_id = os.environ['EVIDENCE_RUN_ID']
    if not run_id.isalnum():
        raise ValueError('Invalid evidence run id')
    path = Path('/evidence') / run_id / 'bi_proof.json'
    path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2, default=str) + '\n', encoding='utf-8')
    print(json.dumps(evidence, ensure_ascii=False, default=str))
