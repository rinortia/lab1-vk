CREATE TABLE iceberg.gold.q3_shipping_priority (
   orderkey bigint,
   revenue decimal(38, 4),
   orderdate date,
   shippriority integer
)
WITH (
   compression_codec = 'ZSTD',
   format = 'PARQUET',
   format_version = 2,
   location = 's3://warehouse/lab/01a14a88-e204-74d2-8a20-01607f79f71a/q3_shipping_priority-cc3a0976b58d4b9080043c240f78753a'
);
