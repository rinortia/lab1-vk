#!/usr/bin/env python3
"""Local Q3 lab. Python 3.10+, standard library only; Docker Compose v2 required."""
from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path
import platform
import random
import re
import shutil
import sqlite3
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone
from decimal import Decimal
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
PROJECT = "00000000-0000-0000-0000-000000000000"
COMBINATIONS = [("PARQUET", "GZIP"), ("PARQUET", "ZSTD"), ("ORC", "ZSTD")]
COLUMNS = {
    "customer": "custkey, mktsegment",
    "orders": "orderkey, custkey, orderdate, shippriority",
    "lineitem": "orderkey, linenumber, extendedprice, discount, shipdate",
}
ORDER = "ORDER BY revenue DESC, orderdate, orderkey"


def json_write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def csv_write(path, rows):
    if not rows:
        return
    with Path(path).open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def http_json(url, data=None, method=None, headers=None, timeout=60):
    payload = None if data is None else json.dumps(data).encode()
    h = {"Content-Type": "application/json", **(headers or {})}
    req = Request(url, data=payload, headers=h, method=method)
    with urlopen(req, timeout=timeout) as response:
        raw = response.read()
        return json.loads(raw) if raw else {}


def compose(*args, capture=False):
    p = subprocess.run(["docker", "compose", *args], cwd=ROOT, text=True,
                       stdout=subprocess.PIPE if capture else None,
                       stderr=subprocess.PIPE if capture else None)
    if p.returncode:
        raise RuntimeError(f"docker compose {' '.join(args)} failed ({p.returncode})\n{p.stderr or ''}")
    return p.stdout or ""


def render(name, **values):
    text = (ROOT / "sql" / name).read_text(encoding="utf-8")
    for key, value in values.items():
        if not re.fullmatch(r"[A-Za-z0-9_.]+", str(value)):
            raise ValueError(f"Unsafe SQL template value: {key}")
        text = text.replace("{{" + key + "}}", str(value))
    if "{{" in text:
        raise ValueError(f"Unresolved SQL template: {name}")
    return text.strip().rstrip(";")


def split_sql(text):
    """Split these standard SQL files while respecting quoted semicolons and comments."""
    statements, pending = [], ""
    for char in text:
        pending += char
        if char == ";" and sqlite3.complete_statement(pending):
            statements.append(pending.strip())
            pending = ""
    if pending.strip():
        statements.append(pending.strip())
    return statements


class Trino:
    def __init__(self, url="http://127.0.0.1:8080", journal=None, timeout=1800):
        self.url = url.rstrip("/")
        self.journal = journal
        self.timeout = timeout

    def _fetch(self, url, data=None, method=None):
        # Never replay POST: a write may have committed before a network error.
        req = Request(url, data=data, method=method, headers={
            "X-Trino-User": "student", "X-Trino-Source": "practical1-q3",
            "Content-Type": "text/plain; charset=utf-8",
        })
        for attempt in range(4):
            try:
                with urlopen(req, timeout=60) as response:
                    raw = response.read()
                    return json.loads(raw, parse_float=Decimal) if raw else {}
            except HTTPError as e:
                if req.get_method() == "GET" and e.code in (502, 503, 504) and attempt < 3:
                    time.sleep(0.25 * (attempt + 1))
                    continue
                raise RuntimeError(f"Trino HTTP {e.code}: {e.read().decode(errors='replace')}") from e

    def query(self, sql, label="sql"):
        sql = sql.strip().rstrip(";")
        start = time.perf_counter()
        next_uri = None
        rows, columns, stats, query_id = [], [], {}, None
        failure = None
        try:
            page = self._fetch(self.url + "/v1/statement", sql.encode(), "POST")
            while True:
                query_id = page.get("id", query_id)
                stats = page.get("stats", stats)
                columns = [c["name"] for c in page.get("columns", [])] or columns
                rows.extend(page.get("data", []))
                next_uri = page.get("nextUri")
                if page.get("error"):
                    err = page["error"]
                    raise RuntimeError(f"{err.get('errorName')}: {err.get('message')} [{query_id}]")
                if not next_uri:
                    break
                if time.perf_counter() - start > self.timeout:
                    raise TimeoutError(f"Query {query_id} exceeded {self.timeout}s")
                # The coordinator must keep pagination on the requested endpoint.
                if urlparse(next_uri).netloc != urlparse(self.url).netloc:
                    raise RuntimeError(f"Unexpected Trino nextUri authority: {urlparse(next_uri).netloc}")
                if not page.get("data"):
                    time.sleep(0.025)
                page = self._fetch(next_uri)
            if stats.get("state") not in (None, "FINISHED"):
                raise RuntimeError(f"Unexpected final state: {stats.get('state')}")
        except Exception as exc:
            failure = str(exc)
            if next_uri:
                try:
                    self._fetch(next_uri, method="DELETE")
                except Exception:
                    pass
            raise
        finally:
            wall = time.perf_counter() - start
            if self.journal:
                with Path(self.journal).open("a", encoding="utf-8") as f:
                    f.write(json.dumps({"at_utc": datetime.now(timezone.utc).isoformat(),
                        "label": label, "query_id": query_id, "sql": sql,
                        "wall_s": wall, "stats": stats, "error": failure,
                        "result_rows": len(rows)}, ensure_ascii=False, default=str) + "\n")
        return {"query_id": query_id, "columns": columns, "rows": rows, "wall_s": wall,
                "elapsed_s": float(stats.get("elapsedTimeMillis", 0)) / 1000,
                "cpu_s": float(stats.get("cpuTimeMillis", 0)) / 1000, "stats": stats}

    def scalar(self, sql, label="check"):
        return self.query(sql, label)["rows"][0][0]


def equal_q3(actual, expected, tolerance=Decimal("0.0001")):
    """Compare ranked keys/dates/priority exactly; decimal vs double revenue with tolerance."""
    if len(actual) != len(expected):
        return False
    for a, b in zip(actual, expected):
        if [a[0], a[2], a[3]] != [b[0], b[2], b[3]]:
            return False
        if abs(Decimal(str(a[1])) - Decimal(str(b[1]))) > tolerance:
            return False
    return True


def check(trino, evidence, name, sql, expected=0):
    actual = trino.scalar(sql, name)
    item = {"check": name, "actual": actual, "expected": expected, "passed": actual == expected}
    evidence.append(item)
    if not item["passed"]:
        raise RuntimeError(f"Data check failed: {name}: {actual!r} != {expected!r}")
    return actual


def bootstrap():
    base = "http://127.0.0.1:8181/management/v1"
    info = http_json(base + "/info")
    if not info["bootstrapped"]:
        http_json(base + "/bootstrap", {"accept-terms-of-use": True}, "POST")
    warehouses = http_json(base + "/warehouse?projectId=" + PROJECT)["warehouses"]
    if not any(w["name"] == "lab" for w in warehouses):
        http_json(base + "/warehouse", {
            "warehouse-name": "lab", "project-id": PROJECT,
            "storage-profile": {"type": "s3", "bucket": "warehouse", "key-prefix": "lab",
                "endpoint": "http://minio:9000", "region": "us-east-1",
                "path-style-access": True, "flavor": "s3-compat", "sts-enabled": False},
            "storage-credential": {"type": "s3", "credential-type": "access-key",
                "aws-access-key-id": "minioadmin", "aws-secret-access-key": "minioadmin-local"},
            "delete-profile": {"type": "hard"},
        }, "POST")
    # An existing warehouse must match this lab; never modify a foreign one silently.
    warehouses = http_json(base + "/warehouse?projectId=" + PROJECT)["warehouses"]
    warehouse = next(w for w in warehouses if w["name"] == "lab")
    profile = warehouse["storage-profile"]
    if profile["bucket"] != "warehouse" or profile.get("key-prefix") != "lab":
        raise RuntimeError("Existing 'lab' warehouse has a different storage profile")
    return {"server": http_json(base + "/info"), "warehouse_id": warehouse["id"]}


def inventory(t, schema, name, fmt="PARQUET", codec="ZSTD"):
    row = t.query(f'SELECT count(*), coalesce(sum(file_size_in_bytes), 0), '
                  f'coalesce(sum(record_count), 0) FROM iceberg.{schema}."{name}$files" WHERE content = 0',
                  "file_size")["rows"][0]
    count = int(t.scalar(f"SELECT count(*) FROM iceberg.{schema}.{name}", "row_count"))
    if count != int(row[2]):
        raise RuntimeError(f"Files vs rows mismatch: {schema}.{name}")
    return {"table": f"{schema}.{name}", "rows": count, "data_files": int(row[0]),
            "bytes": int(row[1]), "MB": int(row[1]) / 1_000_000,
            "format": fmt, "codec": codec, "partitioning": "нет"}


def fingerprint(t, source, table):
    return t.query(f"SELECT count(*), to_hex(checksum(ROW({COLUMNS[table]}))) "
                   f"FROM {source}.{table}", "fingerprint")["rows"][0]


def create_bronze(t, schema, fmt, codec, scale):
    t.query(f"CREATE SCHEMA IF NOT EXISTS iceberg.{schema}", "schema")
    timings = []
    for i, table in enumerate(COLUMNS):
        t.query(f"DROP TABLE IF EXISTS iceberg.{schema}.{table}", "drop_generated_table")
        result = t.query(render(f"{10+i}_bronze_{table}.sql", schema=schema,
                               format=fmt, codec=codec, scale=scale), "bronze_ctas")
        timings.append({"table": table, "query_id": result["query_id"],
                        "wall_s": result["wall_s"], "elapsed_s": result["elapsed_s"]})
    return timings


def table_schema(fmt, codec):
    return "bench_" + fmt.lower() + "_" + codec.lower()


def benchmark(t, args, run_dir, source_fingerprints, reference):
    writes, queries, sizes = [], [], []
    rng = random.Random(42)
    # Warm up source generation and all three CTAS shapes, outside write measurements.
    for fmt, codec in COMBINATIONS:
        create_bronze(t, "bench_warmup", fmt, codec, args.scale)
        for table in COLUMNS:
            t.query(f"DROP TABLE iceberg.bench_warmup.{table}", "drop_warmup")
    for repetition in range(1, args.write_repeats + 1):
        combos = list(COMBINATIONS)
        rng.shuffle(combos)
        for fmt, codec in combos:
            schema = table_schema(fmt, codec)
            print(f"Запись {repetition}/{args.write_repeats}: {fmt}/{codec}", flush=True)
            times = create_bronze(t, schema, fmt, codec, args.scale)
            for item in times:
                writes.append({"format": fmt, "codec": codec, "repetition": repetition, **item})
            tables = [inventory(t, schema, table, fmt, codec) for table in COLUMNS]
            sizes.append({"format": fmt, "codec": codec, "repetition": repetition,
                          "bytes": sum(x["bytes"] for x in tables),
                          "data_files": sum(x["data_files"] for x in tables)})
            for table in COLUMNS:
                if fingerprint(t, f"iceberg.{schema}", table) != source_fingerprints[table]:
                    raise RuntimeError(f"Benchmark data differ from source: {schema}.{table}")
            csv_write(run_dir / "write_runs.csv", writes)
            csv_write(run_dir / "size_runs.csv", sizes)
    for fmt, codec in COMBINATIONS:
        sql = render("40_q3.sql", source="iceberg." + table_schema(fmt, codec))
        warmup = t.query(sql, "q3_warmup")
        if not equal_q3(warmup["rows"], reference):
            raise RuntimeError(f"Warmup Q3 differs: {fmt}/{codec}")
    for repetition in range(1, args.repeats + 1):
        combos = list(COMBINATIONS)
        rng.shuffle(combos)
        for fmt, codec in combos:
            result = t.query(render("40_q3.sql", source="iceberg." + table_schema(fmt, codec)), "q3_measured")
            if not equal_q3(result["rows"], reference):
                raise RuntimeError(f"Measured Q3 differs: {fmt}/{codec}")
            queries.append({"format": fmt, "codec": codec, "repetition": repetition,
                "query_id": result["query_id"], "wall_s": result["wall_s"],
                "elapsed_s": result["elapsed_s"], "cpu_s": result["cpu_s"],
                "processed_rows": result["stats"].get("processedRows"),
                "processed_bytes": result["stats"].get("processedBytes")})
            csv_write(run_dir / "query_runs.csv", queries)
    summary = []
    for fmt, codec in COMBINATIONS:
        qr = [r for r in queries if (r["format"], r["codec"]) == (fmt, codec)]
        wr = [sum(r["elapsed_s"] for r in writes if r["format"] == fmt and r["codec"] == codec
                  and r["repetition"] == rep) for rep in range(1, args.write_repeats + 1)]
        ww = [sum(r["wall_s"] for r in writes if r["format"] == fmt and r["codec"] == codec
                  and r["repetition"] == rep) for rep in range(1, args.write_repeats + 1)]
        size = [r for r in sizes if r["format"] == fmt and r["codec"] == codec]
        summary.append({"format": fmt, "codec": codec,
            "write_elapsed_median_s": statistics.median(wr),
            "write_wall_median_s": statistics.median(ww),
            "query_elapsed_median_s": statistics.median(r["elapsed_s"] for r in qr),
            "query_wall_median_s": statistics.median(r["wall_s"] for r in qr),
            "query_elapsed_min_s": min(r["elapsed_s"] for r in qr),
            "query_elapsed_max_s": max(r["elapsed_s"] for r in qr),
            "query_elapsed_stdev_s": statistics.stdev(r["elapsed_s"] for r in qr) if len(qr)>1 else 0,
            "size_MB_median": statistics.median(r["bytes"] for r in size) / 1_000_000,
            "size_MB_final": size[-1]["bytes"] / 1_000_000,
            "data_files_final": size[-1]["data_files"]})
    csv_write(run_dir / "benchmark_summary.csv", summary)
    return summary


def evolution_and_restore(t, run_dir, checks):
    table = "iceberg.silver.evolution_demo"
    t.query(f"DROP TABLE IF EXISTS {table}", "demo_reset")
    t.query(f"CREATE TABLE {table} WITH (format='PARQUET', compression_codec='ZSTD') "
            "AS SELECT * FROM iceberg.silver.q3_lines ORDER BY orderkey, linenumber LIMIT 1000", "demo_copy")
    def files():
        return t.query('SELECT file_path, file_size_in_bytes FROM iceberg.silver."evolution_demo$files" '
                       'WHERE content = 0 ORDER BY file_path', "demo_files")["rows"]
    before = files()
    t.query(f"ALTER TABLE {table} ADD COLUMN quality_note VARCHAR", "schema_add")
    check(t, checks, "new_column_is_null", f"SELECT count(*) FROM {table} WHERE quality_note IS NOT NULL")
    t.query(f"ALTER TABLE {table} RENAME COLUMN quality_note TO dq_note", "schema_rename")
    after = files()
    same_files = before == after
    checks.append({"check": "schema_evolution_no_data_rewrite", "actual": same_files,
                   "expected": True, "passed": same_files})
    if not same_files:
        raise RuntimeError("Schema evolution unexpectedly rewrote data files")
    snapshot = int(t.scalar('SELECT snapshot_id FROM iceberg.silver."evolution_demo$history" '
                           'ORDER BY made_current_at DESC LIMIT 1', "snapshot_before_delete"))
    n = int(t.scalar(f"SELECT count(*) FROM {table}"))
    # Deliberate damage is isolated to this small demonstration copy.
    t.query(f"DELETE FROM {table}", "demo_delete")
    check(t, checks, "demo_deleted", f"SELECT count(*) FROM {table}")
    check(t, checks, "time_travel_reads_old_data", f"SELECT count(*) FROM {table} FOR VERSION AS OF {snapshot}", n)
    t.query(f"ALTER TABLE {table} EXECUTE rollback_to_snapshot({snapshot})", "demo_rollback")
    check(t, checks, "rollback_restores_count", f"SELECT count(*) FROM {table}", n)
    before_checksum = t.scalar(f"SELECT to_hex(checksum(ROW(orderkey, linenumber, net_revenue))) "
                              f"FROM {table} FOR VERSION AS OF {snapshot}")
    check(t, checks, "rollback_restores_checksum", f"SELECT to_hex(checksum(ROW(orderkey, linenumber, net_revenue))) FROM {table}", before_checksum)
    script = f"""-- Actual snapshot id from this run; applies only to the demonstration table.
SELECT count(*) FROM {table} FOR VERSION AS OF {snapshot};
ALTER TABLE {table} EXECUTE rollback_to_snapshot({snapshot});
SELECT count(*) FROM {table};
"""
    (run_dir / "restore.sql").write_text(script, encoding="utf-8")
    result = {"table": table, "snapshot_id": snapshot, "restored_rows": n,
              "data_files_unchanged_after_add_rename": same_files, "files_before": before, "files_after": after}
    json_write(run_dir / "evolution_restore.json", result)
    return result


def doctor():
    if not shutil.which("docker"):
        raise RuntimeError("Docker не найден. Установите Docker Engine/Desktop и Compose v2, затем повторите запуск.")
    compose("version", capture=True)
    p = subprocess.run(["docker", "info", "--format", "{{json .}}"], text=True, capture_output=True)
    if p.returncode:
        raise RuntimeError("Docker daemon недоступен. Запустите Docker Desktop/Engine.\n" + p.stderr)
    info = json.loads(p.stdout)
    return {k: info.get(k) for k in ("ServerVersion", "OSType", "Architecture", "NCPU", "MemTotal", "OperatingSystem", "Driver")}


def run(args):
    docker_info = doctor()
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    run_dir = ROOT / "results" / run_id
    run_dir.mkdir(parents=True)
    state = {"status": "started", "run_id": run_id, "author": args.author, "scale": args.scale,
             "query_repeats": args.repeats, "write_repeats": args.write_repeats,
             "host": {"system": platform.platform(), "python": platform.python_version(),
                      "host_cpus": os.cpu_count()}, "docker": docker_info,
             "checks": [], "inventory": [], "benchmark": []}
    if os.environ.get("GITHUB_ACTIONS") == "true":
        state["execution_environment"] = "Docker на одной VM GitHub Actions; не персональный компьютер студента"
        state["workflow_run_url"] = (os.environ.get("GITHUB_SERVER_URL", "https://github.com") + "/" +
                                     os.environ.get("GITHUB_REPOSITORY", "") + "/actions/runs/" +
                                     os.environ.get("GITHUB_RUN_ID", ""))
    else:
        state["execution_environment"] = "Локальный Docker на машине, выполнившей run"
    json_write(ROOT / "results" / "latest.json", {"run_id": run_id})
    def save():
        json_write(run_dir / "state.json", state)
    save()
    t = Trino(journal=run_dir / "queries.jsonl", timeout=args.query_timeout)
    try:
        print("Поднимаю PostgreSQL, MinIO, Lakekeeper и Trino…", flush=True)
        compose("config", "--quiet")
        compose("up", "-d", "--wait", "--wait-timeout", "300", "postgres", "minio", "lakekeeper")
        state["catalog"] = bootstrap()
        compose("up", "-d", "--wait", "--wait-timeout", "300", "trino")
        # Health endpoint can be ready before the first query succeeds.
        t.query("SELECT 1", "ready")
        (run_dir / "compose-config.yml").write_text(compose("config", capture=True), encoding="utf-8")
        (run_dir / "docker-version.txt").write_text(subprocess.check_output(["docker", "version"], text=True), encoding="utf-8")
        (run_dir / "images.jsonl").write_text(compose("images", "--format", "json", capture=True), encoding="utf-8")
        # Image IDs/digests, not only mutable human-readable tags.
        for service in ("postgres", "minio", "lakekeeper", "trino"):
            cid = compose("ps", "-q", service, capture=True).strip()
            image_id = subprocess.check_output(["docker", "inspect", "--format", "{{.Image}}", cid], text=True).strip()
            details = json.loads(subprocess.check_output(["docker", "image", "inspect", image_id], text=True))[0]
            state.setdefault("image_digests", {})[service] = {"id": image_id, "repo_digests": details.get("RepoDigests", [])}
        for statement in render("00_schemas.sql").split(";"):
            if statement.strip():
                t.query(statement, "schema")
        print(f"Источник tpch.{args.scale}; загрузка Bronze…", flush=True)
        state["source_fingerprints"] = {table: fingerprint(t, f"tpch.{args.scale}", table) for table in COLUMNS}
        create_bronze(t, "bronze", "PARQUET", "ZSTD", args.scale)
        for table in COLUMNS:
            same = fingerprint(t, "iceberg.bronze", table) == state["source_fingerprints"][table]
            state["checks"].append({"check": f"bronze_{table}_matches_source", "actual": same, "expected": True, "passed": same})
            if not same:
                raise RuntimeError(f"Bronze source mismatch: {table}")
            key = "orderkey, linenumber" if table == "lineitem" else ("custkey" if table == "customer" else "orderkey")
            check(t, state["checks"], f"unique_{table}", f"SELECT count(*) FROM (SELECT {key} FROM iceberg.bronze.{table} GROUP BY {key} HAVING count(*) > 1)")
        check(t, state["checks"], "orders_customer_fk", "SELECT count(*) FROM iceberg.bronze.orders o LEFT JOIN iceberg.bronze.customer c ON o.custkey=c.custkey WHERE c.custkey IS NULL")
        check(t, state["checks"], "lineitem_orders_fk", "SELECT count(*) FROM iceberg.bronze.lineitem l LEFT JOIN iceberg.bronze.orders o ON l.orderkey=o.orderkey WHERE o.orderkey IS NULL")
        for name in ("q3_lines", "rejected_rows", "evolution_demo"):
            t.query(f"DROP TABLE IF EXISTS iceberg.silver.{name}", "reset_generated_silver")
        t.query("DROP TABLE IF EXISTS iceberg.gold.q3_shipping_priority", "reset_generated_gold")
        t.query(render("20_silver.sql"), "silver_ctas")
        t.query(render("21_rejected.sql"), "quarantine_ctas")
        check(t, state["checks"], "tpch_has_no_rejected_rows", "SELECT count(*) FROM iceberg.silver.rejected_rows")
        check(t, state["checks"], "silver_business_predicates", "SELECT count(*) FROM iceberg.silver.q3_lines WHERE mktsegment <> 'BUILDING' OR orderdate >= DATE '1995-03-15' OR shipdate <= DATE '1995-03-15' OR net_revenue < 0")
        t.query(render("30_gold.sql"), "gold_ctas")
        reference = t.query(render("40_q3.sql", source=f"tpch.{args.scale}"), "reference_q3")["rows"]
        actual = t.query(f"SELECT orderkey, revenue, orderdate, shippriority FROM iceberg.gold.q3_shipping_priority {ORDER}", "gold_result")["rows"]
        match = equal_q3(actual, reference)
        state["checks"].append({"check": "gold_matches_source_q3", "actual": match, "expected": True, "passed": match})
        if not match:
            raise RuntimeError("Gold differs from source Q3")
        check(t, state["checks"], "gold_ten_rows", "SELECT count(*) FROM iceberg.gold.q3_shipping_priority", 10)
        json_write(run_dir / "gold.json", {"columns": ["orderkey", "revenue", "orderdate", "shippriority"], "rows": actual})
        json_write(run_dir / "reference_q3.json", {"rows": reference, "absolute_revenue_tolerance": "0.0001"})
        csv_write(run_dir / "gold.csv", [dict(zip(["orderkey", "revenue", "orderdate", "shippriority"], row)) for row in actual])
        for schema, names in [("bronze", list(COLUMNS)), ("silver", ["q3_lines", "rejected_rows"]), ("gold", ["q3_shipping_priority"])]:
            for name in names:
                state["inventory"].append(inventory(t, schema, name))
                ddl = t.query(f"SHOW CREATE TABLE iceberg.{schema}.{name}", "ddl")["rows"][0][0]
                (run_dir / f"ddl_{schema}_{name}.sql").write_text(ddl + ";\n", encoding="utf-8")
        csv_write(run_dir / "inventory.csv", state["inventory"])
        save()
        state["evolution"] = evolution_and_restore(t, run_dir, state["checks"])
        # BI runs only after timings; an earlier BI container must be stopped too.
        compose("--profile", "bi", "stop", "superset")
        state["benchmark"] = benchmark(t, args, run_dir, state["source_fingerprints"], reference)
        state["checks"].append({"check": "all_benchmark_copies_and_q3_results_match", "actual": True, "expected": True, "passed": True})
        save()
        print("Подключаю Superset и читаю Bronze из BI-контейнера…", flush=True)
        compose("--profile", "bi", "up", "-d", "--build", "--wait", "--wait-timeout", "600", "superset")
        compose("exec", "-T", "-e", "EVIDENCE_RUN_ID=" + run_id, "superset", "python", "/app/pythonpath/register.py")
        bi = json.loads((run_dir / "bi_proof.json").read_text(encoding="utf-8"))
        source_rows = int(state["source_fingerprints"]["lineitem"][0])
        if bi["bronze_lineitem_rows"] != source_rows:
            raise RuntimeError("Superset Bronze row count mismatch")
        state["bi"] = bi
        state["checks"].append({"check": "superset_reads_bronze", "actual": bi["bronze_lineitem_rows"], "expected": source_rows, "passed": True})
        state["status"] = "completed"
    except Exception as exc:
        state["status"] = "failed"
        state["error"] = str(exc)
        raise
    finally:
        state["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
        save()
        json_write(run_dir / "validation.json", state["checks"])
        try:
            (run_dir / "docker-ps.txt").write_text(compose("--profile", "bi", "ps", "-a", capture=True), encoding="utf-8")
            (run_dir / "service-logs.txt").write_text(compose("--profile", "bi", "logs", "--no-color", "--tail", "150", capture=True), encoding="utf-8")
        except Exception:
            pass
        from report import make_report
        make_report(state, run_dir)
    print(f"Готово. Отчёт: {ROOT / 'report.md'}\nДоказательства: {run_dir}\nSuperset: http://localhost:8088 (admin / admin-local)")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("run", help="Deploy, ELT, benchmark, BI, generate report")
    p.add_argument("--author", required=True, help="ФИО ровно как в VK Education")
    p.add_argument("--scale", default="sf1", help="TPC-H schema, default sf1")
    p.add_argument("--repeats", type=int, default=5)
    p.add_argument("--write-repeats", type=int, default=3)
    p.add_argument("--query-timeout", type=int, default=1800)
    sub.add_parser("doctor", help="Check Docker daemon and Compose")
    p = sub.add_parser("sql", help="Execute SQL statements from a file through Trino HTTP")
    p.add_argument("--file", type=Path, required=True)
    sub.add_parser("report", help="Regenerate report from latest saved run")
    args = parser.parse_args()
    try:
        if args.command == "run":
            if not re.fullmatch(r"sf[1-9][0-9]*", args.scale):
                parser.error("Use sf1, sf10, sf100, …; fractional scales are outside this lab")
            if args.repeats < 3 or args.write_repeats < 2:
                parser.error("At least 3 query repetitions and 2 write repetitions are required")
            args.author = args.author.strip()
            if len(args.author.split()) < 2:
                parser.error("Укажите ФИО как в VK Education")
            run(args)
        elif args.command == "doctor":
            print(json.dumps(doctor(), ensure_ascii=False, indent=2))
        elif args.command == "sql":
            t = Trino()
            for statement in split_sql(args.file.read_text(encoding="utf-8")):
                print(json.dumps(t.query(statement), ensure_ascii=False, indent=2, default=str))
        else:
            from report import make_report
            latest = json.loads((ROOT / "results" / "latest.json").read_text())["run_id"]
            run_dir = ROOT / "results" / latest
            make_report(json.loads((run_dir / "state.json").read_text(encoding="utf-8")), run_dir)
    except (RuntimeError, OSError, ValueError, HTTPError, URLError) as exc:
        print(f"ОШИБКА: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
