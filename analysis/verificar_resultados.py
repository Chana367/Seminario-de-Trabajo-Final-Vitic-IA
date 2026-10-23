"""Verificacion independiente de integridad, etiquetas y metricas del corte real."""
import hashlib
import json
from pathlib import Path
import sys

import joblib
import numpy as np
import pandas as pd

from actualizar_modelo_real import FEATURES, TARGET, score


def verify(folder):
    hashes=json.loads((folder/'SHA256_RESULTADOS.json').read_text(encoding='utf-8'))
    for name,expected in hashes.items():
        assert hashlib.sha256((folder/name).read_bytes()).hexdigest()==expected,name
    summary=json.loads((folder/'RESUMEN_RESULTADOS.json').read_text(encoding='utf-8'))
    hourly=pd.read_csv(folder/'02_datos/horas_reales.csv',index_col='timestamp')
    hourly.index=pd.to_datetime(hourly.index,utc=True)
    hourly['target_timestamp']=pd.to_datetime(hourly.target_timestamp,utc=True)
    assert not hourly.index.has_duplicates
    assert hourly.index.is_monotonic_increasing
    expected=hourly.soil_moisture.reindex(hourly.target_timestamp).to_numpy()
    np.testing.assert_allclose(hourly[TARGET],expected,equal_nan=True)
    predictions=pd.read_csv(folder/'02_datos/predicciones_retrospectivas.csv')
    for col in ['timestamp','target_timestamp','last_training_target']:
        predictions[col]=pd.to_datetime(predictions[col],utc=True)
    assert (predictions.last_training_target<predictions.timestamp).all()
    assert ((predictions.target_timestamp-predictions.timestamp)==pd.Timedelta(hours=24)).all()
    assert predictions.n_train.ge(24).all()
    np.testing.assert_allclose(predictions.persistence,hourly.soil_moisture.reindex(predictions.timestamp).to_numpy())
    np.testing.assert_allclose(predictions.target,hourly.soil_moisture.reindex(predictions.target_timestamp).to_numpy())
    for name in ['gradient_boosting','persistence']:
        recalculated=score(predictions.target,predictions[name])
        for key in ['mae_pp','rmse_pp','r2']:
            assert np.isclose(recalculated[key],summary['metrics'][name][key]),(name,key)
    if summary['final_model_status']=='ENTRENADO_OFFLINE_NO_DESPLEGADO':
        payload=joblib.load(folder/'04_modelo/gradient_boosting_suelo_real.joblib')
        assert payload['origin']=='REAL_SOIL_MEASUREMENTS_NOT_RECONSTRUCTED'
        assert not payload['deployment_authorized']
        assert pd.Timestamp(payload['latest_training_target'])<=pd.Timestamp(summary['cutoff_utc'])
        pairs=pd.read_csv(folder/'02_datos/pares_24h_reales.csv')
        assert payload['training_rows']==len(pairs)==summary['eligible_pairs']
        values=payload['estimator'].predict(pairs[payload['features']].tail(5))
        assert np.isfinite(values).all()
    assert not summary['production_modified']
    assert not summary['independent_field_validation']
    print(f'Verificado: {len(hashes)} archivos, {len(predictions)} predicciones causales, targets exactos y metricas recalculadas.')


if __name__=='__main__':
    if len(sys.argv) != 2:
        raise SystemExit('Uso: python verificar_resultados.py CARPETA_DE_RESULTADOS_CONFIABLES')
    verify(Path(sys.argv[1]))
