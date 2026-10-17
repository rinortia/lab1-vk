CREATE TABLE iceberg.silver.q3_lines (
   orderkey bigint,
   linenumber integer,
   custkey bigint,
   mktsegment varchar,
   orderdate date,
   shipdate date,
   shippriority integer,
   extendedprice decimal(15, 2),
   discount decimal(4, 2),
   net_revenue decimal(20, 4)
)
WITH (
   compression_codec = 'ZSTD',
   format = 'PARQUET',
   format_version = 2,
   location = 's3://warehouse/lab/01a14a88-e1a7-7d81-9001-d5ef3901cf8f/q3_lines-0b1f7a525c7d46e9b60210564a4700ce'
);
