"""Sella los archivos de la entrega y crea un ZIP para el equipo."""
import hashlib
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def included(p):
    relative = p.relative_to(ROOT)
    return (p.is_file() and "__pycache__" not in relative.parts
            and relative.parts[:2] != ("verificacion", "pdf")
            and p.name != "SHA256_ENTREGA.json" and p.suffix != ".pyc")


def main():
    output = ROOT.with_suffix(".zip")
    if output.exists():
        raise FileExistsError("La entrega comprimida ya existe; no se sobrescribe.")
    files = sorted(p for p in ROOT.rglob("*") if included(p))
    manifest = {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    (ROOT / "SHA256_ENTREGA.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for p in files + [ROOT / "SHA256_ENTREGA.json"]:
            archive.write(p, arcname=(Path(ROOT.name) / p.relative_to(ROOT)).as_posix())
    with zipfile.ZipFile(output) as archive:
        assert archive.testzip() is None
        for name, expected in manifest.items():
            assert hashlib.sha256(archive.read(ROOT.name + "/" + name)).hexdigest() == expected
    print(json.dumps(dict(file=str(output), files=len(manifest) + 1, bytes=output.stat().st_size,
                         sha256=hashlib.sha256(output.read_bytes()).hexdigest(), zip_crc_verified=True,
                         content_hashes_verified=True), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
