CREATE TABLE iceberg.silver.rejected_rows (
   source_table varchar,
   row_id varchar,
   reason varchar
)
WITH (
   compression_codec = 'ZSTD',
   format = 'PARQUET',
   format_version = 2,
   location = 's3://warehouse/lab/01a14a88-e1a7-7d81-9001-d5ef3901cf8f/rejected_rows-66254185ca1b4c3fbb6de20be10c74fa'
);
