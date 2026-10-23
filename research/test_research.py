import unittest
import tempfile
import json
from pathlib import Path
import numpy as np
import pandas as pd

from build_dataset import Assumptions, START, FEATURES, simulate, add_features, rain_audit, inta_context, fit_ridge, predict, benchmark
from compare_snapshots import compare


def forcing(days=3, rain=0.):
    index = pd.date_range(START.tz_convert("UTC"), periods=days * 24 + 1, freq="h")
    return pd.DataFrame({"temperature_2m": 22., "relative_humidity_2m": 40., "precipitation": rain,
                         "wind_speed_10m": 10., "et0_fao_evapotranspiration": .2,
                         "shortwave_radiation": 200.}, index=index)


class ResearchTests(unittest.TestCase):
    def test_inta_duplicates_missing_and_published_clock_are_not_plot_truth(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "inta_catalog").mkdir()
            daily = [{"fechaHora": "2026-10-01T00:00:00Z[UTC]", "idEstacion": 444, "precDiaCrono": 0, "precDiaPlub": 0}]
            record = {"fechaHora": "2026-10-01T12:00:00Z[UTC]", "idEstacion": 444, "precDiaCrono": 0}
            (root / "inta_catalog" / "pocito_daily.json").write_text(json.dumps(daily))
            (root / "inta_catalog" / "pocito_hourly.json").write_text(json.dumps([record, record]))
            contrast, report = inta_context(root, root, START + pd.Timedelta(days=1))
            self.assertEqual(report["duplicate_timestamps"], 1)
            self.assertEqual(report["unique_subhourly_records"], 1)
            self.assertFalse(report["used_to_overwrite_ifs"])
            self.assertEqual(contrast.iloc[0].precDiaCrono, 0)
            self.assertIn("UNRESOLVED", report["timestamp_basis"])

    def test_inta_conflicting_duplicates_do_not_create_rain(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "inta_catalog").mkdir()
            record = {"fechaHora": "2026-10-01T12:00:00Z[UTC]", "idEstacion": 444, "precDiaCrono": 0, "precDiaPlub": 0}
            (root / "inta_catalog" / "pocito_daily.json").write_text(json.dumps([record]))
            (root / "inta_catalog" / "pocito_hourly.json").write_text(json.dumps([record, record | {"precDiaCrono": 5}]))
            _, report = inta_context(root, root, START + pd.Timedelta(days=1))
            saved = pd.read_csv(root / "inta_station_records_provider_clock.csv")
            self.assertEqual(report["conflicting_rain_timestamps"], 1)
            self.assertTrue(saved.precDiaCrono.isna().all())

    def test_repeatable_seed(self):
        f = forcing()
        t = f.index[-1]
        pd.testing.assert_frame_equal(simulate(f, t, Assumptions()), simulate(f, t, Assumptions()))

    def test_strict_cutoff_and_spacing(self):
        cut = START + pd.Timedelta(days=1, hours=18, minutes=57)
        s = simulate(forcing(), cut, Assumptions())
        times = pd.to_datetime(s.timestamp, utc=True)
        self.assertTrue((times.diff().dropna() == pd.Timedelta(minutes=5)).all())
        self.assertLessEqual(times.max(), cut)
        self.assertEqual(int(s.soil_moisture_pct.isna().sum()), 11)

    def test_mass_balance_and_no_flow_with_closed_valve(self):
        s = simulate(forcing(), forcing().index[-1], Assumptions())
        self.assertLess(s.water_balance_residual_mm.abs().max(), 1e-8)
        self.assertTrue(s.loc[~s.valve_open_interval, "flow_l_min"].eq(0).all())
        np.testing.assert_allclose(s.volume_total_l.diff().fillna(0), s.irrigation_l_interval, atol=1e-6)

    def test_rain_conservation_and_physical_response(self):
        f = forcing(rain=1.)
        s = simulate(f, f.index[24], Assumptions())
        self.assertAlmostEqual(s.rain_mm_interval.sum(), 24.)
        wet = s.iloc[-1].soil_storage_mm
        dry_s = simulate(forcing(rain=0.), f.index[24], Assumptions(flow_open_l_min=0.))
        self.assertGreater(wet, dry_s.iloc[-1].soil_storage_mm)

    def test_bounds_and_initial_condition(self):
        f = forcing(rain=10.)
        s = simulate(f, f.index[-1], Assumptions())
        self.assertTrue(s.soil_moisture_pct.between(0, 100).all())
        self.assertTrue(s.soil_raw.between(1104, 3317).all())
        self.assertEqual(s.iloc[0].volume_total_l, 0)
        expected = ((s.soil_raw - 3317) * 100 / (1104 - 3317)).astype(int)
        np.testing.assert_array_equal(s.soil_moisture_pct, expected)

    def test_time_based_target_does_not_jump_over_a_gap(self):
        f = forcing(days=5)
        h = pd.DataFrame({"soil_moisture": np.arange(len(f), dtype=float), "irrigation_l": 0.}, index=f.index)
        missing = f.index[48]
        h.loc[missing, "soil_moisture"] = np.nan
        made = add_features(h, f, f.index[-1], "REAL_TEST")
        self.assertTrue(pd.isna(made.loc[f.index[24], "soil_moisture_t_plus_24h"]))
        self.assertEqual(made.loc[f.index[25], "soil_moisture_t_plus_24h"], 49)
        self.assertTrue(made.loc[made.target_timestamp > f.index[-1], "soil_moisture_t_plus_24h"].isna().all())

    def test_rain_hour_midnight_belongs_to_previous_day(self):
        f = forcing(days=3, rain=1.)
        s = pd.DataFrame(columns=["day", "rain_code"])
        r = rain_audit(f, f, s, START + pd.Timedelta(days=2))
        self.assertEqual(r.iloc[0].ifs_horas, 24)
        self.assertEqual(r.iloc[0].ifs_mm_estimados, 24)
        self.assertTrue(r.lluvia_medida_parcela_mm.isna().all())

    def test_ridge_contract_and_training_only_scaling(self):
        rng = np.random.default_rng(1)
        x = pd.DataFrame(rng.normal(size=(100, len(FEATURES))), columns=FEATURES)
        x["soil_moisture_t_plus_24h"] = 30 + x.soil_moisture * 2
        model = fit_ridge(x.iloc[:60])
        np.testing.assert_allclose(model["mean"], x.iloc[:60][FEATURES].mean())
        self.assertEqual(predict(model, x.iloc[60:]).shape, (40,))

    def test_time_split_purges_future_labels(self):
        f = forcing(days=14)
        h = pd.DataFrame({"soil_moisture": 20 + np.sin(np.arange(len(f))/24), "irrigation_l": .1}, index=f.index)
        made = add_features(h, f, f.index[-1], "SEMISYNTHETIC_TEST")
        with tempfile.TemporaryDirectory() as temp:
            result = benchmark(made, f.index[-1], Path(temp), "semisynthetic")
        self.assertEqual(result["status"], "TRAINED_OFFLINE_NOT_DEPLOYED")
        self.assertLess(pd.Timestamp(result["max_train_target_time_utc"]), pd.Timestamp(result["first_test_feature_time_utc"]))

    def test_refuse_fabricated_features_for_real_data(self):
        f = forcing(days=14)
        h = pd.DataFrame({"soil_moisture": 20., "irrigation_l": np.nan}, index=f.index)
        made = add_features(h, f, f.index[-1], "REAL_SENSOR_WITH_MODEL_WEATHER_CONTEXT")
        with tempfile.TemporaryDirectory() as temp:
            result = benchmark(made, f.index[-1], Path(temp), "real")
        self.assertEqual(result["status"], "NOT_TRAINED_INSUFFICIENT_RELIABLE_DATA")

    def comparison_fixture(self, root):
        old, new = root / "old", root / "new"
        old.mkdir()
        new.mkdir()
        f = forcing(days=30)
        old_cut, new_cut = START + pd.Timedelta(days=13, hours=18), START + pd.Timedelta(days=29, hours=18)
        f = f[f.index <= new_cut]
        raw = pd.DataFrame({"soil_moisture": 30 + np.sin(np.arange(len(f))/24), "irrigation_l": .1}, index=f.index)
        h = add_features(raw, f, new_cut, "SEMISYNTHETIC_UNIT_TEST")
        eligible = h[(h.target_timestamp <= old_cut)].dropna(subset=FEATURES + ["soil_moisture_t_plus_24h"])
        np.savez(old / "model_semisynthetic_cutoff_frozen.npz", **fit_ridge(eligible))
        (old / "model_metrics.json").write_text(json.dumps({"semisynthetic": {"frozen_cutoff_model": {"max_target_time_utc": old_cut.isoformat()}}}))
        for folder in (old, new):
            (folder / "assumptions.json").write_text('{"seed":20261001}')
        f[f.index <= old_cut].to_csv(old / "forcing_hourly.csv")
        f.to_csv(new / "forcing_hourly.csv")
        h.index.name = "timestamp"
        h.to_csv(new / "features_semisynthetic_hourly.csv")
        return old, new

    def test_future_comparator_uses_same_rows_and_purges_targets(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            old, new = self.comparison_fixture(root)
            compare(old, new, root / "comparison", "2026-10-27T00:00:00-03:00")
            report = json.loads((root / "comparison" / "comparison.json").read_text())
            sizes = {m["n"] for m in report["metrics"].values()}
            self.assertEqual(len(sizes), 1)
            self.assertGreater(report["n_test"], 24)
            self.assertLess(pd.Timestamp(report["new_train_max_target_time_utc"]), pd.Timestamp(report["test_start_utc"]))

    def test_future_comparator_rejects_revised_initial_weather(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            old, new = self.comparison_fixture(root)
            f = pd.read_csv(new / "forcing_hourly.csv", index_col=0)
            f.iloc[0, 0] += 5
            f.to_csv(new / "forcing_hourly.csv")
            with self.assertRaisesRegex(ValueError, "Cambio el clima"):
                compare(old, new, root / "comparison", "2026-10-27T00:00:00-03:00")


if __name__ == "__main__":
    unittest.main()
