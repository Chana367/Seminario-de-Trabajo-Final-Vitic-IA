"""Ejemplo offline de inferencia; no envía órdenes y no convierte el futuro en etiqueta."""
from datetime import datetime, timezone
import json

import joblib
import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

from evaluar_cierre import ROOT, CUT, TZ


def main():
    payload = joblib.load(ROOT / "modelo/gradient_boosting_cierre.joblib")
    hourly = pd.read_csv(ROOT / "datos/serie_horaria.csv", index_col=0)
    hourly.index = pd.to_datetime(hourly.index, utc=True)
    row = hourly.loc[[CUT], payload["features"]].apply(pd.to_numeric)
    if row.soil_moisture.isna().any():
        raise ValueError("No hay cobertura de suelo al corte para demostrar la inferencia.")
    with threadpool_limits(limits=1):
        predicted = float(np.clip(payload["estimator"].predict(row)[0], 0, 100))
    result = dict(feature_origin_local=str(CUT.tz_convert(TZ)),
                  calculated_at_utc=datetime.now(timezone.utc).isoformat(),
                  target_local=str((CUT + pd.Timedelta(hours=24)).tz_convert(TZ)),
                  predicted_relative_soil_pct=predicted,
                  persistence_relative_soil_pct=float(row.soil_moisture.iloc[0]),
                  target_observed=False, counted_in_validation=False,
                  status="DEMOSTRACION_OFFLINE_CALCULADA_DESPUES_DEL_CORTE_NO_PROSPECTIVA",
                  actuators_controlled=False)
    (ROOT / "modelo/prediccion_demostracion_sin_etiqueta.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
