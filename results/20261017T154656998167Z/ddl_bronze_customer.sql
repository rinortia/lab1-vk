CREATE TABLE iceberg.bronze.customer (
   custkey bigint,
   mktsegment varchar
)
WITH (
   compression_codec = 'ZSTD',
   format = 'PARQUET',
   format_version = 2,
   location = 's3://warehouse/lab/01a14a88-e14f-79b3-8439-fb9ea8f91112/customer-d395be812b02405eaa7fa67d9eb42c41'
);
