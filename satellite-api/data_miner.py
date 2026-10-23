"""Orquestador de datos de VitiAlert.

Recolecta e importa meteorologia, solicita el refresco satelital y exporta el dataset
horario. El entrenamiento de humedad a 24 h se ejecuta en un pipeline independiente.
"""

from __future__ import annotations

import argparse
import os
import tempfile
import time
from collections.abc import Callable
from datetime import date, timedelta
from pathlib import Path

import requests

from weather_collector import build_session, collect_weather, write_weather_csv

DEFAULT_LATITUDE = -31.6550
DEFAULT_LONGITUDE = -68.5750


def _base_url(value: str | None) -> str:
    url = (value or os.getenv("BACKEND_BASE_URL") or "http://localhost:8080").rstrip("/")
    if not url.startswith(("http://", "https://")):
        raise ValueError("BACKEND_BASE_URL debe comenzar con http:// o https://")
    return url


def _headers() -> dict[str, str]:
    api_key = os.getenv("VITIALERT_API_KEY", "").strip()
    return {"X-API-Key": api_key} if api_key else {}


def import_weather(csv_path: Path, source_name: str, backend_url: str,
                   session: requests.Session) -> dict:
    with csv_path.open("rb") as handle:
        response = session.post(
            f"{backend_url}/api/weather/import",
            params={"source": source_name},
            files={"file": (csv_path.name, handle, "text/csv")},
            headers=_headers(), timeout=90,
        )
    response.raise_for_status()
    return response.json()


def refresh_satellite(backend_url: str, session: requests.Session) -> dict:
    response = session.post(
        f"{backend_url}/api/satellite/refresh", headers=_headers(), timeout=180
    )
    response.raise_for_status()
    return response.json()


def refresh_satellite_with_retry(
    backend_url: str,
    session: requests.Session,
    *,
    attempts: int = 2,
    delay_seconds: float = 10,
    sleeper: Callable[[float], None] = time.sleep,
) -> dict:
    """Refresca satelite y no permite que una falla funcional quede en verde.

    El endpoint es *fail-soft* y responde HTTP 200 aunque VitiAI no este disponible, porque
    una falla satelital nunca debe interrumpir la telemetria IoT. Para el proceso batch eso
    no alcanza: si ``unavailable_nodes`` es mayor que cero se reintenta y, al agotarse los
    intentos, se falla el workflow para que GitHub Actions lo haga visible.
    """
    if attempts < 1:
        raise ValueError("attempts debe ser mayor o igual a 1")
    if delay_seconds < 0:
        raise ValueError("delay_seconds no puede ser negativo")

    result: dict = {}
    for attempt in range(1, attempts + 1):
        result = refresh_satellite(backend_url, session)
        unavailable = int(result.get("unavailable_nodes", 0))
        if unavailable == 0:
            return result
        if attempt < attempts:
            print(
                "VitiAI no respondio para "
                f"{unavailable} nodo(s); reintento {attempt + 1}/{attempts} "
                f"en {delay_seconds:g} s."
            )
            sleeper(delay_seconds)

    raise RuntimeError(
        "El refresco satelital termino sin datos despues de "
        f"{attempts} intento(s): {result}"
    )


def sync(args: argparse.Namespace) -> None:
    client = build_session()
    backend = _base_url(args.backend_url)
    today = date.today()
    archive_day = today - timedelta(days=args.archive_lag_days)
    recent_start = today - timedelta(days=args.recent_days)

    health = client.get(f"{backend}/health", timeout=30)
    health.raise_for_status()

    with tempfile.TemporaryDirectory(prefix="vitialert-weather-") as temporary:
        folder = Path(temporary)
        consolidated = collect_weather(
            archive_day, archive_day, args.latitude, args.longitude,
            source="archive", session=client,
        )
        archive_file = write_weather_csv(consolidated, folder / "weather_era5.csv")
        archive_result = import_weather(archive_file, "OPEN_METEO_ERA5", backend, client)

        recent = collect_weather(
            recent_start, today, args.latitude, args.longitude,
            source="forecast", session=client,
        )
        recent_file = write_weather_csv(recent, folder / "weather_recent.csv")
        recent_result = import_weather(recent_file, "OPEN_METEO_FORECAST", backend, client)

    satellite_result = refresh_satellite_with_retry(
        backend,
        client,
        attempts=args.satellite_attempts,
        delay_seconds=args.satellite_retry_delay_seconds,
    )
    print("Sincronizacion completa:", {
        "era5": archive_result, "recent": recent_result, "satellite": satellite_result,
    })


def weather(args: argparse.Namespace) -> None:
    rows = collect_weather(
        args.start, args.end, args.latitude, args.longitude, source=args.source
    )
    path = write_weather_csv(rows, args.output)
    print(f"{len(rows)} dias guardados en {path.resolve()}")


def dataset(args: argparse.Namespace) -> None:
    backend = _base_url(args.backend_url)
    client = build_session()
    response = client.get(
        f"{backend}/api/dataset/export",
        params={"nodeId": args.node_id, "from": args.start, "to": args.end},
        headers=_headers(), timeout=180,
    )
    response.raise_for_status()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(response.content)
    print(f"Dataset guardado en {output.resolve()}")


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="Pipeline de datos de VitiAlert")
    commands = root.add_subparsers(dest="command", required=True)
    location = argparse.ArgumentParser(add_help=False)
    location.add_argument(
        "--latitude", type=float,
        default=float(os.getenv("VITIALERT_LATITUDE", DEFAULT_LATITUDE)),
    )
    location.add_argument(
        "--longitude", type=float,
        default=float(os.getenv("VITIALERT_LONGITUDE", DEFAULT_LONGITUDE)),
    )

    weather_parser = commands.add_parser("weather", parents=[location])
    weather_parser.add_argument("--from", dest="start", required=True, type=date.fromisoformat)
    weather_parser.add_argument("--to", dest="end", required=True, type=date.fromisoformat)
    weather_parser.add_argument("--source", choices=("archive", "forecast"), default="archive")
    weather_parser.add_argument("--output", default="dataset_meteorologico.csv")
    weather_parser.set_defaults(func=weather)

    sync_parser = commands.add_parser("sync", parents=[location])
    sync_parser.add_argument("--backend-url")
    sync_parser.add_argument("--archive-lag-days", type=int, default=7)
    sync_parser.add_argument("--recent-days", type=int, default=5)
    sync_parser.add_argument("--satellite-attempts", type=int, default=2)
    sync_parser.add_argument("--satellite-retry-delay-seconds", type=float, default=10)
    sync_parser.set_defaults(func=sync)

    dataset_parser = commands.add_parser("dataset")
    dataset_parser.add_argument("--backend-url")
    dataset_parser.add_argument("--node-id", required=True)
    dataset_parser.add_argument("--from", dest="start", required=True)
    dataset_parser.add_argument("--to", dest="end", required=True)
    dataset_parser.add_argument("--output", default="vitialert_dataset.csv")
    dataset_parser.set_defaults(func=dataset)
    return root


if __name__ == "__main__":
    parsed = parser().parse_args()
    parsed.func(parsed)


