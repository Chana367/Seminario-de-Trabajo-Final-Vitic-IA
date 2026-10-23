"""Fuentes instrumentales alternativas: conserva errores y rechaza HTML disfrazado de CSV."""
import argparse
import hashlib
import json
from pathlib import Path
from datetime import datetime, timezone, timedelta
import urllib.parse
import urllib.request


def probe(folder: Path, cutoff: str):
    end = datetime.fromisoformat(cutoff)
    tomorrow = end + timedelta(days=1)
    urls = {
        "noaa_access_hourly.json": "https://www.ncei.noaa.gov/access/services/data/v1?" + urllib.parse.urlencode({
            "dataset": "global-hourly", "stations": "87311099999", "startDate": "2026-10-01", "endDate": end.date().isoformat(), "format": "json", "includeAttributes": "true", "includeStationLocation": "true"}),
        "noaa_access_daily.json": "https://www.ncei.noaa.gov/access/services/data/v1?" + urllib.parse.urlencode({
            "dataset": "daily-summaries", "stations": "ARM00087311", "startDate": "2026-10-01", "endDate": end.date().isoformat(), "format": "json", "includeAttributes": "true", "includeStationLocation": "true", "units": "metric"}),
        "iem_sanu.csv": "https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py?" + urllib.parse.urlencode({
            "station": "SANU", "data": "all", "year1": 2026, "month1": 10, "day1": 1, "year2": tomorrow.year, "month2": tomorrow.month, "day2": tomorrow.day, "tz": "UTC", "format": "onlycomma", "latlon": "yes", "elev": "no", "missing": "M", "trace": "T", "direct": "no", "report_type": 3}),
    }
    manifest = []
    for name, url in urls.items():
        entry = {"name": name, "url": url, "retrieved_at_utc": datetime.now(timezone.utc).isoformat()}
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "VitiAlert-Thesis-Research/1.0"}), timeout=40) as r:
                raw = r.read()
                entry["final_url"] = r.geturl()
            (folder / name).write_bytes(raw)
            if name.endswith(".json"):
                rows = json.loads(raw)
                if not isinstance(rows, list):
                    raise ValueError("No es una lista de observaciones")
                entry.update(status="downloaded", rows=len(rows))
                print(name, "registros", len(rows), str(rows[:1])[:500], flush=True)
            else:
                if b"<html" in raw[:1000].lower() or b"station,valid" not in raw[:1500]:
                    raise ValueError("Respuesta no es CSV meteorologico")
                entry.update(status="downloaded", bytes=len(raw))
                print(name, len(raw), raw[:500].decode(errors="replace"), flush=True)
            entry["sha256"] = hashlib.sha256(raw).hexdigest()
        except Exception as exc:
            entry.update(status="unavailable_or_invalid", error=str(exc)[:300])
            print(name, entry["status"], entry["error"], flush=True)
        manifest.append(entry)
    (folder / "manifest_stations.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("folder", type=Path)
    p.add_argument("--cutoff", default="2026-10-14T18:57:00-03:00")
    a = p.parse_args()
    probe(a.folder, a.cutoff)
