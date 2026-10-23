import csv
from pathlib import Path

from weather_collector import CSV_COLUMNS, normalize_response, write_weather_csv


def test_normaliza_contrato_y_maximo_diario_de_vpd(tmp_path: Path):
    payload = {
        "daily": {
            "time": ["2026-09-01"],
            "temperature_2m_max": [28.0],
            "temperature_2m_mean": [19.0],
            "relative_humidity_2m_mean": [40],
            "relative_humidity_2m_min": [20],
            "wind_speed_10m_mean": [8.0],
            "wind_speed_10m_max": [20.0],
            "precipitation_sum": [0.0],
            "shortwave_radiation_sum": [21.5],
            "et0_fao_evapotranspiration": [4.2],
        },
        "hourly": {
            "time": ["2026-09-01T00:00", "2026-09-01T01:00"],
            "vapour_pressure_deficit": [0.5, 1.8],
        },
    }

    rows = normalize_response(payload)

    assert rows[0]["vpd_max_kpa"] == 1.8
    assert rows[0]["precipitacion_mm"] == 0.0
    output = write_weather_csv(rows, tmp_path / "weather.csv")
    with output.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        assert tuple(reader.fieldnames or []) == CSV_COLUMNS
        assert next(reader)["et0_mm"] == "4.2"


def test_faltantes_se_escriben_vacios(tmp_path: Path):
    payload = {"daily": {"time": ["2026-09-01"]}, "hourly": {}}
    output = write_weather_csv(normalize_response(payload), tmp_path / "weather.csv")
    row = list(csv.DictReader(output.open(encoding="utf-8")))[0]
    assert row["temp_max_c"] == ""
    assert row["vpd_max_kpa"] == ""
