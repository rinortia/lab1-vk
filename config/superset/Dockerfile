FROM apache/superset:4.1.2
USER root
RUN pip install --no-cache-dir 'trino[sqlalchemy]==0.333.0'
# Local lab: root lets the console proof write into the host-mounted results folder.
# All published ports are bound to 127.0.0.1 in compose.
