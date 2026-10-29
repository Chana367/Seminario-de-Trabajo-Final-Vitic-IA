"""Controles de horizonte, cobertura, censura y disponibilidad temporal."""
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

import evaluar_cierre as close
import protocolo_suelo as prior


def readings(hours=80):
    start = pd.Timestamp("2026-10-24T03:00:00Z")
    result = []
    for h in range(hours):
        for minute in (5, 15, 25, 35, 45, 55):
            result.append(dict(id=len(result) + 1, timestamp=start + pd.Timedelta(hours=h, minutes=minute),
                               humedad_suelo_pct=20 + h * .02, calidad="VALID", quality_notes=None,
                               temperatura_ambiente_c=24., humedad_relativa_pct=40.))
    return pd.DataFrame(result), start + pd.Timedelta(hours=hours)


class TemporalTests(unittest.TestCase):
    def test_exact_target_and_last_unobserved_day(self):
        raw, cutoff = readings()
        _, h, _ = prior.prepare_hourly(raw, cutoff)
        pairs = prior.eligible_pairs(h)
        self.assertTrue(((pairs.target_timestamp - pairs.index) == pd.Timedelta(hours=24)).all())
        self.assertTrue(h.loc[h.index > cutoff - pd.Timedelta(hours=24), prior.TARGET].isna().all())

    def test_gap_does_not_shift_target(self):
        raw, cutoff = readings()
        missing = pd.Timestamp("2026-10-26T08:00:00Z")
        raw = raw[~((raw.timestamp > missing - pd.Timedelta(hours=1)) & (raw.timestamp <= missing))]
        _, h, _ = prior.prepare_hourly(raw, cutoff)
        self.assertTrue(pd.isna(h.loc[missing - pd.Timedelta(hours=24), prior.TARGET]))

    def test_training_labels_are_known_before_origin(self):
        raw, cutoff = readings()
        _, h, _ = prior.prepare_hourly(raw, cutoff)
        pairs = prior.eligible_pairs(h)
        at = pairs.index[-1]
        train = prior.causal_training(pairs, at)
        self.assertTrue((train.target_timestamp < at).all())
        self.assertNotIn(at - pd.Timedelta(hours=24), train.index)

    def test_missing_dht_does_not_erase_soil(self):
        raw, cutoff = readings()
        raw["temperatura_ambiente_c"] = np.nan
        measured, h, _ = prior.prepare_hourly(raw, cutoff)
        h = close.add_dht(h, measured)
        self.assertEqual(h.soil_moisture.notna().sum(), 80)
        self.assertEqual(h.air_temperature.notna().sum(), 0)
        self.assertEqual(h.air_humidity.notna().sum(), 80)

    def test_isolated_dht_samples_do_not_create_hourly_coverage(self):
        raw, cutoff = readings(hours=2)
        raw.loc[1:5, "temperatura_ambiente_c"] = np.nan
        measured, h, _ = prior.prepare_hourly(raw, cutoff)
        h = close.add_dht(h, measured)
        self.assertTrue(pd.isna(h.loc[pd.Timestamp("2026-10-24T04:00:00Z"), "air_temperature"]))
        self.assertTrue(pd.notna(h.loc[pd.Timestamp("2026-10-24T05:00:00Z"), "air_temperature"]))

    def test_weather_version_from_future_is_not_used(self):
        at = pd.Timestamp("2026-10-24T19:00:00Z")
        h = pd.DataFrame(index=pd.DatetimeIndex([at]))
        row = dict(id=1, observation_date="2026-10-23", source="OPEN_METEO_FORECAST", created_at="2026-10-24T01:00:00Z", updated_at="2026-10-25T01:00:00Z", **{c: 5. for c in close.WEATHER_COLUMNS})
        with patch.object(close, "read_table", side_effect=lambda name: pd.DataFrame([row]) if name == "weather_observation" else pd.DataFrame()):
            result, _ = close.add_external(h)
        self.assertTrue(result[close.EXTERNAL_FEATURES].isna().all().all())

    def test_current_day_weather_summary_is_not_used(self):
        at = pd.Timestamp("2026-10-24T19:00:00Z")
        row = dict(id=1, observation_date="2026-10-24", source="OPEN_METEO_FORECAST", created_at="2026-10-24T01:00:00Z", updated_at="2026-10-24T01:00:00Z", **{c: 5. for c in close.WEATHER_COLUMNS})
        with patch.object(close, "read_table", side_effect=lambda name: pd.DataFrame([row]) if name == "weather_observation" else pd.DataFrame()):
            result, _ = close.add_external(pd.DataFrame(index=pd.DatetimeIndex([at])))
        self.assertTrue(result[close.EXTERNAL_FEATURES].isna().all().all())

    def test_satellite_unavailable_future_observation_is_not_used(self):
        at = pd.Timestamp("2026-10-24T19:00:00Z")
        row = dict(id=1, retrieved_at="2026-10-24T18:00:00Z", goes_observation_time="2026-10-24T20:00:00Z", sentinel_image_date="2026-10-25", overall_quality="VALID", **{c: 5. for c in close.GOES_COLUMNS + close.SENTINEL_COLUMNS})
        with patch.object(close, "read_table", side_effect=lambda name: pd.DataFrame([row]) if name == "satellite_observation" else pd.DataFrame()):
            result, _ = close.add_external(pd.DataFrame(index=pd.DatetimeIndex([at])))
        self.assertTrue(result[["sat_" + c for c in close.GOES_COLUMNS + close.SENTINEL_COLUMNS]].isna().all().all())

    def test_recognized_experiment_is_excluded_without_altering_source(self):
        raw, cutoff = readings()
        raw["contexto_adquisicion"] = None
        for i in range(6):
            raw.at[i, "contexto_adquisicion"] = {"modo": "ENSAYO"}
        _, h, audit = prior.prepare_hourly(raw, cutoff)
        self.assertEqual(audit["experiment_rows_excluded"], 6)
        self.assertFalse(h.coverage_usable.iloc[0])
        self.assertEqual(len(raw), 480)

    def test_metric_values(self):
        m = close.metrics([1., 3.], [2., 1.])
        self.assertEqual(m["mae_pp"], 1.5)
        self.assertAlmostEqual(m["rmse_pp"], np.sqrt(2.5))


if __name__ == "__main__":
    unittest.main()
