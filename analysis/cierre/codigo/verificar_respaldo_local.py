"""Repite la restauración y exporta las tablas desde el respaldo ya descargado."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

from respaldar_postgres import ROOT, TABLES, run


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--existing-cluster", type=Path)
    args = parser.parse_args()
    folder = ROOT / "respaldo_bd"
    dump = folder / "vitialert_respaldo_nativo_2026-10-28.dump"
    manifest = folder / "MANIFIESTO_RESPALDO.json"
    metadata = json.loads(manifest.read_text(encoding="utf-8")) if manifest.exists() else {}
    env = {k: v for k, v in os.environ.items() if not k.startswith("PG")}
    cluster = (args.existing_cluster or Path(tempfile.gettempdir()) / ("vitialert_cierre_restore_" + uuid.uuid4().hex)).resolve()
    assert cluster.parent == Path(tempfile.gettempdir()).resolve() and cluster.name.startswith("vitialert_cierre_restore_")
    started = False
    try:
        if args.existing_cluster:
            port = int((cluster / "postmaster.pid").read_text().splitlines()[3])
            started = True
        else:
            with socket.socket() as available:
                available.bind(("127.0.0.1", 0))
                port = available.getsockname()[1]
            run("initdb.exe", ["-D", cluster, "--username=vitialert_snapshot", "--auth=trust", "--encoding=UTF8", "--no-locale"], env)
            run("pg_ctl.exe", ["-D", cluster, "-l", cluster / "restore_server.log", "-o", f"-h 127.0.0.1 -p {port}", "-w", "start"], env)
            started = True
        env.update(PGHOST="127.0.0.1", PGPORT=str(port), PGUSER="vitialert_snapshot", PGDATABASE="vitialert_cierre", PGCLIENTENCODING="UTF8")
        run("createdb.exe", ["--encoding=UTF8", "vitialert_cierre"], env)
        run("pg_restore.exe", ["--exit-on-error", "--no-owner", "--no-privileges", "--dbname=vitialert_cierre", dump], env)
        exports = folder / "tablas"
        exports.mkdir(exist_ok=True)
        env["PGOPTIONS"] = "-c default_transaction_read_only=on"
        metadata["tables"] = {}
        for name, order in TABLES.items():
            p = exports / (name + ".jsonl")
            run("psql.exe", ["-X", "-A", "-t", "-v", "ON_ERROR_STOP=1", "-c",
                             f'SELECT row_to_json(t) FROM (SELECT * FROM public."{name}" ORDER BY "{order}") t;', "-o", p], env)
            count = len([line for line in p.read_text(encoding="utf-8").splitlines() if line.strip()])
            metadata["tables"][name] = dict(rows=count, sha256=hashlib.sha256(p.read_bytes()).hexdigest())
            print(f"{name}: {count:,} filas restauradas y exportadas.", flush=True)
        metadata.update(full_restore_test="SUCCESS_IN_ISOLATED_LOCAL_DATABASE", production_mutated=False,
                        format="PostgreSQL custom archive", credential_included=False,
                        analysis_cutoff_utc="2026-10-28T19:00:00Z", analysis_cutoff_local="2026-10-28T16:00:00-03:00",
                        backup_bytes=dump.stat().st_size, backup_sha256=hashlib.sha256(dump.read_bytes()).hexdigest(),
                        local_cluster_directory=str(cluster), local_cluster_port=port,
                        completed_utc=datetime.now(timezone.utc).isoformat())
    finally:
        if started:
            run("pg_ctl.exe", ["-D", cluster, "-m", "fast", "-w", "stop"], env)
            metadata["local_cluster_stopped"] = True
        manifest.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
