"""Revision local de fuentes, enlaces y patrones de credenciales antes de publicar."""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path
from urllib.parse import unquote


IGNORED_DIRS = {'.git', '.venv', 'venv', 'node_modules', '__pycache__',
                '.pytest_cache', '.mypy_cache', '.ruff_cache', 'target',
                'outputs', 'snapshots', 'data', 'repeticiones', '.idea', '.vscode'}
BLOCKED_EXTENSIONS = {'.pyc', '.pyo', '.jar', '.class', '.bin', '.elf', '.dump',
                      '.backup', '.joblib', '.pkl', '.pickle', '.npz', '.nc', '.h5',
                      '.csv', '.parquet', '.jsonl', '.zip', '.rar', '.7z', '.log',
                      '.pptx', '.pdf', '.docx', '.xlsx', '.pem', '.key', '.p12', '.pfx'}
SECRET_PATTERNS = (
    r'postgres(?:ql)?://[^\s:@/]+:[^\s@]+@',
    r'jdbc:postgresql://[^\s]+[?&]password=[^\s"\'}]+',
    r'\b(?:ghp_|github_pat_|sk-proj-)[A-Za-z0-9_]{20,}',
    r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',
    r'(?i)\b(?:password|api_key|client_secret)\s*[=:]\s*["\'][A-Za-z0-9+/=_-]{24,}["\']',
)


def verify(root: Path) -> tuple[int, int]:
    errors = []
    files, links = 0, 0
    for path in sorted(root.rglob('*')):
        relative = path.relative_to(root)
        if not path.is_file() or set(relative.parts[:-1]) & IGNORED_DIRS:
            continue
        if any(part.startswith('resultados_') for part in relative.parts[:-1]):
            continue
        files += 1
        if path.name == 'secrets.h' or (path.name.startswith('.env') and path.name != '.env.example'):
            errors.append(f'Configuracion privada: {relative.as_posix()}')
        if path.suffix.lower() in BLOCKED_EXTENSIONS:
            errors.append(f'Archivo no publicable en esta carpeta de codigo: {relative.as_posix()}')
            continue
        try:
            text = path.read_text(encoding='utf-8-sig')
        except UnicodeDecodeError:
            errors.append(f'Archivo binario inesperado: {relative.as_posix()}')
            continue
        if path.suffix == '.py':
            try:
                ast.parse(text, filename=str(relative))
            except SyntaxError as exc:
                errors.append(f'Error de Python en {relative.as_posix()}:{exc.lineno}')
        for number, line in enumerate(text.splitlines(), 1):
            if any(re.search(pattern, line) for pattern in SECRET_PATTERNS):
                # No imprimir el contenido que podria contener una credencial.
                errors.append(f'Posible credencial en {relative.as_posix()}:{number}')
            if re.search(r'[A-Z]:[\\/](?:Users|Educacion)[\\/]', line):
                errors.append(f'Ruta de equipo local en {relative.as_posix()}:{number}')
        if path.suffix == '.md':
            for target in re.findall(r'!?\[[^\]]*\]\(([^)]+)\)', text):
                target = target.strip().strip('<>')
                if re.match(r'^[a-zA-Z][a-zA-Z0-9+.-]*:', target) or target.startswith('#'):
                    continue
                destination = unquote(target.split('#', 1)[0])
                if not (path.parent / destination).exists():
                    errors.append(f'Enlace local inexistente en {relative.as_posix()}: {destination}')
                links += 1
    if errors:
        raise ValueError('\n'.join(errors))
    return files, links


if __name__ == '__main__':
    try:
        count, links = verify(Path(__file__).resolve().parents[1])
    except ValueError as exc:
        print(exc, file=sys.stderr)
        raise SystemExit(1)
    print(f'Revision completada: {count} archivos y {links} enlaces locales.')
    print('Sin archivos privados ni coincidencias con los patrones examinados.')
    print('Completar con revision manual de los archivos a publicar.')
