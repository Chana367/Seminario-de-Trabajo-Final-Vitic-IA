"""Genera el respaldo al corte exclusivamente desde la copia local restaurada."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path

from respaldar_postgres import ROOT, run


def main():
    folder = ROOT / "respaldo_bd"
    manifest_path = folder / "MANIFIESTO_RESPALDO.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    cluster = Path(manifest["local_cluster_directory"]).resolve()
    assert cluster.parent == Path(tempfile.gettempdir()).resolve() and cluster.name.startswith("vitialert_cierre_restore_")
    env = {k: v for k, v in os.environ.items() if not k.startswith("PG")}
    env.update(PGHOST="127.0.0.1", PGPORT=str(manifest["local_cluster_port"]), PGUSER="vitialert_snapshot", PGDATABASE="vitialert_cierre", PGCLIENTENCODING="UTF8")
    output = folder / "vitialert_corte_2026-10-28_1600.dump"
    if output.exists():
        raise FileExistsError("El respaldo del corte ya existe.")
    started = False
    try:
        run("pg_ctl.exe", ["-D", cluster, "-l", cluster / "restore_server.log", "-o", f"-h 127.0.0.1 -p {manifest['local_cluster_port']}", "-w", "start"], env)
        started = True
        cut = "2026-10-28T19:00:00Z"
        # Solo se modifica esta copia local. La base de Render y el archivo nativo
        # permanecen intactos. No hay eventos atravesando el corte en este snapshot.
        crossing = int(run("psql.exe", ["-X", "-At", "-v", "ON_ERROR_STOP=1", "-c", f"SELECT count(*) FROM irrigation_event WHERE started_at <= '{cut}'::timestamptz AND ended_at > '{cut}'::timestamptz"], env).strip())
        if crossing:
            raise ValueError("Hay eventos que cruzan el corte; requieren una exportación censurada explícita.")
        query = f"""BEGIN;
DELETE FROM telemetry_reading WHERE timestamp_received > '{cut}'::timestamptz;
DELETE FROM irrigation_event WHERE started_at > '{cut}'::timestamptz;
DELETE FROM satellite_observation WHERE retrieved_at > '{cut}'::timestamptz;
DELETE FROM weather_observation WHERE created_at > '{cut}'::timestamptz OR updated_at > '{cut}'::timestamptz;
COMMIT;"""
        result = run("psql.exe", ["-X", "-v", "ON_ERROR_STOP=1", "-c", query], env)
        run("pg_dump.exe", ["--format=custom", "--no-owner", "--no-privileges", "--encoding=UTF8", "--file", output], env)
        # Se comprueba además que el archivo filtrado se pueda restaurar.
        run("createdb.exe", ["vitialert_corte_verificado"], env)
        run("pg_restore.exe", ["--exit-on-error", "--no-owner", "--no-privileges", "--dbname=vitialert_corte_verificado", output], env)
        check_env = dict(env, PGDATABASE="vitialert_corte_verificado", PGOPTIONS="-c default_transaction_read_only=on")
        controls = json.loads(run("psql.exe", ["-X", "-At", "-v", "ON_ERROR_STOP=1", "-c", "SELECT json_build_object('readings',count(*),'latest_received',max(timestamp_received)) FROM telemetry_reading"], check_env).strip())
        assert controls["readings"] == 21180
        manifest["filtered_cut_backup"] = dict(file=output.name, bytes=output.stat().st_size,
                                              sha256=hashlib.sha256(output.read_bytes()).hexdigest(),
                                              restore_test="SUCCESS", controls=controls,
                                              filter_output=result.strip(), local_only=True,
                                              note="Exportación por timestamps del snapshot descargado; no recupera versiones sobreescritas de meteorología.")
        print(json.dumps(manifest["filtered_cut_backup"], ensure_ascii=False, indent=2), flush=True)
    finally:
        if started:
            run("pg_ctl.exe", ["-D", cluster, "-m", "fast", "-w", "stop"], env)
        manifest["local_cluster_stopped"] = True
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
