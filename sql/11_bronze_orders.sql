CREATE TABLE iceberg.{{schema}}.orders
WITH (format = '{{format}}', compression_codec = '{{codec}}', format_version = 2)
AS SELECT orderkey, custkey, orderdate, shippriority FROM tpch.{{scale}}.orders;
