"""Conserva respuestas GET con un corte fijo, sin escribir en el backend."""
from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
CUTOFF = "2026-10-28T19:00:00+00:00"
BASE = "https://vitialert-backend.onrender.com"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    folder = ROOT / "fuentes_api"
    manifest = folder / "MANIFIESTO_FUENTES.json"
    if manifest.exists():
        raise FileExistsError("El snapshot ya existe; no se sobrescribe.")
    started = datetime.now(timezone.utc).isoformat()
    sources = []
    for endpoint in ("telemetry", "irrigation-events"):
        page, ids, totals = 0, set(), []
        while True:
            params = {"page": page, "size": 500, "from": "2026-09-17T00:00:00Z", "to": CUTOFF}
            url = f"{BASE}/api/nodes/1/{endpoint}?{urlencode(params)}"
            for attempt in range(3):
                try:
                    with urlopen(url, timeout=60) as response:
                        raw = response.read()
                    break
                except Exception:
                    if attempt == 2:
                        raise
                    time.sleep(3 * (attempt + 1))
            body = json.loads(raw)
            path = folder / f"{endpoint}_{page:03d}.json"
            if path.exists():
                if path.read_bytes() != raw:
                    raise ValueError("La respuesta cambió respecto de una descarga parcial.")
            else:
                path.write_bytes(raw)
            totals.append(body["total_elements"])
            for row in body["content"]:
                if row["id"] in ids:
                    raise ValueError("Identificador repetido durante paginación.")
                ids.add(row["id"])
            sources.append({"url": url, "file": path.name, "rows": len(body["content"]), "sha256": digest(path)})
            page += 1
            if page % 10 == 0 or page >= body["total_pages"]:
                print(f"{endpoint}: {len(ids)}/{body['total_elements']} filas", flush=True)
            if page >= body["total_pages"]:
                break
        if len(set(totals)) != 1 or len(ids) != totals[0]:
            raise ValueError("La paginación cambió durante la descarga.")
    manifest.write_text(json.dumps({
        "cutoff_utc": CUTOFF, "cutoff_local": "2026-10-28T16:00:00-03:00",
        "download_started_utc": started, "download_finished_utc": datetime.now(timezone.utc).isoformat(),
        "read_only": True, "node_external_id": "1", "requests": sources,
        "scope": "Respuestas API filtradas al corte; el respaldo nativo de PostgreSQL se conserva por separado."
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Snapshot GET completo y verificado.", flush=True)


if __name__ == "__main__":
    main()
