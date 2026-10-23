"""Recoleccion meteorologica de VitiAlert mediante la API de Open-Meteo.

Produccion no raspa HTML: consume un contrato JSON documentado y estable. Asi se evitan
selectores CSS fragiles, cambios visuales del sitio y etiquetas fabricadas con reglas
heuristicas. La salida coincide con el contrato de importacion del backend Java.
"""

from __future__ import annotations

import csv
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any, Iterable

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
TIMEZONE = "America/Argentina/San_Juan"

CSV_COLUMNS = (
    "fecha", "temp_max_c", "temp_media_c", "humedad_media_pct",
    "humedad_min_pct", "velocidad_viento_media_kmh",
    "velocidad_viento_max_kmh", "precipitacion_mm",
    "radiacion_solar_mj_m2", "et0_mm", "vpd_max_kpa",
)

DAILY_VARIABLES = (
    "temperature_2m_max", "temperature_2m_mean",
    "relative_humidity_2m_mean", "relative_humidity_2m_min",
    "wind_speed_10m_mean", "wind_speed_10m_max", "precipitation_sum",
    "shortwave_radiation_sum", "et0_fao_evapotranspiration",
)


def build_session() -> requests.Session:
    """Cliente HTTP con reintentos acotados para errores transitorios."""
    retry = Retry(
        total=4, connect=4, read=4, backoff_factor=0.8,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET", "POST"}),
    )
    session = requests.Session()
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update({"User-Agent": "VitiAlert-DataMiner/1.0"})
    return session


def collect_weather(
    start_date: date,
    end_date: date,
    latitude: float,
    longitude: float,
    *,
    source: str = "archive",
    timezone: str = TIMEZONE,
    timeout_seconds: int = 60,
    session: requests.Session | None = None,
) -> list[dict[str, Any]]:
    """Descarga meteorologia diaria para un punto y la normaliza.

    ``archive`` usa ERA5-Seamless consolidado; ``forecast`` cubre dias recientes. El VPD
    se solicita por hora y se agrega como maximo diario.
    """
    if start_date > end_date:
        raise ValueError("start_date debe ser anterior o igual a end_date")
    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        raise ValueError("Coordenadas fuera de rango")
    if source not in {"archive", "forecast"}:
        raise ValueError("source debe ser 'archive' o 'forecast'")

    endpoint = ARCHIVE_URL if source == "archive" else FORECAST_URL
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "daily": ",".join(DAILY_VARIABLES),
        "hourly": "vapour_pressure_deficit",
        "timezone": timezone,
        "wind_speed_unit": "kmh",
        "precipitation_unit": "mm",
    }
    if source == "archive":
        params["models"] = "era5_seamless"

    client = session or build_session()
    response = client.get(endpoint, params=params, timeout=timeout_seconds)
    response.raise_for_status()
    return normalize_response(response.json())


def normalize_response(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Convierte una respuesta Open-Meteo al contrato estable del backend."""
    daily = payload.get("daily") or {}
    days = daily.get("time") or []
    if not days:
        raise ValueError("Open-Meteo respondio sin datos diarios")

    vpd_by_day: dict[str, list[float]] = defaultdict(list)
    hourly = payload.get("hourly") or {}
    for timestamp, value in zip(
        hourly.get("time") or [], hourly.get("vapour_pressure_deficit") or [], strict=False
    ):
        if value is not None:
            vpd_by_day[str(timestamp)[:10]].append(float(value))

    mapping = {
        "temp_max_c": "temperature_2m_max",
        "temp_media_c": "temperature_2m_mean",
        "humedad_media_pct": "relative_humidity_2m_mean",
        "humedad_min_pct": "relative_humidity_2m_min",
        "velocidad_viento_media_kmh": "wind_speed_10m_mean",
        "velocidad_viento_max_kmh": "wind_speed_10m_max",
        "precipitacion_mm": "precipitation_sum",
        "radiacion_solar_mj_m2": "shortwave_radiation_sum",
        "et0_mm": "et0_fao_evapotranspiration",
    }

    rows: list[dict[str, Any]] = []
    for index, day in enumerate(days):
        row: dict[str, Any] = {"fecha": day}
        for output_name, api_name in mapping.items():
            values = daily.get(api_name) or []
            row[output_name] = values[index] if index < len(values) else None
        daily_vpd = vpd_by_day.get(str(day), [])
        row["vpd_max_kpa"] = max(daily_vpd) if daily_vpd else None
        rows.append(row)
    return rows


def write_weather_csv(rows: Iterable[dict[str, Any]], destination: str | Path) -> Path:
    """Escribe UTF-8 y deja los faltantes vacios, nunca en cero."""
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: _csv_value(row.get(column)) for column in CSV_COLUMNS})
    return path


def _csv_value(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.6f}".rstrip("0").rstrip(".")
    return value


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Descarga meteorologia diaria de Open-Meteo")
    parser.add_argument("--from", dest="start", required=True, type=date.fromisoformat)
    parser.add_argument("--to", dest="end", required=True, type=date.fromisoformat)
    parser.add_argument("--latitude", required=True, type=float)
    parser.add_argument("--longitude", required=True, type=float)
    parser.add_argument("--source", choices=("archive", "forecast"), default="archive")
    parser.add_argument("--output", default="dataset_meteorologico.csv")
    args = parser.parse_args()
    result = collect_weather(args.start, args.end, args.latitude, args.longitude, source=args.source)
    output = write_weather_csv(result, args.output)
    print(f"{len(result)} dias guardados en {output.resolve()}")


