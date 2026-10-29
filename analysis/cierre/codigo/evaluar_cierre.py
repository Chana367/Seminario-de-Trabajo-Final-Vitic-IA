"""Auditoría y validación temporal del corte de VitiAlert, sin acceso de escritura a producción."""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
from datetime import datetime, timezone
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
import joblib
import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from threadpoolctl import threadpool_limits

import protocolo_suelo as prior

ROOT = Path(__file__).resolve().parents[1]
CUT = pd.Timestamp("2026-10-28T19:00:00Z")
START = pd.Timestamp("2026-10-01T03:00:00Z")
FREEZE = CUT - pd.Timedelta(hours=96)
OLD_CUT = pd.Timestamp("2026-10-22T22:28:09Z")
TZ = prior.TZ
BASE_FEATURES = prior.FEATURES
DHT_FEATURES = ["air_temperature", "air_humidity"]
WEATHER_COLUMNS = ["temp_max_c", "temp_mean_c", "humidity_mean_pct", "humidity_min_pct",
                   "wind_mean_kmh", "wind_max_kmh", "precipitation_mm", "solar_radiation_mj_m2", "et0_mm", "vpd_max_kpa"]
GOES_COLUMNS = ["cloud_top_temperature_c", "cloud_temperature_delta_c", "cloud_fraction", "rainfall_rate_mm_h"]
SENTINEL_COLUMNS = ["ndvi_mean", "ndmi_mean"]
EXTERNAL_FEATURES = ["weather_" + x for x in WEATHER_COLUMNS] + ["sat_" + x for x in GOES_COLUMNS + SENTINEL_COLUMNS]


def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def clean_json(value):
    if isinstance(value, dict):
        return {str(k): clean_json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean_json(v) for v in value]
    if isinstance(value, (pd.Timestamp, datetime, Path)):
        return str(value)
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, (float, np.floating)):
        return float(value) if np.isfinite(value) else None
    if isinstance(value, np.bool_):
        return bool(value)
    if value is pd.NaT:
        return None
    return value


def save_json(path, value):
    path.write_text(json.dumps(clean_json(value), ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")


def load_api():
    folder = ROOT / "fuentes_api"
    manifest = json.loads((folder / "MANIFIESTO_FUENTES.json").read_text(encoding="utf-8"))
    assert pd.Timestamp(manifest["cutoff_utc"]) == CUT
    rows, events = [], []
    for item in manifest["requests"]:
        p = folder / item["file"]
        if digest(p) != item["sha256"]:
            raise ValueError(f"Fuente modificada: {p.name}")
        content = json.loads(p.read_text(encoding="utf-8"))["content"]
        (rows if p.name.startswith("telemetry_") else events).extend(content)
    return pd.DataFrame(rows), pd.DataFrame(events)


def read_table(name):
    p = ROOT / "respaldo_bd" / "tablas" / f"{name}.jsonl"
    if not p.exists():
        return pd.DataFrame()
    return pd.DataFrame([json.loads(line) for line in p.read_text(encoding="utf-8-sig").splitlines() if line.strip()])


def verify_database_exports():
    manifest_path = ROOT / "respaldo_bd/MANIFIESTO_RESPALDO.json"
    if not manifest_path.exists():
        return False
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for name, spec in manifest["tables"].items():
        path = ROOT / "respaldo_bd/tablas" / (name + ".jsonl")
        assert digest(path) == spec["sha256"], f"Tabla modificada: {name}"
    return True


def enrich_context(raw):
    stored = read_table("telemetry_reading")
    audit = {"database_context_checked": False, "api_omits_context_after_rollback": True}
    if not stored.empty:
        stored["timestamp_received"] = pd.to_datetime(stored.timestamp_received, utc=True, format="mixed")
        selected = stored[(stored.timestamp_received <= CUT) & stored.id.isin(raw.id)]
        assert set(selected.id) == set(raw.id), "Diferencia entre respaldo y API al corte."
        a = raw.set_index("id")
        b = selected.set_index("id")
        for col in ("humedad_suelo_pct", "temperatura_ambiente_c", "humedad_relativa_pct", "caudal_l_min", "volumen_total_l"):
            np.testing.assert_allclose(pd.to_numeric(a[col]).sort_index(), pd.to_numeric(b[col]).sort_index(), equal_nan=True)
        raw = raw.copy()
        raw["contexto_adquisicion"] = raw.id.map(b.acquisition_context)
        audit.update(database_context_checked=True, matched_telemetry_rows=len(selected),
                     stored_context_rows=int(selected.acquisition_context.notna().sum()),
                     records_after_cut_in_native_backup=int(stored.timestamp_received.gt(CUT).sum()))
    return raw, audit


def stage(at):
    return "corte_22_octubre" if at <= OLD_CUT else "posterior_22_octubre"


def quality_stats(raw, events):
    raw = raw.copy()
    raw["timestamp"] = pd.to_datetime(raw.timestamp, utc=True, format="mixed")
    raw = raw[raw.timestamp.ge(START) & raw.timestamp.le(CUT)]
    raw["fecha_local"] = raw.timestamp.dt.tz_convert(TZ).dt.strftime("%Y-%m-%d")
    raw["etapa"] = raw.timestamp.map(stage)
    raw["dht_completo"] = raw.temperatura_ambiente_c.notna() & raw.humedad_relativa_pct.notna()
    raw["flow_positive"] = pd.to_numeric(raw.caudal_l_min, errors="coerce").gt(.2)
    raw["valve_open"] = raw.valvula_abierta_actual.eq(True)
    raw["flow_with_closed_valve"] = raw.flow_positive & raw.valvula_abierta_actual.eq(False)
    raw["open_without_flow"] = raw.valve_open & ~raw.flow_positive
    raw["soil_extreme"] = ~pd.to_numeric(raw.humedad_suelo_pct, errors="coerce").between(0, 100, inclusive="neither")
    daily = raw.groupby("fecha_local").agg(
        lecturas=("id", "size"), temperatura_presente=("temperatura_ambiente_c", "count"),
        humedad_aire_presente=("humedad_relativa_pct", "count"), dht_completo=("dht_completo", "sum"),
        suelo_min=("humedad_suelo_pct", "min"), suelo_max=("humedad_suelo_pct", "max"),
        caudal_mayor_02=("flow_positive", "sum"), caudal_max=("caudal_l_min", "max"),
        valvula_abierta=("valve_open", "sum"), caudal_con_valvula_cerrada=("flow_with_closed_valve", "sum"),
        viento_presente=("velocidad_viento_kmh", "count"), viento_min=("velocidad_viento_kmh", "min"),
        viento_max=("velocidad_viento_kmh", "max"), suelo_extremo_o_ausente=("soil_extreme", "sum"))
    calendar = pd.date_range("2026-10-01", "2026-10-28").strftime("%Y-%m-%d")
    daily = daily.reindex(calendar)
    for col in ["lecturas", "temperatura_presente", "humedad_aire_presente", "dht_completo", "caudal_mayor_02", "valvula_abierta", "caudal_con_valvula_cerrada", "viento_presente", "suelo_extremo_o_ausente"]:
        daily[col] = daily[col].fillna(0).astype(int)
    daily.index.name = "fecha_local"
    daily["dht_disponible_pct"] = 100 * daily.dht_completo / daily.lecturas.replace(0, np.nan)
    stages = []
    for label, g in raw.groupby("etapa", sort=True):
        t = g.sort_values("timestamp")
        resets = t.volumen_total_l.diff().lt(-.001)
        stages.append(dict(etapa=label, lecturas=len(g), primera_local=g.timestamp.min().tz_convert(TZ),
                           ultima_local=g.timestamp.max().tz_convert(TZ), dht_completo=int(g.dht_completo.sum()),
                           dht_disponible_pct=100 * float(g.dht_completo.mean()), caudal_mayor_02=int(g.flow_positive.sum()),
                           caudal_con_valvula_cerrada=int(g.flow_with_closed_valve.sum()),
                           valvula_abierta_sin_caudal_mayor_02=int(g.open_without_flow.sum()),
                           viento_no_nulo=int(g.velocidad_viento_kmh.notna().sum()),
                           flags=g.quality_flag.value_counts().to_dict(), caidas_contador=int(resets.sum())))
    e = events.copy()
    e["started_at"] = pd.to_datetime(e.started_at, utc=True, format="mixed")
    e["ended_at"] = pd.to_datetime(e.ended_at, utc=True, format="mixed")
    e = e[e.started_at.ge(START) & e.started_at.le(CUT)].copy()
    e["cerrado_al_corte"] = e.ended_at.notna() & e.ended_at.le(CUT) & e.estado.eq("CLOSED")
    e["etapa"] = e.started_at.map(stage)
    e["advertencia"] = e.observaciones.fillna("").ne("")
    e["reinicio_contador"] = e.observaciones.fillna("").str.contains("reinici", case=False)
    e["volumen_circulado_reportado_l"] = pd.to_numeric(e.volumen_aplicado_l, errors="coerce").where(e.cerrado_al_corte)
    e["ciclo_sin_advertencia_volumen_positivo"] = e.cerrado_al_corte & ~e.advertencia & e.volumen_circulado_reportado_l.gt(0)
    event_stats = []
    for label, g in e.groupby("etapa"):
        good = g[g.ciclo_sin_advertencia_volumen_positivo]
        event_stats.append(dict(etapa=label, eventos=len(g), cerrados_al_corte=int(g.cerrado_al_corte.sum()),
                                volumen_positivo=int(g.volumen_circulado_reportado_l.gt(0).sum()),
                                con_advertencia=int(g.advertencia.sum()), con_reinicio=int(g.reinicio_contador.sum()),
                                ciclos_sin_advertencia_con_volumen=int(len(good)),
                                suma_volumen_circulado_reportado_l=float(good.volumen_circulado_reportado_l.sum()),
                                no_cerrados_o_censurados=int((~g.cerrado_al_corte).sum())))
    return raw, daily, stages, e, event_stats


def add_dht(hourly, measured):
    result = hourly.copy()
    for src, dst, lo, hi in [("temperatura_ambiente_c", "air_temperature", -40, 80), ("humedad_relativa_pct", "air_humidity", 0, 100)]:
        v = pd.to_numeric(measured[src], errors="coerce")
        d = pd.DataFrame({"value": v.where(v.between(lo, hi)), "clock": measured.index}, index=measured.index).dropna(subset=["value"])
        if d.empty:
            result[dst] = np.nan
            continue
        g = d.resample("h", closed="right", label="right").agg(value=("value", "mean"), count=("value", "size"), first=("clock", "min"), last=("clock", "max"), gap=("clock", lambda x: x.sort_values().diff().dt.total_seconds().max() / 60))
        ok = g["count"].ge(6) & (g["last"] - g["first"]).dt.total_seconds().ge(45 * 60) & g.gap.le(10)
        result[dst] = g.value.where(ok).reindex(result.index)
    return result


def add_external(hourly):
    result = hourly.copy()
    for f in EXTERNAL_FEATURES:
        result[f] = np.nan
    result["weather_available_at"] = pd.Series(pd.NaT, index=result.index, dtype="datetime64[ns, UTC]")
    result["sat_available_at"] = pd.Series(pd.NaT, index=result.index, dtype="datetime64[ns, UTC]")
    result["weather_observation_date"] = pd.Series(None, index=result.index, dtype=object)
    result["weather_source"] = pd.Series(None, index=result.index, dtype=object)
    result["weather_age_days"] = np.nan
    result["satellite_row_id"] = np.nan
    result["sentinel_image_date"] = pd.Series(None, index=result.index, dtype=object)
    weather, sat = read_table("weather_observation"), read_table("satellite_observation")
    if not weather.empty:
        for c in ("created_at", "updated_at"):
            weather[c] = pd.to_datetime(weather[c], utc=True, format="mixed")
        weather["available"] = weather[["created_at", "updated_at"]].max(axis=1)
        weather["day"] = pd.to_datetime(weather.observation_date).dt.date
        for at in result.index:
            localday = at.tz_convert(TZ).date()
            q = weather[(weather.available <= at) & (weather.day < localday)].copy()
            if q.empty:
                continue
            q = q[q.day.map(lambda day: (localday - day).days <= 10)]
            if q.empty:
                continue
            q["archive"] = q.source.eq("OPEN_METEO_ERA5")
            row = q.sort_values(["day", "archive", "available"]).iloc[-1]
            for c in WEATHER_COLUMNS:
                result.loc[at, "weather_" + c] = row[c]
            result.loc[at, "weather_available_at"] = row.available
            result.loc[at, "weather_observation_date"] = str(row.day)
            result.loc[at, "weather_source"] = row.source
            result.loc[at, "weather_age_days"] = (localday - row.day).days
    if not sat.empty:
        sat["retrieved_at"] = pd.to_datetime(sat.retrieved_at, utc=True, format="mixed")
        sat["goes_observation_time"] = pd.to_datetime(sat.goes_observation_time, utc=True, format="mixed")
        sat["sentinel_day"] = pd.to_datetime(sat.sentinel_image_date).dt.date
        # Retrieved_at procede del timestamp de respuesta. El margen evita usar
        # una captura emitida unos segundos antes de que se persistiera.
        sat["available"] = sat.retrieved_at + pd.Timedelta(minutes=5)
        sat = sat[sat.overall_quality.ne("NO_DATA")]
        for at in result.index:
            q = sat[sat.available.le(at)].sort_values("available")
            if q.empty:
                continue
            row = q.iloc[-1]
            result.loc[at, "sat_available_at"] = row.available
            result.loc[at, "satellite_row_id"] = row.id
            result.loc[at, "sentinel_image_date"] = str(row.sentinel_day) if pd.notna(row.sentinel_day) else None
            if pd.notna(row.goes_observation_time) and pd.Timedelta(0) <= at - row.goes_observation_time <= pd.Timedelta(hours=6):
                for c in GOES_COLUMNS:
                    result.loc[at, "sat_" + c] = row[c]
            if pd.notna(row.sentinel_day) and 0 <= (at.tz_convert(TZ).date() - row.sentinel_day).days <= 14:
                for c in SENTINEL_COLUMNS:
                    result.loc[at, "sat_" + c] = row[c]
    inventory = dict(weather_rows=len(weather), satellite_rows=len(sat),
                     weather_hours_with_value=int(result[["weather_" + x for x in WEATHER_COLUMNS]].notna().any(axis=1).sum()),
                     satellite_hours_with_value=int(result[["sat_" + x for x in GOES_COLUMNS + SENTINEL_COLUMNS]].notna().any(axis=1).sum()),
                     database_tables_available=not weather.empty or not sat.empty)
    return result, inventory


def metrics(y, pred):
    v = prior.score(y, pred)
    np.testing.assert_allclose(v["mae_pp"], mean_absolute_error(y, pred))
    np.testing.assert_allclose(v["rmse_pp"], np.sqrt(mean_squared_error(y, pred)))
    if v["r2"] is not None:
        np.testing.assert_allclose(v["r2"], r2_score(y, pred))
    v["bias_pp"] = float(np.mean(np.asarray(pred) - np.asarray(y)))
    v["median_absolute_error_pp"] = float(np.median(np.abs(np.asarray(pred) - np.asarray(y))))
    v["max_absolute_error_pp"] = float(np.max(np.abs(np.asarray(pred) - np.asarray(y))))
    return v


def active(train, features):
    return [f for f in features if train[f].notna().any()]


def fit(train, features):
    used = active(train, features)
    model = HistGradientBoostingRegressor(**prior.PARAMS).fit(train[used], train[prior.TARGET])
    return model, used


def walk(pairs, features):
    rows = []
    for at, row in pairs.iterrows():
        train = prior.causal_training(pairs, at)
        if len(train) < 24:
            continue
        model, used = fit(train, features)
        pred = float(np.clip(model.predict(pairs.loc[[at], used])[0], 0, 100))
        rows.append(dict(timestamp=at, target_timestamp=row.target_timestamp, target=row[prior.TARGET],
                         model=pred, persistence=row.soil_moisture, n_train=len(train),
                         last_training_target=train.target_timestamp.max(), active_features="|".join(used)))
    return pd.DataFrame(rows)


def compare(frame, columns):
    if frame.empty:
        return {"n": 0}
    baseline = metrics(frame.target, frame.persistence)
    result = {"n": len(frame), "target_days": frame.target_timestamp.dt.tz_convert(TZ).dt.date.nunique(),
              "origin_first_local": frame.timestamp.min().tz_convert(TZ), "origin_last_local": frame.timestamp.max().tz_convert(TZ),
              "target_first_local": frame.target_timestamp.min().tz_convert(TZ), "target_last_local": frame.target_timestamp.max().tz_convert(TZ),
              "persistence": baseline}
    for c in columns:
        v = metrics(frame.target, frame[c])
        v["mae_improvement_pct"] = 100 * (1 - v["mae_pp"] / baseline["mae_pp"]) if baseline["mae_pp"] else None
        v["rmse_skill"] = 1 - v["rmse_pp"] / baseline["rmse_pp"] if baseline["rmse_pp"] else None
        result[c] = v
    return result


def per_day(predictions, names):
    rows = []
    for day, g in predictions.groupby(predictions.target_timestamp.dt.tz_convert(TZ).dt.strftime("%Y-%m-%d")):
        row = dict(fecha_objetivo_local=day, n=len(g), mae_persistencia=metrics(g.target, g.persistence)["mae_pp"])
        for name in names:
            row["mae_" + name] = metrics(g.target, g[name])["mae_pp"]
        rows.append(row)
    return pd.DataFrame(rows)


def bootstrap_days(predictions, model="model", seed=20261028):
    groups = [g for _, g in predictions.groupby(predictions.target_timestamp.dt.tz_convert(TZ).dt.date)]
    if len(groups) < 6:
        return dict(status="NO_ESTIMADO_MENOS_DE_6_DIAS", distinct_days=len(groups), independent_replications=False)
    rng = np.random.default_rng(seed)
    stats = []
    for _ in range(2000):
        sampled = pd.concat([groups[i] for i in rng.integers(len(groups), size=len(groups))])
        stats.append(float((sampled[model] - sampled.target).abs().mean() - (sampled.persistence - sampled.target).abs().mean()))
    return dict(status="EXPLORATORIO_BLOQUES_DIA_OBJETIVO", distinct_days=len(groups), repetitions=2000,
                mae_difference_model_minus_persistence_pp=float((predictions[model] - predictions.target).abs().mean() - (predictions.persistence - predictions.target).abs().mean()),
                interval_95_pp=np.quantile(stats, [.025, .975]).tolist(), independent_replications=False)


def plots(hourly, daily, test, comparison, day_errors, folder):
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.spines.top": False,
                         "axes.spines.right": False, "axes.titleweight": "bold", "figure.facecolor": "white"})
    fig, axes = plt.subplots(2, 1, figsize=(11, 6.5), layout="constrained")
    days = pd.to_datetime(daily.index)
    axes[0].bar(days, daily.lecturas, color="#1b6076")
    axes[0].set(title="La captura aumentó; los días sin registros permanecen vacíos", ylabel="Lecturas recibidas")
    axes[1].bar(days, daily.dht_disponible_pct, color="#42867d")
    axes[1].set(title="DHT22: recuperación al cierre, con fallas durante la campaña", ylabel="Lecturas con ambos datos (%)", ylim=(0, 105))
    for ax in axes:
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m"))
        ax.grid(axis="y", alpha=.18)
    fig.savefig(folder / "01_captura_y_dht.png", dpi=180)
    plt.close(fig)
    x = test.target_timestamp.dt.tz_convert(TZ)
    fig, ax = plt.subplots(figsize=(11, 4.8), layout="constrained")
    grid = pd.date_range(test.target_timestamp.min(), test.target_timestamp.max(), freq="h")
    t = test.set_index("target_timestamp").reindex(grid)
    for col, label, color, style in [("target", "Humedad observada", "#25323a", "-"), ("model", "Gradient Boosting", "#1b6076", "-"), ("persistence", "Persistencia", "#bf762f", "--")]:
        ax.plot(t.index.tz_convert(TZ), t[col], label=label, color=color, ls=style, lw=1.8)
    ax.set(title="Prueba temporal: predicción a 24 horas, sin reajuste dentro del bloque", ylabel="Escala relativa de humedad (%)", xlabel="Momento del objetivo, hora argentina")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m %Hh", tz=TZ))
    handles, labels = ax.get_legend_handles_labels()
    fig.legend(handles, labels, frameon=False, loc="outside lower center", ncol=3)
    ax.grid(axis="y", alpha=.18)
    fig.savefig(folder / "02_prueba_temporal.png", dpi=180)
    plt.close(fig)
    names = ["Modelo conservado\ndel 22/10", "Modelo reentrenado\nantes del bloque", "Persistencia"]
    vals = [comparison["old_model"]["mae_pp"], comparison["model"]["mae_pp"], comparison["persistence"]["mae_pp"]]
    fig, ax = plt.subplots(figsize=(9, 4.8), layout="constrained")
    bars = ax.bar(names, vals, color=["#879aa1", "#1b6076", "#bf762f"], width=.6)
    ax.bar_label(bars, fmt="%.2f", padding=5)
    ax.set(title="Error de pronóstico en el mismo período de prueba", ylabel="Error absoluto medio (puntos)", ylim=(0, max(vals) * 1.22))
    ax.text(.01, .96, f"{comparison['n']} pronósticos • {comparison['target_days']} días con objetivos\nMenor error es mejor", transform=ax.transAxes, va="top", fontsize=9)
    ax.grid(axis="y", alpha=.18)
    fig.savefig(folder / "03_comparacion_mismo_periodo.png", dpi=180)
    plt.close(fig)
    fig, ax = plt.subplots(figsize=(10, 4.8), layout="constrained")
    for col, label, color in [("mae_model", "Gradient Boosting", "#1b6076"), ("mae_persistencia", "Persistencia", "#bf762f")]:
        ax.plot(day_errors.fecha_objetivo_local.str.slice(5), day_errors[col], marker="o", label=label, color=color)
    ax.set(title="El promedio no resume por igual todos los días", ylabel="MAE diario (puntos)", xlabel="Día del objetivo (mes-día)")
    ax.legend(frameon=False)
    ax.grid(axis="y", alpha=.18)
    fig.savefig(folder / "04_error_por_dia.png", dpi=180)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--allow-api-only", action="store_true", help="Evaluación preliminar sin respaldo nativo; el estado queda registrado.")
    args = parser.parse_args()
    if not args.allow_api_only and not (ROOT / "respaldo_bd/tablas/weather_observation.jsonl").exists():
        raise FileNotFoundError("Falta el respaldo nativo para contrastar integración multimodal.")
    database_hashes_verified = verify_database_exports()
    raw, events = load_api()
    raw, source_audit = enrich_context(raw)
    measured, hourly, exclusions = prior.prepare_hourly(raw, CUT)
    hourly = add_dht(hourly, measured)
    hourly, external = add_external(hourly)
    pairs = prior.eligible_pairs(hourly)
    for col in ("weather_available_at", "sat_available_at"):
        assert (pairs[col].isna() | pairs[col].le(pairs.index)).all()
    quality, daily, stages, audited_events, event_stats = quality_stats(raw, events)
    for folder in ("datos", "modelo", "graficos", "verificacion"):
        (ROOT / folder).mkdir(exist_ok=True)
    raw.to_csv(ROOT / "datos/telemetria_al_corte.csv", index=False)
    events.to_csv(ROOT / "datos/eventos_originales.csv", index=False)
    audited_events.to_csv(ROOT / "datos/eventos_auditados.csv", index=False)
    hourly.to_csv(ROOT / "datos/serie_horaria.csv")
    pairs.to_csv(ROOT / "datos/pares_24h.csv")
    daily.to_csv(ROOT / "datos/calidad_diaria.csv")
    save_json(ROOT / "datos/calidad_por_etapa.json", dict(telemetria=stages, eventos=event_stats))
    chosen_features = BASE_FEATURES + DHT_FEATURES + (EXTERNAL_FEATURES if external["database_tables_available"] else [])
    with threadpool_limits(limits=1):
        moving_soil = walk(pairs, BASE_FEATURES)
        moving = walk(pairs, chosen_features)
        assert moving.timestamp.equals(moving_soil.timestamp)
        moving["soil_only"] = moving_soil.model.to_numpy()
        moving["error_model_pp"] = moving.model - moving.target
        moving["error_persistence_pp"] = moving.persistence - moving.target
        moving["target_day_local"] = moving.target_timestamp.dt.tz_convert(TZ).dt.strftime("%Y-%m-%d")
        moving.to_csv(ROOT / "datos/predicciones_origen_movil.csv", index=False)
        train = pairs[pairs.target_timestamp < FREEZE]
        test = pairs[(pairs.index > FREEZE) & (pairs.index <= CUT - pd.Timedelta(hours=24))].copy()
        assert len(train) >= 24 and len(test) > 0
        assert train.target_timestamp.max() < test.index.min()
        fixed, used = fit(train, chosen_features)
        fixed_soil, soil_used = fit(train, BASE_FEATURES)
        fixed_dht, dht_used = fit(train, BASE_FEATURES + DHT_FEATURES)
        old = joblib.load(ROOT / "referencia_22_octubre/modelo_22_octubre.joblib")
        assert pd.Timestamp(old["latest_training_target"]) < test.index.min()
        holdout = pd.DataFrame(dict(timestamp=test.index, target_timestamp=test.target_timestamp.to_numpy(), target=test[prior.TARGET].to_numpy(),
                                    model=np.clip(fixed.predict(test[used]), 0, 100),
                                    soil_only=np.clip(fixed_soil.predict(test[soil_used]), 0, 100),
                                    soil_plus_dht=np.clip(fixed_dht.predict(test[dht_used]), 0, 100),
                                    old_model=np.clip(old["estimator"].predict(test[old["features"]]), 0, 100),
                                    persistence=test.soil_moisture.to_numpy(), n_train=len(train),
                                    last_training_target=train.target_timestamp.max()))
        holdout["target_timestamp"] = pd.to_datetime(holdout.target_timestamp, utc=True)
        holdout["target_day_local"] = holdout.target_timestamp.dt.tz_convert(TZ).dt.strftime("%Y-%m-%d")
        holdout.to_csv(ROOT / "datos/predicciones_bloque_fijo.csv", index=False)
        test_day = per_day(holdout, ["model", "old_model", "soil_only", "soil_plus_dht"])
        test_day.to_csv(ROOT / "datos/error_diario_bloque.csv", index=False)
        daily_errors = per_day(moving, ["model", "soil_only"])
        daily_errors.to_csv(ROOT / "datos/error_diario_origen_movil.csv", index=False)
        final, final_features = fit(pairs, chosen_features)
        artifact = dict(estimator=final, features=final_features, target=prior.TARGET, horizon_hours=24,
                        training_rows=len(pairs), cutoff_utc=str(CUT), params=prior.PARAMS,
                        latest_training_target=str(pairs.target_timestamp.max()),
                        dataset_sha256=digest(ROOT / "datos/pares_24h.csv"),
                        deployment_authorized=False, independent_field_validation=False,
                        context="Maqueta de riego con agua recirculada e intervenciones manuales.")
        model_path = ROOT / "modelo/gradient_boosting_cierre.joblib"
        joblib.dump(artifact, model_path)
        reloaded = joblib.load(model_path)
        np.testing.assert_allclose(final.predict(pairs[final_features]), reloaded["estimator"].predict(pairs[final_features]))
        joblib.dump(dict(estimator=fixed, features=used, freeze_utc=str(FREEZE), params=prior.PARAMS, training_rows=len(train)), ROOT / "modelo/modelo_prueba_congelado.joblib")
    comparison = compare(holdout, ["model", "old_model", "soil_only", "soil_plus_dht"])
    historical = json.loads((ROOT / "referencia_22_octubre/RESUMEN_RESULTADOS.json").read_text())
    old_rows_now = moving_soil[moving_soil.target_timestamp <= OLD_CUT]
    old_saved = pd.read_csv(ROOT / "referencia_22_octubre/predicciones_22_octubre.csv")
    old_saved["timestamp"] = pd.to_datetime(old_saved.timestamp, utc=True)
    matched = old_rows_now.merge(old_saved, on="timestamp", suffixes=("_new", "_old"))
    # Las exclusiones de contexto recuperadas pueden modificar el conjunto nuevo.
    old_reproduced = len(matched) == len(old_saved) and np.allclose(matched.model, matched.gradient_boosting, atol=1e-9)
    train_cov = {f: dict(training_non_missing=int(train[f].notna().sum()), test_non_missing=int(test[f].notna().sum()),
                        final_non_missing=int(pairs[f].notna().sum()), distinct_training_values=int(train[f].nunique())) for f in chosen_features}
    save_json(ROOT / "datos/cobertura_variables.json", train_cov)
    post = moving[moving.timestamp > OLD_CUT]
    worst = moving.assign(abs_error=lambda x: (x.model - x.target).abs()).nlargest(10, "abs_error")
    worst.to_csv(ROOT / "datos/mayores_errores.csv", index=False)
    summary = dict(cutoff_local=str(CUT.tz_convert(TZ)), cutoff_utc=str(CUT),
                   api_readings=len(raw), october_readings=len(quality), events_all=len(events),
                   first_reading_local=pd.to_datetime(raw.timestamp, utc=True).min().tz_convert(TZ),
                   last_reading_local=pd.to_datetime(raw.timestamp, utc=True).max().tz_convert(TZ),
                   usable_hours=int(hourly.soil_moisture.notna().sum()), eligible_pairs=len(pairs),
                   excludes=exclusions, acquisition_audit=source_audit, external_inventory=external,
                   quality_stages=stages, water_events=event_stats,
                   historical_published=historical,
                   historical_22_reproduced=old_reproduced,
                   walk_forward_all=compare(moving, ["model", "soil_only"]),
                   walk_forward_post_22=compare(post, ["model", "soil_only"]),
                   fixed_holdout=comparison,
                   fixed_training=dict(freeze_local=str(FREEZE.tz_convert(TZ)), n=len(train), latest_target_local=str(train.target_timestamp.max().tz_convert(TZ)),
                                       first_test_origin_local=str(test.index.min().tz_convert(TZ)), last_test_origin_local=str(test.index.max().tz_convert(TZ)),
                                       expected_origins=72, available_origins=len(test), active_features=used,
                                       soil_only_features=soil_used, soil_plus_dht_features=dht_used),
                   uncertainty_fixed=bootstrap_days(holdout), uncertainty_walk=bootstrap_days(moving),
                   final_model=dict(family="HistGradientBoostingRegressor", params=prior.PARAMS, features=final_features,
                                    n_pairs=len(pairs), sha256=digest(model_path), inference_pipeline="codigo/predecir_cierre.py", deployment=False),
                   checks=dict(no_future_targets=bool((pairs.target_timestamp <= CUT).all()),
                               fixed_no_label_leakage=bool(train.target_timestamp.max() < test.index.min()),
                               moving_no_label_leakage=bool((moving.last_training_target < moving.timestamp).all()),
                               exact_24h=bool(((pairs.target_timestamp - pairs.index) == pd.Timedelta(hours=24)).all()),
                               same_test_rows=True, sklearn_metrics_crosscheck=True, artifact_roundtrip=True,
                               original_22_artifact_preserved=True, production_modified=False),
                   packages={p: importlib.metadata.version(p) for p in ("numpy", "pandas", "scikit-learn", "matplotlib", "joblib")},
                   completed_utc=datetime.now(timezone.utc).isoformat())
    summary["checks"]["database_export_hashes_verified"] = database_hashes_verified
    summary["dht_hourly_coverage"] = dict(hours_with_adequate_temperature=int(hourly.air_temperature.notna().sum()),
                                           eligible_pairs_with_dht=int(pairs.air_temperature.notna().sum()),
                                           training_pairs_with_dht=int(train.air_temperature.notna().sum()),
                                           test_origins_with_dht=int(test.air_temperature.notna().sum()))
    summary["fixed_training"]["target_min"] = float(train[prior.TARGET].min())
    summary["fixed_training"]["target_max"] = float(train[prior.TARGET].max())
    rows = []
    for day in holdout.target_day_local.unique():
        g = holdout[holdout.target_day_local != day]
        m = compare(g, ["model"])
        rows.append(dict(day_omitted=day, n=len(g), mae_model=m["model"]["mae_pp"], mae_persistence=m["persistence"]["mae_pp"],
                         rmse_skill=m["model"]["rmse_skill"]))
    pd.DataFrame(rows).to_csv(ROOT / "datos/sensibilidad_por_dia.csv", index=False)
    summary["fixed_leave_one_day_out"] = rows
    save_json(ROOT / "RESUMEN_RESULTADOS.json", summary)
    plots(hourly, daily, holdout, comparison, daily_errors, ROOT / "graficos")
    print(json.dumps(clean_json({k: summary[k] for k in ("usable_hours", "eligible_pairs", "historical_22_reproduced", "fixed_holdout", "walk_forward_all", "walk_forward_post_22", "fixed_training", "external_inventory", "checks")}), ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
