"""Comprueba el manifiesto de archivos sin conectarse a servicios ni reentrenar."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    manifest = json.loads((ROOT / "SHA256_ENTREGA.json").read_text(encoding="utf-8"))
    for relative, expected in manifest.items():
        if Path(relative).is_absolute() or ".." in Path(relative).parts:
            raise ValueError("Ruta inesperada en el manifiesto.")
        path = ROOT / relative
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError(f"Falta un archivo o cambió su contenido: {relative}")
    print(f"Integridad correcta: {len(manifest)} archivos verificados.")


if __name__ == "__main__":
    main()
