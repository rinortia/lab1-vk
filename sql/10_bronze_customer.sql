CREATE TABLE iceberg.{{schema}}.customer
WITH (format = '{{format}}', compression_codec = '{{codec}}', format_version = 2)
AS SELECT custkey, mktsegment FROM tpch.{{scale}}.customer;
