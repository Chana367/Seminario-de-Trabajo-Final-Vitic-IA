"""Descarga PostgreSQL y verifica su restauración en una instancia local aislada."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import subprocess
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BIN = Path(r"C:\Program Files\PostgreSQL\18\bin")
TABLES = {"flyway_schema_history": "installed_rank", "node": "id", "telemetry_reading": "id",
          "irrigation_event": "id", "weather_observation": "id", "satellite_observation": "id"}


def run(name, args, env, timeout=180):
    if name == "pg_ctl.exe" and "start" in args:
        # Evita que los procesos hijos hereden pipes de captura en Windows.
        process = subprocess.run([str(BIN / name), *map(str, args)], env=env, stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL, timeout=timeout, creationflags=subprocess.CREATE_NO_WINDOW)
        if process.returncode:
            raise RuntimeError("pg_ctl no inició la instancia aislada; revisar restore_server.log.")
        return ""
    process = subprocess.run([str(BIN / name), *map(str, args)], env=env, capture_output=True,
                             timeout=timeout, creationflags=subprocess.CREATE_NO_WINDOW)
    if process.returncode:
        # Los errores no contienen contraseñas: estas se pasan únicamente por entorno.
        message = process.stderr.decode("utf-8", errors="replace")
        raise RuntimeError(f"{name} terminó con código {process.returncode}: {message}")
    return process.stdout.decode("utf-8", errors="replace")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--connection-file", type=Path, required=True)
    args = parser.parse_args()
    config = json.loads(args.connection_file.read_text(encoding="utf-8"))
    folder = ROOT / "respaldo_bd"
    folder.mkdir(exist_ok=True)
    dump = folder / "vitialert_respaldo_nativo_2026-10-28.dump"
    if dump.exists():
        raise FileExistsError("El respaldo nativo ya existe y no se sobrescribe.")
    dbeaver = json.loads((Path.home() / "AppData/Roaming/DBeaverData/workspace6/General/.dbeaver/data-sources.json").read_text(encoding="utf-8"))
    candidates = [x["configuration"]["host"] for x in dbeaver["connections"].values()
                  if x.get("configuration", {}).get("database") == config["DB_NAME"]
                  and x.get("configuration", {}).get("host", "").split(".")[0] == config["DB_HOST"].split(".")[0]]
    if "." in config["DB_HOST"]:
        host = config["DB_HOST"]
    elif len(candidates) == 1:
        host = candidates[0]
    else:
        raise ValueError("Falta verificar el hostname externo de Render.")
    remote = os.environ.copy()
    remote.update(PGHOST=host, PGPORT=str(config["DB_PORT"]), PGUSER=config["DB_USERNAME"],
                  PGPASSWORD=config["DB_PASSWORD"], PGDATABASE=config["DB_NAME"],
                  PGSSLMODE="require", PGCONNECT_TIMEOUT="20", PGCLIENTENCODING="UTF8",
                  PGOPTIONS="-c default_transaction_read_only=on -c statement_timeout=180000")
    cluster, started = None, False
    metadata = {"started_utc": datetime.now(timezone.utc).isoformat(),
                "analysis_cutoff_utc": "2026-10-28T19:00:00Z", "analysis_cutoff_local": "2026-10-28T16:00:00-03:00",
                "production_mutated": False, "format": "PostgreSQL custom archive",
                "note": "El respaldo captura el estado al descargar. El análisis filtra el corte; las tablas originales preservan también las filas posteriores si existen.",
                "credential_included": False}
    try:
        metadata["server_version"] = run("psql.exe", ["-X", "-A", "-t", "-c", "SHOW server_version;"], remote).strip()
        run("pg_dump.exe", ["--format=custom", "--no-owner", "--no-privileges", "--encoding=UTF8",
                             "--lock-wait-timeout=15000", "--file", dump], remote, timeout=300)
        metadata["download_finished_utc"] = datetime.now(timezone.utc).isoformat()
        metadata["backup_bytes"] = dump.stat().st_size
        metadata["backup_sha256"] = hashlib.sha256(dump.read_bytes()).hexdigest()
        print(f"Respaldo nativo descargado: {dump.stat().st_size:,} bytes.", flush=True)
        inventory = run("pg_restore.exe", ["--list", dump], os.environ.copy())
        (folder / "contenido_del_respaldo.txt").write_text(inventory, encoding="utf-8")
        cluster = Path(tempfile.gettempdir()) / ("vitialert_cierre_restore_" + uuid.uuid4().hex)
        cluster = cluster.resolve()
        assert cluster.parent == Path(tempfile.gettempdir()).resolve() and cluster.name.startswith("vitialert_cierre_restore_")
        with socket.socket() as available:
            available.bind(("127.0.0.1", 0))
            port = available.getsockname()[1]
        local = os.environ.copy()
        for key in list(local):
            if key.startswith("PG"):
                local.pop(key)
        run("initdb.exe", ["-D", cluster, "--username=vitialert_snapshot", "--auth=trust", "--encoding=UTF8", "--no-locale"], local)
        run("pg_ctl.exe", ["-D", cluster, "-l", cluster / "restore_server.log", "-o", f"-h 127.0.0.1 -p {port}", "-w", "start"], local)
        started = True
        local.update(PGHOST="127.0.0.1", PGPORT=str(port), PGUSER="vitialert_snapshot", PGDATABASE="vitialert_cierre", PGCLIENTENCODING="UTF8")
        run("createdb.exe", ["--encoding=UTF8", "vitialert_cierre"], local)
        run("pg_restore.exe", ["--exit-on-error", "--no-owner", "--no-privileges", "--dbname=vitialert_cierre", dump], local)
        metadata["full_restore_test"] = "SUCCESS_IN_ISOLATED_LOCAL_DATABASE"
        exports = folder / "tablas"
        exports.mkdir(exist_ok=True)
        local["PGOPTIONS"] = "-c default_transaction_read_only=on"
        metadata["tables"] = {}
        for name, order in TABLES.items():
            output = exports / (name + ".jsonl")
            run("psql.exe", ["-X", "-A", "-t", "-v", "ON_ERROR_STOP=1", "-c",
                             f'SELECT row_to_json(t) FROM (SELECT * FROM public."{name}" ORDER BY "{order}") t;', "-o", output], local)
            count = sum(bool(x.strip()) for x in output.read_text(encoding="utf-8").splitlines())
            metadata["tables"][name] = {"rows": count, "sha256": hashlib.sha256(output.read_bytes()).hexdigest()}
            print(f"Restauración verificada, {name}: {count:,} filas.", flush=True)
        metadata["completed_utc"] = datetime.now(timezone.utc).isoformat()
        metadata["local_cluster_directory"] = str(cluster)
        metadata["local_cluster_port"] = port
    finally:
        if started:
            assert cluster.parent == Path(tempfile.gettempdir()).resolve() and cluster.name.startswith("vitialert_cierre_restore_")
            run("pg_ctl.exe", ["-D", cluster, "-m", "fast", "-w", "stop"], os.environ.copy())
            metadata["local_cluster_stopped"] = True
        remote.pop("PGPASSWORD", None)
        config.clear()
        if args.connection_file.exists():
            args.connection_file.unlink()
        metadata["temporary_connection_removed"] = not args.connection_file.exists()
        (folder / "MANIFIESTO_RESPALDO.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
