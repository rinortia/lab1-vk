-- Actual snapshot id from this run; applies only to the demonstration table.
SELECT count(*) FROM iceberg.silver.evolution_demo FOR VERSION AS OF 757705280548165639;
ALTER TABLE iceberg.silver.evolution_demo EXECUTE rollback_to_snapshot(757705280548165639);
SELECT count(*) FROM iceberg.silver.evolution_demo;
