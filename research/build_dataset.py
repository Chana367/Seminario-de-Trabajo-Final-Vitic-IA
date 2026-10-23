"""Dataset de investigacion: realidad intacta, simulacion declarada y evaluacion temporal.

No escribe en PostgreSQL ni llama a endpoints de ingesta. Requiere numpy y pandas.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

TZ = "America/Argentina/Buenos_Aires"
START = pd.Timestamp("2026-10-01T00:00:00-03:00").tz_convert(TZ)
NEWS_URL = "https://www.sanjuan8.com/san-juan/se-cumplio-el-pronostico-llovizna-distintos-sectores-san-juan-n1604403"
FEATURES = ["soil_moisture", "soil_lag_6h", "soil_lag_24h", "soil_mean_24h",
            "temperature_c", "relative_humidity_pct", "wind_kmh", "rain_24h_mm",
            "et0_24h_mm", "irrigation_24h_l", "hour_sin", "hour_cos"]


@dataclass(frozen=True)
class Assumptions:
    seed: int = 20261001
    minutes: int = 5
    initial_sensor_pct: float = 35.0
    storage_capacity_mm: float = 70.0
    field_capacity_fraction: float = 0.65
    soil_area_m2: float = 0.25
    crop_coefficient_assumed: float = 0.7
    rainfall_capture_fraction: float = 0.8
    irrigation_efficiency: float = 0.9
    drainage_fraction_per_hour: float = 0.08
    flow_open_l_min: float = 0.4
    soil_irrigation_threshold_pct: float = 30.0
    wind_close_kmh: float = 45.0
    wind_10m_to_sensor_factor: float = 0.65
    sensor_soil_noise_sd_pct: float = 0.6
    sensor_raw_dry: int = 3317
    sensor_raw_water: int = 1104


def save_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")


def weather(path: Path) -> pd.DataFrame:
    raw = json.loads(path.read_text(encoding="utf-8"))
    h = pd.DataFrame(raw["hourly"])
    h["time"] = pd.to_datetime(h["time"], utc=True)
    return h.set_index("time").sort_index()


def station(folder, cutoff):
    path = folder / "iem_sanu.csv"
    if not path.exists():
        return pd.DataFrame(columns=["time", "day", "rain_code"])
    s = pd.read_csv(path, na_values=["M"])
    if not {"station", "valid", "metar", "wxcodes"}.issubset(s):
        raise ValueError("El archivo de estacion no tiene el contrato METAR esperado")
    s["time"] = pd.to_datetime(s.valid, utc=True)
    s = s[(s.time >= START.tz_convert("UTC")) & (s.time <= cutoff)].copy()
    s["day"] = s.time.dt.tz_convert(TZ).dt.strftime("%Y-%m-%d")
    s["rain_code"] = s.wxcodes.fillna("").str.contains("RA|DZ", regex=True)
    # IEM: p01i no esta disponible fuera de EEUU. Los ceros NO son evidencia de sequedad.
    return s


def inta_context(folder, out, cutoff):
    """Estacion vecina, no observacion de parcela ni reemplazo automatico del forzado.

    SIGA etiqueta Z[UTC] pero la interfaz elimina ese sufijo. Conservamos el reloj
    publicado, sin inventar una conversion. Las fechas diarias son etiquetas del proveedor.
    """
    root = folder / "inta_catalog"
    daily_path, hourly_path = root / "pocito_daily.json", root / "pocito_hourly.json"
    report = {"station_id": 444, "station_name": "Pocito - EEA San Juan",
              "latitude": -31.66, "longitude": -68.59, "source": "https://siga.inta.gob.ar/",
              "timestamp_basis": "UNRESOLVED_PROVIDER_Z_UTC_STRIPPED_BY_WEB_UI",
              "rainfall_quality": "PUBLISHED_VALUES_NOT_INDEPENDENTLY_INSTRUMENT_QA_VALIDATED",
              "rain_used_as_plot_truth": False, "used_to_overwrite_ifs": False}
    if not daily_path.exists() or not hourly_path.exists():
        report["status"] = "UNAVAILABLE"
        save_json(out / "inta_station_audit.json", report)
        return pd.DataFrame(), report
    daily = pd.DataFrame(json.loads(daily_path.read_text(encoding="utf-8")))
    hourly = pd.DataFrame(json.loads(hourly_path.read_text(encoding="utf-8")))
    if daily.empty or hourly.empty:
        report["status"] = "EMPTY_RESPONSE"
        save_json(out / "inta_station_audit.json", report)
        return pd.DataFrame(), report
    for frame in (daily, hourly):
        if not {"fechaHora", "idEstacion", "precDiaCrono"}.issubset(frame):
            raise ValueError("Respuesta INTA sin contrato esperado")
        if not frame.idEstacion.eq(444).all():
            raise ValueError("Respuesta INTA contiene otra estacion")
        frame["provider_time_label"] = frame.fechaHora.str.replace("Z[UTC]", "", regex=False)
        frame["provider_date_label"] = frame.provider_time_label.str[:10]
    # Conservador frente a ambas interpretaciones de reloj: nunca mas alla del corte local.
    limit = cutoff.tz_convert(TZ).strftime("%Y-%m-%dT%H:%M:%S")
    hourly = hourly[(hourly.provider_time_label >= "2026-10-01T00:00:00") & (hourly.provider_time_label <= limit)].copy()
    daily = daily[(daily.provider_date_label >= "2026-10-01") & (daily.provider_date_label < limit[:10])].copy()
    report["hourly_rows_before_dedup"] = len(hourly)
    report["duplicate_timestamps"] = int(hourly.provider_time_label.duplicated().sum())
    conflicts = hourly.groupby("provider_time_label").precDiaCrono.nunique(dropna=False)
    report["conflicting_rain_timestamps"] = int(conflicts.gt(1).sum())
    # No sumar duplicados: una lectura fisica por reloj publicado; conflictos no se resuelven inventando.
    hourly = hourly.drop_duplicates("provider_time_label").sort_values("provider_time_label")
    hourly.loc[hourly.provider_time_label.isin(conflicts[conflicts.gt(1)].index), "precDiaCrono"] = np.nan
    for frame in (daily, hourly):
        frame["origin"] = "REAL_INTA_NEARBY_STATION_NOT_ESP32_NOT_PLOT"
        frame["timestamp_basis"] = report["timestamp_basis"]
    hourly.to_csv(out / "inta_station_records_provider_clock.csv", index=False)
    daily.to_csv(out / "inta_station_daily_provider_dates.csv", index=False)
    report.update(status="DOWNLOADED_WITH_LIMITATIONS", daily_records=len(daily),
                  unique_subhourly_records=len(hourly),
                  rain_positive_records=int(hourly.precDiaCrono.gt(0).sum()),
                  last_provider_time_label=str(hourly.provider_time_label.max()),
                  distance_km=round(2 * 6371 * math.asin(math.sqrt(
                      math.sin(math.radians(-31.66 + 31.655) / 2)**2 +
                      math.cos(math.radians(-31.655)) * math.cos(math.radians(-31.66)) *
                      math.sin(math.radians(-68.59 + 68.575) / 2)**2)), 2))
    save_json(out / "inta_station_audit.json", report)
    counts = hourly.groupby("provider_date_label").size()
    contrast = daily[["provider_date_label", "precDiaCrono", "precDiaPlub"]].copy()
    contrast["inta_registros_unicos_reloj_proveedor"] = contrast.provider_date_label.map(counts)
    return contrast, report


def rain_audit(ifs, era5, s, cutoff):
    rows = []
    for day in pd.date_range(START.normalize(), cutoff.tz_convert(TZ).normalize(), freq="D"):
        rec = {"fecha_local": day.strftime("%Y-%m-%d"), "lluvia_medida_parcela_mm": None,
               "certeza_lluvia_parcela": "NO_VERIFICADA_CON_PLUVIOMETRO",
               "dia_completo": day + pd.Timedelta(days=1) <= cutoff,
               "fuente_cantidad": "OPEN_METEO_ECMWF_IFS_ANALISIS_NO_PLUVIOMETRO"}
        for name, h in (("ifs", ifs), ("era5", era5)):
            valid = h[h.index <= cutoff]
            # El acumulado de las 00:00 corresponde a la hora anterior, no al nuevo dia.
            d = (valid.index - pd.Timedelta(hours=1)).tz_convert(TZ).strftime("%Y-%m-%d")
            rain = valid.loc[d == rec["fecha_local"], "precipitation"]
            rec[name + "_horas"] = int(rain.notna().sum())
            rec[name + "_mm_estimados"] = round(float(rain.sum(min_count=1)), 3) if rain.notna().any() else None
        rec["discrepancia_modelos_mm"] = round(rec["era5_mm_estimados"] - rec["ifs_mm_estimados"], 3) if rec["era5_horas"] == rec["ifs_horas"] == 24 else None
        reports = s[s.day == rec["fecha_local"]]
        rec["sanu_reportes"] = len(reports)
        rec["sanu_reportes_RA_DZ"] = int(reports.rain_code.sum())
        rec["sanu_precipitacion_mm"] = None
        rec["evidencia_presencia"] = "MODELO_SOLAMENTE_NO_CONFIRMA_PARCELA"
        rec["fuente_evidencia"] = "https://open-meteo.com/en/docs/historical-weather-api"
        if rec["fecha_local"] == "2026-10-08":
            rec["evidencia_presencia"] = "LLOVIZNA_REPORTADA_EN_POCITO_SIN_CANTIDAD"
            rec["fuente_evidencia"] = NEWS_URL
        if rec["sanu_reportes_RA_DZ"]:
            rec["evidencia_presencia"] = "LLUVIA_O_LLOVIZNA_METAR_SANU_NO_PRUEBA_EN_PARCELA"
            rec["fuente_evidencia"] = "https://mesonet.agron.iastate.edu/request/download.phtml"
        rows.append(rec)
    return pd.DataFrame(rows)


def simulate(forcing, cutoff, a: Assumptions):
    cutoff = pd.Timestamp(cutoff).tz_convert("UTC")
    if a.minutes <= 0 or 60 % a.minutes:
        raise ValueError("La cadencia debe dividir exactamente 60 minutos")
    grid = pd.date_range(START.tz_convert("UTC"), cutoff.floor(f"{a.minutes}min"), freq=f"{a.minutes}min")
    rng = np.random.default_rng(a.seed)
    water = a.storage_capacity_mm * a.initial_sensor_pct / 100
    volume = 0.0
    noise_soil = 0.0
    rows = []
    for pos, t in enumerate(grid):
        # Distribucion uniforme dentro de una hora: SUPUESTO, no dato observado de 5 min.
        hour = t.ceil("h")
        complete = hour in forcing.index and hour <= cutoff
        w = forcing.loc[hour] if complete else None
        complete = complete and all(pd.notna(w[k]) for k in ["precipitation", "et0_fao_evapotranspiration", "temperature_2m", "relative_humidity_2m", "wind_speed_10m"])
        noise_soil = 0.75 * noise_soil + rng.normal(0, a.sensor_soil_noise_sd_pct * math.sqrt(1 - .75 ** 2))
        temp_noise, rh_noise, wind_noise = rng.normal(0, .15), rng.normal(0, .8), rng.normal(0, .15)
        item = {"timestamp": t.isoformat(), "timestamp_local": t.tz_convert(TZ).isoformat(),
                "node_id": "SIM_1", "origin": "SEMISYNTHETIC_NOT_MEASURED",
                "weather_source": "OPEN_METEO_ECMWF_IFS_ANALYSIS", "soil_source": "ASSUMED_WATER_BALANCE_NOT_CALIBRATED",
                "rain_timing_source": "MODEL_HOURLY_UNIFORM_DISAGGREGATION_NOT_5MIN_OBSERVATION",
                "as_of_cutoff": cutoff.isoformat(), "ndvi_mean": None, "ndmi_mean": None,
                "satellite_source": "NOT_SIMULATED_NO_HISTORICAL_SERIES",
                "quality_flag": "SIMULATED" if complete else "SIMULATED_INCOMPLETE_FORCING"}
        if not complete:
            # No se usa la hora 19:00 para completar 18:05--18:55 en el corte 18:57.
            item.update(soil_moisture_pct=None, temperature_c=None, relative_humidity_pct=None,
                        wind_kmh=None, rain_mm_interval=None, et0_mm_interval=None,
                        flow_l_min=None, volume_total_l=round(volume, 6), irrigation_l_interval=None,
                        valve_open_interval=None, soil_raw=None, water_balance_residual_mm=None)
            rows.append(item)
            continue
        wind = max(0.0, float(w.wind_speed_10m) * a.wind_10m_to_sensor_factor + wind_noise)
        before = water
        open_ = water / a.storage_capacity_mm * 100 < a.soil_irrigation_threshold_pct and wind < a.wind_close_kmh
        # La primera fila es condicion inicial, no una acumulacion previa al inicio.
        dt = a.minutes if pos else 0
        rain = max(0., float(w.precipitation)) * dt / 60
        et0 = max(0., float(w.et0_fao_evapotranspiration)) * dt / 60
        liters = a.flow_open_l_min * dt if open_ else 0.
        irrig_mm = liters / a.soil_area_m2 * a.irrigation_efficiency
        added = rain * a.rainfall_capture_fraction + irrig_mm
        et = min(before + added, a.crop_coefficient_assumed * et0)
        after_et = before + added - et
        drainage = max(0., after_et - a.field_capacity_fraction * a.storage_capacity_mm) * a.drainage_fraction_per_hour * dt / 60
        uncapped = after_et - drainage
        overflow = max(0., uncapped - a.storage_capacity_mm)
        water = min(a.storage_capacity_mm, max(0., uncapped))
        volume += liters
        sensor = float(np.clip(water / a.storage_capacity_mm * 100 + noise_soil, 0, 100))
        raw = int(round(a.sensor_raw_dry - sensor / 100 * (a.sensor_raw_dry - a.sensor_raw_water)))
        # Arduino map() usa division entera. El porcentaje debe concordar con el ADC.
        reported_pct = int((raw - a.sensor_raw_dry) * 100 / (a.sensor_raw_water - a.sensor_raw_dry))
        item.update(soil_moisture_pct=reported_pct, soil_storage_mm=round(water, 8),
                    soil_raw=raw, temperature_c=round(float(w.temperature_2m) + temp_noise, 1),
                    relative_humidity_pct=round(float(np.clip(float(w.relative_humidity_2m) + rh_noise, 0, 100)), 1),
                    wind_kmh=round(wind, 3), rain_mm_interval=rain, et0_mm_interval=et0,
                    flow_l_min=a.flow_open_l_min if open_ and dt else 0., volume_total_l=round(volume, 6),
                    irrigation_l_interval=liters, valve_open_interval=bool(open_ and dt),
                    drainage_mm_interval=drainage, runoff_mm_interval=overflow,
                    actual_et_mm_interval=et, effective_rain_mm_interval=rain * a.rainfall_capture_fraction,
                    effective_irrigation_mm_interval=irrig_mm,
                    water_balance_residual_mm=water - (before + added - et - drainage - overflow))
        rows.append(item)
    return pd.DataFrame(rows)


def add_features(h, forcing, cutoff, origin):
    h = h.copy()
    for hours in (6, 24):
        h[f"soil_lag_{hours}h"] = h.soil_moisture.reindex(h.index - pd.Timedelta(hours=hours)).to_numpy()
    h["soil_mean_24h"] = h.soil_moisture.rolling("24h", min_periods=24).mean()
    h["temperature_c"] = forcing.temperature_2m.reindex(h.index)
    h["relative_humidity_pct"] = forcing.relative_humidity_2m.reindex(h.index)
    h["wind_kmh"] = forcing.wind_speed_10m.reindex(h.index)
    h["rain_24h_mm"] = forcing.precipitation.reindex(h.index).rolling("24h", min_periods=24).sum()
    h["et0_24h_mm"] = forcing.et0_fao_evapotranspiration.reindex(h.index).rolling("24h", min_periods=24).sum()
    h["irrigation_24h_l"] = h.irrigation_l.rolling("24h", min_periods=24).sum()
    local = h.index.tz_convert(TZ)
    h["hour_sin"] = np.sin(local.hour * 2 * np.pi / 24)
    h["hour_cos"] = np.cos(local.hour * 2 * np.pi / 24)
    h["target_timestamp"] = h.index + pd.Timedelta(hours=24)
    h["soil_moisture_t_plus_24h"] = h.soil_moisture.reindex(h.target_timestamp).to_numpy()
    h.loc[h.target_timestamp > cutoff, "soil_moisture_t_plus_24h"] = np.nan
    h["origin"] = origin
    h["target_origin"] = "REAL_SENSOR_HOURLY_MEAN" if origin.startswith("REAL") else "SIMULATED_HOURLY_MEAN_NOT_GROUND_TRUTH"
    h["weather_origin"] = "IFS_ANALYSIS_HISTORICAL_CONTEXT_NOT_AS_ISSUED_FORECAST"
    h["timestamp_local"] = local.astype(str)
    h["as_of_cutoff"] = cutoff.isoformat()
    return h


def hourly_frames(sim, raw, forcing, cutoff, minutes):
    complete_grid = pd.date_range(START.tz_convert("UTC") + pd.Timedelta(hours=1), cutoff.floor("h"), freq="h")
    sx = sim.copy()
    sx.index = pd.to_datetime(sx.timestamp, utc=True)
    sx = sx[sx.index > START]
    sh = sx.resample("h", closed="right", label="right").agg(
        soil_moisture=("soil_moisture_pct", "mean"), sample_count=("soil_moisture_pct", "count"),
        irrigation_l=("irrigation_l_interval", lambda s: s.sum(min_count=60 // minutes)))
    sh.loc[sh.sample_count != 60 // minutes, "soil_moisture"] = np.nan
    sh = sh.reindex(complete_grid)
    r = raw.copy()
    r.index = pd.to_datetime(r.timestamp_received, format="mixed", utc=True)
    # Conservar el original. No se convierte MISSING del DHT en suelo faltante ni en cero.
    r["soil_usable"] = r.humedad_suelo_pct.where(r.humedad_suelo_pct.between(0, 100, inclusive="neither"))
    r["clock"] = r.index
    rh = r.resample("h", closed="right", label="right").agg(
        soil_moisture=("soil_usable", "mean"), sample_count=("soil_usable", "count"),
        first=("clock", "min"), last=("clock", "max"))
    rh["covered_minutes"] = (rh["last"] - rh["first"]).dt.total_seconds() / 60
    rh.loc[(rh.covered_minutes < 45) | (rh.sample_count < 6), "soil_moisture"] = np.nan
    # Los pulsos/volumen reales no son confiables aun: no inventar ceros de riego.
    rh["irrigation_l"] = np.nan
    rh = rh.drop(columns=["first", "last"]).reindex(complete_grid)
    return (add_features(sh, forcing, cutoff, "SEMISYNTHETIC_NOT_MEASURED"),
            add_features(rh, forcing, cutoff, "REAL_SENSOR_WITH_MODEL_WEATHER_CONTEXT"))


def metrics(y, prediction):
    residual = y - prediction
    return {"mae_percentage_points": float(np.abs(residual).mean()),
            "rmse_percentage_points": float(np.sqrt(np.mean(residual ** 2))), "n": len(y)}


def fit_ridge(frame):
    x = frame[FEATURES].to_numpy(float)
    mean, scale = x.mean(axis=0), x.std(axis=0)
    scale[scale == 0] = 1
    design = np.column_stack([np.ones(len(x)), (x - mean) / scale])
    penalty = np.eye(design.shape[1]) * 10.0
    penalty[0, 0] = 0
    weights = np.linalg.solve(design.T @ design + penalty, design.T @ frame.soil_moisture_t_plus_24h.to_numpy())
    return {"weights": weights, "mean": mean, "scale": scale, "features": np.array(FEATURES),
            "target_mean": np.array(frame.soil_moisture_t_plus_24h.mean())}


def predict(model, frame):
    if list(model["features"]) != FEATURES:
        raise ValueError("Contrato de features incompatible")
    z = (frame[FEATURES].to_numpy(float) - model["mean"]) / model["scale"]
    return np.clip(np.column_stack([np.ones(len(z)), z]) @ model["weights"], 0, 100)


def benchmark(h, cutoff, out, name):
    split = cutoff.floor("h") - pd.Timedelta(days=3)
    data = h.dropna(subset=FEATURES + ["soil_moisture_t_plus_24h"])
    train = data[data.target_timestamp < split]
    test = data[data.index >= split]
    result = {"dataset": name, "features": FEATURES, "split_feature_time_utc": split.isoformat(),
              "train_samples": len(train), "test_samples": len(test),
              "purge_hours": 24, "interpretation": "SIMULATION_BENCHMARK_NOT_FIELD_VALIDATION" if name == "semisynthetic" else "LIMITED_REAL_SENSOR_EVIDENCE"}
    # Evaluacion simple real aunque otras features (riego) esten ausentes.
    pairs = h.dropna(subset=["soil_moisture", "soil_moisture_t_plus_24h"])
    if len(pairs):
        result["persistence_all_available_pairs_descriptive_only"] = metrics(pairs.soil_moisture_t_plus_24h.to_numpy(), pairs.soil_moisture.to_numpy())
    if len(data) >= 48:
        # Modelo congelado al corte: nunca usa los targets de dias posteriores.
        frozen = fit_ridge(data)
        np.savez(out / f"model_{name}_cutoff_frozen.npz", **frozen)
        result["frozen_cutoff_model"] = {"training_samples": len(data),
                                        "max_target_time_utc": data.target_timestamp.max().isoformat(),
                                        "purpose": "COMPARE_ON_FUTURE_COMMON_HOLDOUT_NOT_ON_TRAINING_ROWS"}
    if len(train) < 48 or len(test) < 24:
        result.update(status="NOT_TRAINED_INSUFFICIENT_RELIABLE_DATA", reason="Se requieren >=48 horas de entrenamiento y >=24 de prueba, sin etiquetas futuras y con features disponibles.")
        return result
    model = fit_ridge(train)
    pred = predict(model, test)
    y = test.soil_moisture_t_plus_24h.to_numpy()
    result.update(status="TRAINED_OFFLINE_NOT_DEPLOYED", ridge=metrics(y, pred),
                  persistence=metrics(y, test.soil_moisture.to_numpy()),
                  train_mean_baseline=metrics(y, np.full(len(y), train.soil_moisture_t_plus_24h.mean())),
                  ridge_alpha_fixed_not_tuned_on_test=10.0,
                  max_train_target_time_utc=train.target_timestamp.max().isoformat(),
                  first_test_feature_time_utc=test.index.min().isoformat())
    np.savez(out / f"model_{name}_holdout_benchmark.npz", **model)
    predictions = pd.DataFrame({"timestamp": test.index, "target_timestamp": test.target_timestamp,
                                "target": y, "ridge": pred, "persistence": test.soil_moisture.to_numpy(),
                                "origin": test.origin.to_numpy()})
    predictions.to_csv(out / f"predictions_{name}.csv", index=False)
    return result


def build(folder: Path, out: Path, cutoff: str, freeze_from: Path | None = None):
    if out.exists() and any(out.iterdir()):
        raise FileExistsError("Salida existente: elegir otra carpeta para no alterar el corte congelado")
    out.mkdir(parents=True, exist_ok=True)
    cut = pd.Timestamp(cutoff)
    if cut.tz is None:
        raise ValueError("El corte debe indicar zona horaria")
    cut = cut.tz_convert("UTC")
    if cut <= START:
        raise ValueError("Corte anterior al inicio")
    if cut > pd.Timestamp.now(tz="UTC"):
        raise ValueError("No construir un dataset de observaciones futuras")
    a = Assumptions()
    forcing = weather(folder / "open_meteo_ecmwf_ifs.json")
    if freeze_from:
        old = pd.read_csv(freeze_from / "forcing_hourly.csv", index_col=0, parse_dates=True)
        old.index = pd.to_datetime(old.index, utc=True)
        forcing.loc[old.index.intersection(forcing.index), old.columns] = old.loc[old.index.intersection(forcing.index)]
    forcing = forcing[(forcing.index <= cut) & (forcing.index >= START.tz_convert("UTC"))]
    forcing.index.name = "hour_end_utc"
    forcing.to_csv(out / "forcing_hourly.csv")
    era5 = weather(folder / "open_meteo_era5.json")
    s = station(folder, cut)
    rain = rain_audit(forcing, era5, s, cut)
    inta, inta_report = inta_context(folder, out, cut)
    if not inta.empty:
        rain = rain.merge(inta.rename(columns={"provider_date_label": "fecha_local",
            "precDiaCrono": "inta_mm_publicados_fecha_proveedor",
            "precDiaPlub": "inta_mm_pluviometricos_publicados_fecha_proveedor"}), on="fecha_local", how="left")
    else:
        rain["inta_mm_publicados_fecha_proveedor"] = np.nan
        rain["inta_registros_unicos_reloj_proveedor"] = np.nan
    rain["inta_advertencia"] = "ESTACION_VECINA_RELOJ_Y_QA_SIN_CONFIRMAR_NO_PRUEBA_PARCELA"
    rain.to_csv(out / "rain_validation.csv", index=False)
    if not s.empty:
        s.to_csv(out / "station_context.csv", index=False)
    raw = pd.read_csv(folder / "telemetry_real.csv")
    raw_times = pd.to_datetime(raw.timestamp_received, format="mixed", utc=True)
    if ((raw_times < START) | (raw_times > cut)).any():
        raise ValueError("La exportacion contiene datos fuera del corte")
    raw["origin"] = "REAL_ESP32_MEASURED_UNMODIFIED"
    raw["sensor_environment"] = "OUTDOOR_WATER_CIRCULATES_USER_REPORTED_2026_10_14"
    raw.to_csv(out / "telemetry_real_labeled.csv", index=False)
    sim = simulate(forcing, cut, a)
    sim.to_csv(out / "telemetry_semisynthetic_5min.csv", index=False)
    sh, rh = hourly_frames(sim, raw, forcing, cut, a.minutes)
    sh.index.name = rh.index.name = "timestamp"
    sh.to_csv(out / "features_semisynthetic_hourly.csv")
    rh.to_csv(out / "features_real_hourly.csv")
    daily_real = raw.assign(day=raw_times.dt.tz_convert(TZ).dt.strftime("%Y-%m-%d")).groupby("day").agg(
        rows=("id", "size"), temperature_present=("temperatura_ambiente_c", "count"),
        humidity_present=("humedad_relativa_pct", "count"), soil_min=("humedad_suelo_pct", "min"),
        soil_max=("humedad_suelo_pct", "max"))
    daily_real.to_csv(out / "quality_daily_real.csv")
    bench = {name: benchmark(h, cut, out, name) for name, h in (("semisynthetic", sh), ("real", rh))}
    save_json(out / "model_metrics.json", bench)
    save_json(out / "assumptions.json", asdict(a))
    complete = sim[sim.soil_moisture_pct.notna()]
    max_residual = float(complete.water_balance_residual_mm.abs().max())
    assert max_residual < 1e-8, "Balance hidrico no cierra"
    assert (complete.flow_l_min > 0).equals(complete.valve_open_interval.astype(bool))
    assert complete.volume_total_l.diff().dropna().ge(0).all()
    assert complete.soil_moisture_pct.between(0, 100).all()
    assert pd.to_datetime(sim.timestamp, utc=True).max() <= cut
    for h in (sh, rh):
        assert h.loc[h.target_timestamp > cut, "soil_moisture_t_plus_24h"].isna().all()
    sources_manifest = json.loads((folder / "manifest_sources.json").read_text(encoding="utf-8"))
    # Una pagina HTML retornada con 200 no se acepta como evidencia instrumental.
    rejected = ["noaa_hourly_87311099999.csv: HTML AWS S3 Explorer, no observaciones"] if (folder / "noaa_hourly_87311099999.csv").exists() and b"<html" in (folder / "noaa_hourly_87311099999.csv").read_bytes()[:1000].lower() else []
    summary = {"cutoff_local": cut.tz_convert(TZ).isoformat(), "start_local": START.isoformat(),
               "real_records": len(raw), "real_quality_counts": {str(k): int(v) for k,v in raw.quality_flag.value_counts().items()},
               "real_temperature_missing": int(raw.temperatura_ambiente_c.isna().sum()),
               "real_flow_above_0_2_records": int((raw.caudal_l_min > .2).sum()),
               "latest_real_telemetry_local": raw_times.max().tz_convert(TZ).isoformat(),
               "simulated_records": len(sim), "simulated_missing_forcing_rows": int(sim.soil_moisture_pct.isna().sum()),
               "hourly_rows": len(sh), "simulation_target_pairs": int(sh.soil_moisture_t_plus_24h.notna().sum()),
               "real_target_pairs": int(rh.dropna(subset=["soil_moisture", "soil_moisture_t_plus_24h"]).shape[0]),
               "max_water_balance_residual_mm": max_residual,
               "satellite_measured_records": len(pd.read_csv(folder / "satellite_real.csv")),
               "rainfall_exact_plot_validation": "NOT_POSSIBLE_WITH_AVAILABLE_SOURCES",
               "station_rain_amount_used": False, "weather_model": "ECMWF_IFS_ANALYSIS",
               "no_5_minute_weather_observations_claimed": True,
               "production_database_modified": False, "model_deployed": False,
               "source_download_time_utc": sources_manifest["retrieved_at_utc"], "rejected_sources": rejected,
               "freeze_weather_from": str(freeze_from) if freeze_from else None}
    summary["inta_station_audit"] = inta_report
    if not s.empty:
        lat, lon = float(s.lat.iloc[0]), float(s.lon.iloc[0])
        phi1, phi2 = math.radians(-31.655), math.radians(lat)
        hav = math.sin((phi2 - phi1) / 2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(math.radians(lon + 68.575)/2)**2
        summary["station_distance_km"] = round(2 * 6371 * math.asin(math.sqrt(hav)), 2)
        st = s.drop_duplicates("time").set_index("time")
        joined = forcing.join(st[["tmpf", "relh", "sknt"]], how="inner")
        comparisons = {}
        for model_col, obs, name in (("temperature_2m", (joined.tmpf-32)*5/9, "temperature_c"),
                                     ("relative_humidity_2m", joined.relh, "humidity_pct"),
                                     ("wind_speed_10m", joined.sknt*1.852, "wind_kmh")):
            ok = obs.notna() & joined[model_col].notna()
            if ok.any():
                residual = joined.loc[ok, model_col] - obs[ok]
                comparisons[name] = {"n": int(ok.sum()), "rmse": float(np.sqrt(np.mean(residual**2))), "bias_model_minus_station": float(residual.mean())}
        save_json(out / "weather_station_comparison.json", {"station": "SANU", "distance_km": summary["station_distance_km"],
                  "warning": "DIFERENTES_UBICACIONES_NO_CALIBRACION_DEL_SENSOR", "comparison": comparisons})
    save_json(out / "summary.json", summary)
    def matrix(frame):
        return [list(frame.columns)] + json.loads(frame.to_json(orient="values", date_format="iso"))
    save_json(out / "workbook_payload.json", {
        "summary": summary, "metrics": bench, "assumptions": asdict(a),
        "rain": matrix(rain[["fecha_local", "ifs_mm_estimados", "era5_mm_estimados", "ifs_horas", "era5_horas", "sanu_reportes_RA_DZ", "evidencia_presencia", "lluvia_medida_parcela_mm", "inta_mm_publicados_fecha_proveedor", "inta_registros_unicos_reloj_proveedor"]]),
        "quality": matrix(daily_real.reset_index()),
        "hourly": matrix(sh.reset_index()[["timestamp_local", "origin", "soil_moisture", "soil_lag_6h", "soil_lag_24h", "temperature_c", "relative_humidity_pct", "wind_kmh", "rain_24h_mm", "et0_24h_mm", "irrigation_24h_l", "soil_moisture_t_plus_24h", "target_origin"]]),
        "sources": ["https://open-meteo.com/en/docs/historical-weather-api", "https://mesonet.agron.iastate.edu/request/download.phtml", NEWS_URL,
                    "https://www.fao.org/4/X0490E/x0490e0e.htm", "https://siga.inta.gob.ar/"]})
    checksums = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.iterdir()) if p.is_file()}
    save_json(out / "checksums.json", checksums)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(json.dumps(bench, ensure_ascii=False, indent=2))
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cutoff", default="2026-10-14T18:57:00-03:00")
    parser.add_argument("--freeze-weather-from", type=Path)
    args = parser.parse_args()
    build(args.snapshot, args.output, args.cutoff, args.freeze_weather_from)
