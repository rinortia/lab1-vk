CREATE TABLE iceberg.{{schema}}.lineitem
WITH (format = '{{format}}', compression_codec = '{{codec}}', format_version = 2)
AS SELECT orderkey, linenumber, extendedprice, discount, shipdate
FROM tpch.{{scale}}.lineitem;
