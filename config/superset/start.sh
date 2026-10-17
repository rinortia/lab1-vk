#!/usr/bin/env bash
set -euo pipefail
superset db upgrade
python /app/pythonpath/create_admin.py
superset init
exec gunicorn --bind 0.0.0.0:8088 --workers 1 --threads 4 --timeout 120 'superset.app:create_app()'
