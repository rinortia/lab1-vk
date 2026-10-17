CREATE TABLE iceberg.bronze.orders (
   orderkey bigint,
   custkey bigint,
   orderdate date,
   shippriority integer
)
WITH (
   compression_codec = 'ZSTD',
   format = 'PARQUET',
   format_version = 2,
   location = 's3://warehouse/lab/01a14a88-e14f-79b3-8439-fb9ea8f91112/orders-f3398fc2bfae4df09d026b39e2e8fe2f'
);
