CREATE TABLE iceberg.bronze.lineitem (
   orderkey bigint,
   linenumber integer,
   extendedprice double,
   discount double,
   shipdate date
)
WITH (
   compression_codec = 'ZSTD',
   format = 'PARQUET',
   format_version = 2,
   location = 's3://warehouse/lab/01a14a88-e14f-79b3-8439-fb9ea8f91112/lineitem-e70eabd14ac64ae28dcb4bf865e1345d'
);
