"""Recoleccion historica y exportacion reproducible de PostgreSQL en modo de solo lectura."""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

HOURLY = "temperature_2m,relative_humidity_2m,precipitation,wind_speed_10m,et0_fao_evapotranspiration,shortwave_radiation"


def collect(out: Path, cutoff: str, database: bool) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    if any(out.iterdir()):
        raise FileExistsError("Usar un snapshot nuevo; no sobrescribir evidencia congelada")
    end = datetime.fromisoformat(cutoff)
    if end.tzinfo is None or end < datetime(2026, 10, 1, tzinfo=timezone.utc):
        raise ValueError("Corte invalido: especificar fecha/hora y offset")
    if end > datetime.now(timezone.utc):
        raise ValueError("No se pueden recolectar observaciones de un corte futuro")
    manifest = {"cutoff": cutoff, "retrieved_at_utc": datetime.now(timezone.utc).isoformat(), "sources": []}
    def fetch(name, url, kind):
        entry = {"name": name, "url": url, "kind": kind}
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "VitiAlert-Thesis-Research/1.0"})
            with urllib.request.urlopen(request, timeout=50) as response:
                raw = response.read()
                entry["final_url"] = response.geturl()
            (out / name).write_bytes(raw)
            if name.endswith(".csv") and b"<html" in raw[:1000].lower():
                raise ValueError("HTML recibido en lugar de CSV: no son observaciones")
            if name.endswith(".json"):
                parsed = json.loads(raw)
                if "hourly" not in parsed:
                    raise ValueError("Falta serie horaria meteorologica")
            entry.update(status="downloaded", bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
            print(name, len(raw), "bytes", flush=True)
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            entry.update(status="unavailable", error=str(exc)[:300])
            print(name, "NO DISPONIBLE", str(exc)[:130], flush=True)
        manifest["sources"].append(entry)
    params = {"latitude": -31.655, "longitude": -68.575, "start_date": "2026-10-01",
              "end_date": end.astimezone(timezone.utc).date().isoformat(), "hourly": HOURLY, "timezone": "UTC"}
    for model in ("era5", "ecmwf_ifs"):
        fetch(f"open_meteo_{model}.json", "https://archive-api.open-meteo.com/v1/archive?" +
              urllib.parse.urlencode(params | {"models": model}), "REANALYSIS_OR_ANALYSIS_NOT_STATION")
    fetch("open_meteo_forecast.json", "https://api.open-meteo.com/v1/forecast?" +
          urllib.parse.urlencode(params), "MODEL_NOT_STATION_PROVISIONAL")
    fetch("noaa_gsod_87311099999.csv", "https://www.ncei.noaa.gov/data/global-summary-of-the-day/access/2026/87311099999.csv", "STATION_DAILY_UTC_NOT_LOCAL_DAY")
    fetch("noaa_hourly_87311099999.csv", "https://www.ncei.noaa.gov/data/global-hourly/access/2026/87311099999.csv", "STATION_REPORTS_NOT_POCITO_PLOT")
    fetch("smn_download_page.html", "https://www.smn.gob.ar/descarga-de-datos", "OFFICIAL_CATALOG_NOT_OBSERVATIONS")
    if database:
        psql = os.getenv("VITIALERT_PSQL", r"C:\Program Files\PostgreSQL\18\bin\psql.exe")
        env = os.environ.copy()
        env["PGOPTIONS"] = "-c default_transaction_read_only=on -c statement_timeout=15000"
        env["PGSSLMODE"] = "require"
        env["PGCONNECT_TIMEOUT"] = "15"
        # SQL usa literales ISO validados, nunca interpolacion libre del usuario.
        until = end.astimezone(timezone.utc).isoformat()
        queries = {
            "telemetry_real.csv": "SELECT * FROM telemetry_reading WHERE timestamp_received >= '2026-10-01T03:00:00Z' AND timestamp_received <= '" + until + "' ORDER BY timestamp_received,id",
            "weather_backend.csv": "SELECT * FROM weather_observation WHERE observation_date >= '2026-10-01' AND observation_date <= '" + end.date().isoformat() + "' ORDER BY observation_date,source",
            "satellite_real.csv": "SELECT * FROM satellite_observation WHERE retrieved_at <= '" + until + "' ORDER BY retrieved_at,id",
            "nodes_real.csv": "SELECT id, external_id, latitud, longitud FROM node ORDER BY id",
            "irrigation_real.csv": "SELECT * FROM irrigation_event WHERE started_at >= '2026-10-01T03:00:00Z' AND started_at <= '" + until + "' ORDER BY started_at,id",
        }
        for name, query in queries.items():
            proc = subprocess.run([psql, "-X", "-w", "-q", "-v", "ON_ERROR_STOP=1", "-c", f"COPY ({query}) TO STDOUT WITH CSV HEADER"], env=env, capture_output=True, timeout=40)
            if proc.returncode:
                raise RuntimeError(proc.stderr.decode(errors="replace")[:500])
            (out / name).write_bytes(proc.stdout)
            count = len(list(csv.DictReader(io.StringIO(proc.stdout.decode("utf-8")))))
            manifest["sources"].append({"name": name, "kind": "POSTGRESQL_MEASURED_RAW", "status": "exported_read_only", "rows": count,
                                        "sha256": hashlib.sha256(proc.stdout).hexdigest()})
            print(name, count, "registros reales", flush=True)
    (out / "manifest_sources.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--cutoff", default="2026-10-14T18:57:00-03:00")
    p.add_argument("--database", action="store_true")
    a = p.parse_args()
    collect(a.output, a.cutoff, a.database)
