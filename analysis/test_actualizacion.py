import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from actualizar_modelo_real import FEATURES, TARGET, available_features, causal_training, eligible_pairs, prepare_hourly, score, walk_forward


def fixture(hours=100):
    rows = []
    start = pd.Timestamp('2026-10-01T03:00:00Z')
    for h in range(hours):
        for minute in (5,15,25,35,45,55):
            rows.append(dict(id=len(rows)+1, timestamp=(start+pd.Timedelta(hours=h, minutes=minute)).isoformat(),
                             humedad_suelo_pct=20+h*.02, quality_notes=None, calidad='MISSING'))
    return pd.DataFrame(rows), start+pd.Timedelta(hours=hours)


class UpdateTests(unittest.TestCase):
    def test_targets_are_exactly_24_hours(self):
        raw, cutoff = fixture()
        _, hourly, _ = prepare_hourly(raw, cutoff)
        pairs = eligible_pairs(hourly)
        self.assertTrue(((pairs.target_timestamp-pairs.index)==pd.Timedelta(hours=24)).all())
        expected = hourly.soil_moisture.reindex(pairs.target_timestamp).to_numpy()
        np.testing.assert_allclose(pairs[TARGET], expected)

    def test_gap_does_not_shift_future_target(self):
        raw, cutoff = fixture()
        missing = pd.Timestamp('2026-10-03T04:00:00Z')
        t = pd.to_datetime(raw.timestamp, utc=True)
        raw = raw[~((t>missing-pd.Timedelta(hours=1)) & (t<=missing))]
        _, hourly, _ = prepare_hourly(raw, cutoff)
        self.assertTrue(pd.isna(hourly.loc[missing-pd.Timedelta(hours=24),TARGET]))

    def test_reconstructed_rows_are_excluded(self):
        raw, cutoff = fixture()
        raw.loc[:5,'quality_notes'] = 'RECONSTRUIDO:fila completa'
        _, hourly, audit = prepare_hourly(raw, cutoff)
        self.assertEqual(audit['reconstructed_rows_excluded'],6)
        self.assertFalse(hourly.iloc[0].coverage_usable)

    def test_sparse_or_internal_gap_hour_not_usable(self):
        raw, cutoff = fixture()
        raw = raw.drop(index=[1,2,3,4])
        _, hourly, _ = prepare_hourly(raw, cutoff)
        self.assertTrue(pd.isna(hourly.iloc[0].soil_moisture))

    def test_future_reading_is_rejected(self):
        raw, cutoff = fixture()
        with self.assertRaisesRegex(ValueError,'posteriores'):
            prepare_hourly(raw, cutoff-pd.Timedelta(hours=2))

    def test_missing_environment_does_not_discard_soil(self):
        raw, cutoff = fixture()
        _, hourly, _ = prepare_hourly(raw, cutoff)
        self.assertEqual(hourly.soil_moisture.notna().sum(),100)
        self.assertFalse(any('irrigation' in x for x in FEATURES))

    def test_causal_purge_uses_target_timestamp(self):
        raw, cutoff = fixture()
        _, hourly, _ = prepare_hourly(raw, cutoff)
        pairs = eligible_pairs(hourly)
        at = pairs.index[50]
        train = causal_training(pairs,at)
        self.assertTrue((train.target_timestamp<at).all())
        self.assertFalse((train.index==at-pd.Timedelta(hours=24)).any())

    def test_walk_forward_comparisons_use_same_rows(self):
        raw, cutoff = fixture()
        _, hourly, _ = prepare_hourly(raw, cutoff)
        pairs = eligible_pairs(hourly)
        class FakeEstimator:
            def __init__(self,**kwargs): pass
            def fit(self,x,y): self.value=float(y.mean()); return self
            def predict(self,x): return np.full(len(x),self.value)
        with patch('actualizar_modelo_real.HistGradientBoostingRegressor',FakeEstimator):
            pred = walk_forward(pairs)
        self.assertTrue((pred.last_training_target<pred.timestamp).all())
        self.assertTrue(pred.n_train.ge(24).all())
        self.assertFalse(pred[['target','persistence','gradient_boosting']].isna().any().any())

    def test_metric_values_and_constant_target(self):
        result = score([1,3],[2,1])
        self.assertAlmostEqual(result['mae_pp'],1.5)
        self.assertAlmostEqual(result['rmse_pp'],np.sqrt(2.5))
        self.assertIsNone(score([2,2],[2,3])['r2'])

    def test_all_missing_column_omitted_from_training_only(self):
        raw, cutoff = fixture()
        _, hourly, _ = prepare_hourly(raw, cutoff)
        pairs = eligible_pairs(hourly)
        train = pairs.iloc[:24].copy()
        train['soil_mean_24h'] = np.nan
        self.assertNotIn('soil_mean_24h',available_features(train))
        self.assertIn('soil_moisture',available_features(train))


if __name__=='__main__':
    unittest.main()
