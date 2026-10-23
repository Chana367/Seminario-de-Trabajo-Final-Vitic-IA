"""Comparacion al corte30, sobre EXACTAMENTE el mismo periodo futuro para ambos modelos.

La simulacion no valida desempeno sobre suelo real. El nuevo modelo excluye el holdout.
"""
import argparse
from pathlib import Path
import numpy as np
import pandas as pd
from build_dataset import FEATURES, fit_ridge, metrics, predict, save_json


def compare(old_folder: Path, new_folder: Path, output: Path, test_start: str):
    if output.exists():
        raise FileExistsError("No sobrescribir una comparacion existente")
    h = pd.read_csv(new_folder / "features_semisynthetic_hourly.csv", index_col="timestamp")
    h.index = pd.to_datetime(h.index, utc=True)
    h["target_timestamp"] = pd.to_datetime(h.target_timestamp, utc=True)
    start = pd.Timestamp(test_start).tz_convert("UTC")
    h = h.dropna(subset=FEATURES + ["soil_moisture_t_plus_24h"])
    train = h[h.target_timestamp < start]
    test = h[h.index >= start]
    if len(train) < 48 or len(test) < 24:
        raise ValueError("Todavia no hay >=24 targets futuros del bloque comun de prueba")
    old_metrics = __import__("json").loads((old_folder / "model_metrics.json").read_text(encoding="utf-8"))
    if pd.Timestamp(old_metrics["semisynthetic"]["frozen_cutoff_model"]["max_target_time_utc"]) >= start:
        raise ValueError("El modelo antiguo ya vio targets del periodo de prueba")
    old_assumptions = __import__("json").loads((old_folder / "assumptions.json").read_text())
    new_assumptions = __import__("json").loads((new_folder / "assumptions.json").read_text())
    if old_assumptions != new_assumptions:
        raise ValueError("Cambiaron los supuestos del simulador: no es una comparacion controlada")
    old_weather = pd.read_csv(old_folder / "forcing_hourly.csv", index_col=0)
    new_weather = pd.read_csv(new_folder / "forcing_hourly.csv", index_col=0)
    if not old_weather.equals(new_weather.reindex(old_weather.index)[old_weather.columns]):
        raise ValueError("Cambio el clima del corte inicial: usar --freeze-weather-from")
    old = dict(np.load(old_folder / "model_semisynthetic_cutoff_frozen.npz", allow_pickle=False))
    new = fit_ridge(train)
    y = test.soil_moisture_t_plus_24h.to_numpy()
    preds = {"ridge_corte14": predict(old, test), "ridge_corte30_sin_holdout": predict(new, test),
             "persistencia": test.soil_moisture.to_numpy(),
             "media_entrenamiento_corte14": np.full(len(y), float(old["target_mean"])),
             "media_entrenamiento_corte30": np.full(len(y), float(new["target_mean"]))}
    report = {"interpretation": "SEMISYNTHETIC_SAME_HOLDOUT_NOT_FIELD_VALIDATION", "test_start_utc": test.index.min().isoformat(),
              "test_end_feature_time_utc": test.index.max().isoformat(), "n_test": len(test),
              "new_train_max_target_time_utc": train.target_timestamp.max().isoformat(),
              "warning": "El modelo del corte30 no se entrena con el bloque de prueba, por lo que no usa los 30 dias completos.",
              "metrics": {name: metrics(y, p) for name, p in preds.items()}}
    output.mkdir(parents=True)
    save_json(output / "comparison.json", report)
    pd.DataFrame({"timestamp": test.index, "target": y, **preds}).to_csv(output / "same_holdout_predictions.csv", index=False)
    np.savez(output / "model_new_train_without_holdout.npz", **new)
    print(__import__("json").dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--old", type=Path, required=True)
    p.add_argument("--new", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--test-start", default="2026-10-27T00:00:00-03:00")
    a = p.parse_args()
    compare(a.old, a.new, a.output, a.test_start)
