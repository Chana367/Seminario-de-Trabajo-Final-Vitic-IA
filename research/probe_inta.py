"""Inspeccion del catalogo publico INTA SIGA; no autentica ni evade restricciones."""
from pathlib import Path
import argparse
import re
import json
import urllib.request
import urllib.parse
from datetime import datetime, timezone, timedelta


def observations(folder, cutoff):
    """GET publicos usados por data.js; conservamos la respuesta sin inferir su zona horaria."""
    cut = datetime.fromisoformat(cutoff)
    if cut.tzinfo is None or cut > datetime.now(timezone.utc):
        raise ValueError("Corte sin zona horaria o en el futuro: no son observaciones disponibles")
    local = cut.astimezone(timezone(timedelta(hours=-3)))
    date_end = f"{local.day}-{local.month}-{local.year}"
    folder.mkdir(parents=True, exist_ok=True)
    base = "https://siga.inta.gob.ar/CdnaUV0iiERRpFQE.php?"
    manifest = []
    for kind, value, filename in [
        ("diario", f"444/1-10-2026/{date_end}", "pocito_daily.json"),
        ("datosestaciones", f"444/1-10-2026 00:00:00/{date_end} {local:%H:%M:%S}", "pocito_hourly.json"),
    ]:
        url = base + urllib.parse.urlencode({"param_type": kind, "param_value": value})
        entry = {"url": url, "retrieved_at": datetime.now(timezone.utc).isoformat(), "file": filename,
                 "cutoff": cutoff, "timestamp_basis": "UNRESOLVED_PROVIDER_Z_UTC_STRIPPED_BY_WEB_UI"}
        try:
            if (folder / filename).exists():
                raise FileExistsError("No sobrescribir registros de INTA ya descargados")
            req = urllib.request.Request(url, headers={"User-Agent": "VitiAlert-Thesis-Research/1.0"})
            with urllib.request.urlopen(req, timeout=45) as response:
                raw = response.read(15_000_000)
                entry["status"] = response.status
            (folder / filename).write_bytes(raw)
            data = json.loads(raw)
            entry["records"] = len(data)
            print(filename, "records", len(data), "sample", str(data[:2] if isinstance(data, list) else data)[:3000], flush=True)
        except Exception as exc:
            entry["error"] = str(exc)
            print(kind, type(exc).__name__, str(exc), flush=True)
        manifest.append(entry)
    (folder / "manifest_observations.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def probe(folder):
    folder.mkdir(parents=True, exist_ok=True)
    base = "https://siga.inta.gob.ar/"
    req = urllib.request.Request(base, headers={"User-Agent": "VitiAlert-Thesis-Research/1.0"})
    with urllib.request.urlopen(req, timeout=25) as r:
        text = r.read().decode("utf-8", errors="replace")
    (folder / "index.html").write_text(text, encoding="utf-8")
    refs = re.findall(r'<script[^>]+src=["\']([^"\']+)', text)
    print("Referencias publicas de la pagina:", refs, flush=True)
    findings = []
    for i, ref in enumerate(refs):
        if not any(k in ref for k in ["main.js", "data.js", "global.js", "urlserver.js"]):
            continue
        url = urllib.parse.urljoin(base, ref)
        if urllib.parse.urlparse(url).hostname != "siga.inta.gob.ar":
            continue
        with urllib.request.urlopen(url, timeout=25) as r:
            raw = r.read(6_000_000)
        content = raw.decode("utf-8", errors="replace")
        (folder / f"script_{i}.js").write_bytes(raw)
        urls = sorted(set(re.findall(r'https?://[^\s"\'<>`\\]{5,180}', content)))
        contexts = re.findall(r'.{0,70}(?:estaciones|Estaciones|precipitaci|api/|baseUrl|baseURL|Pocito).{0,160}', content)
        entry = {"url": url, "bytes": len(raw), "urls": [u.split("?")[0] for u in urls if any(k in u for k in ["inta", "siga", "api"])], "contexts": contexts[:15]}
        findings.append(entry)
        print(json.dumps(entry, ensure_ascii=False), flush=True)
    (folder / "catalog_findings.json").write_text(json.dumps(findings, ensure_ascii=False, indent=2), encoding="utf-8")
    # Endpoint GET publicado por js/urlserver.js (no son rutas adivinadas).
    source = next((x for x in findings if x["url"].endswith("/urlserver.js")), None)
    if source:
        index = refs.index("js/urlserver.js")
        config = (folder / f"script_{index}.js").read_text(encoding="utf-8")
        config = re.sub(r"/\*.*?\*/", "", config, flags=re.S)
        match = re.search(r"^var URL_MYSQL_ESTACION\s*=\s*'([^']+)'", config, flags=re.M)
        if match:
            url = urllib.parse.urljoin(base, match.group(1))
            with urllib.request.urlopen(url, timeout=25) as response:
                raw = response.read()
            (folder / "stations_response.json").write_bytes(raw)
            stations = json.loads(raw)
            near = [s for s in stations if any(k in json.dumps(s, ensure_ascii=False).lower() for k in ["pocito", "san juan"])]
            print("Estaciones locales INTA", json.dumps(near, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("folder", type=Path)
    p.add_argument("--observations", action="store_true")
    p.add_argument("--cutoff", default="2026-10-14T18:57:00-03:00")
    args = p.parse_args()
    observations(args.folder, args.cutoff) if args.observations else probe(args.folder)
