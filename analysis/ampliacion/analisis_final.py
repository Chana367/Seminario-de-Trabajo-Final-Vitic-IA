"""
Vitic AI - Analisis final del modelo predictivo (version de entrega).

Reglas:
  * Solo datos reales: los 153 pares del cierre del 28/10/2026. Ninguna fila se agrega ni se modifica.
  * El OBJETIVO (humedad a t+24 h) es siempre una medicion. Nunca se imputa.
  * Los hiperparametros se eligen DENTRO de cada entrenamiento (origen movil interno).
  * Se imputan predictores (rezagos) solo dentro del pipeline, ajustado con el entrenamiento.
Uso:
  python analisis_final.py [carpeta_datos] [carpeta_salida]
  carpeta_datos: tablas del paquete de cierre (por defecto ../cierre/datos):
                 pares_24h.csv, serie_horaria.csv y meteorologia_original.csv.
  carpeta_salida: por defecto ./salidas (fuera del control de versiones).
Salida: resultados.json, tablas auxiliares y el artefacto Ridge (no desplegado).
"""
import json, hashlib, warnings, sys
from pathlib import Path
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")
from sklearn.linear_model import Ridge
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.pipeline import make_pipeline
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
import joblib

BASE = Path(__file__).resolve().parent
DATA = Path(sys.argv[1]) if len(sys.argv) > 1 else BASE.parent / "cierre" / "datos"
OUT = Path(sys.argv[2]) if len(sys.argv) > 2 else BASE / "salidas"
OUT.mkdir(parents=True, exist_ok=True)
SEED = 20261014
GBP = dict(max_iter=100, max_depth=2, max_leaf_nodes=5, min_samples_leaf=15, learning_rate=0.05,
           l2_regularization=5.0, early_stopping=False, random_state=SEED)
SOIL = ["soil_moisture", "soil_lag_6h", "soil_lag_24h", "soil_mean_24h", "hour_sin", "hour_cos"]
LAGS = ["soil_lag_6h", "soil_lag_24h", "soil_mean_24h"]
DHT = ["air_temperature", "air_humidity"]
MET = ["weather_temp_max_c", "weather_temp_mean_c", "weather_humidity_mean_pct", "weather_humidity_min_pct",
       "weather_wind_mean_kmh", "weather_wind_max_kmh", "weather_precipitation_mm",
       "weather_solar_radiation_mj_m2", "weather_et0_mm", "weather_vpd_max_kpa"]
SAT = ["sat_ndvi_mean", "sat_ndmi_mean"]
ALPHAS = (0.1, 1, 3, 10, 30, 100)
UMBRAL = 30.0
TZ = "America/Argentina/San_Juan"
OFICIAL = "2026-10-24 19:00"
CORTES = ["2026-10-23 19:00", "2026-10-24 19:00", "2026-10-25 07:00", "2026-10-25 19:00", "2026-10-26 19:00"]

p = pd.read_csv(DATA / "pares_24h.csv", parse_dates=["timestamp", "target_timestamp"])
Y, S0 = "soil_moisture_t_plus_24h", "soil_moisture"
R = {}

def met(y, yh, per=None):
    y, yh = np.asarray(y, float), np.asarray(yh, float)
    d = dict(n=int(len(y)), mae=float(mean_absolute_error(y, yh)),
             rmse=float(np.sqrt(mean_squared_error(y, yh))), r2=float(r2_score(y, yh)) if len(y) > 1 else None)
    if per is not None:
        b_mae, b_rmse = mean_absolute_error(y, per), np.sqrt(mean_squared_error(y, per))
        d["mejora_mae_pct"] = float(100 * (1 - d["mae"] / b_mae))
        d["habilidad_rmse"] = float(1 - d["rmse"] / b_rmse)
    return d

def ridge(a): return make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), Ridge(alpha=a))
def rf(): return make_pipeline(SimpleImputer(strategy="median"),
                               RandomForestRegressor(n_estimators=300, max_depth=4, min_samples_leaf=10, random_state=SEED))
def gb(): return HistGradientBoostingRegressor(**GBP)

def alpha_interno(tr, feats=SOIL):
    """Origen movil dentro del entrenamiento; la prueba no interviene."""
    best, bv = None, np.inf
    for a in ALPHAS:
        e = []
        for _, r in tr.iterrows():
            h = tr[tr.target_timestamp < r.timestamp]
            if len(h) < 24: continue
            m = ridge(a).fit(h[feats], h[Y] - h[S0])
            e.append(abs(r[Y] - (r[S0] + m.predict(r[feats].to_frame().T.astype(float))[0])))
        if e and np.mean(e) < bv: best, bv = a, float(np.mean(e))
    return best, bv

def split(corte, horas=72):
    fz = pd.Timestamp(corte, tz="UTC")
    tr = p[p.target_timestamp < fz].copy()
    te = p[(p.timestamp > fz) & (p.timestamp <= fz + pd.Timedelta(hours=horas))].copy()
    return tr, te

def usable(cols, tr):  # GB/RF: omite columnas sin ningun valor en el entrenamiento
    return [c for c in cols if tr[c].notna().any()]

def predecir(tr, te, alpha, feats=SOIL):
    per = te[S0].values
    f = usable(feats, tr)
    out = {
        "Persistencia": per,
        "Media del entrenamiento": np.full(len(te), tr[Y].mean()),
        "Ridge (nivel)": ridge(alpha).fit(tr[f], tr[Y]).predict(te[f]),
        "Ridge (variación)": per + ridge(alpha).fit(tr[f], tr[Y] - tr[S0]).predict(te[f]),
        "Bosque aleatorio (nivel)": rf().fit(tr[f], tr[Y]).predict(te[f]),
        "Bosque aleatorio (variación)": per + rf().fit(tr[f], tr[Y] - tr[S0]).predict(te[f]),
        "Gradient boosting (nivel)": gb().fit(tr[f], tr[Y]).predict(te[f]),
        "Gradient boosting (variación)": per + gb().fit(tr[f], tr[Y] - tr[S0]).predict(te[f]),
    }
    return out

# ---------------------------------------------------------------- 1. Bloque fijo oficial
tr, te = split(OFICIAL)
a_of, a_of_mae = alpha_interno(tr)
pred = predecir(tr, te, a_of)
per = te[S0].values; y = te[Y].values
dia = te.target_timestamp.dt.tz_convert(TZ).dt.date.astype(str).values
R["oficial"] = dict(corte_utc=OFICIAL, n_entrenamiento=int(len(tr)), n_prueba=int(len(te)),
                    alpha=a_of, alpha_mae_interno=a_of_mae,
                    rango_objetivo_entrenamiento=[float(tr[Y].min()), float(tr[Y].max())],
                    rango_objetivo_prueba=[float(te[Y].min()), float(te[Y].max())],
                    modelos={k: met(y, v, per) for k, v in pred.items()})
# por dia
pd_rows = {}
for d in sorted(set(dia)):
    m = dia == d
    pd_rows[d] = {"n": int(m.sum()), **{k: float(mean_absolute_error(y[m], v[m])) for k, v in pred.items()}}
R["oficial"]["por_dia"] = pd_rows
# dejar un dia afuera
lodo = {}
for d in sorted(set(dia)):
    m = dia != d
    lodo[d] = {k: float(1 - np.sqrt(mean_squared_error(y[m], pred[k][m])) / np.sqrt(mean_squared_error(y[m], per[m])))
               for k in ("Ridge (variación)", "Gradient boosting (nivel)")}
R["oficial"]["sin_un_dia_habilidad"] = lodo
serie_oficial = pd.DataFrame(dict(origen=te.timestamp.values, objetivo=te.target_timestamp.values, y=y, per=per,
                                  gb=pred["Gradient boosting (nivel)"], ridge=pred["Ridge (variación)"]))

# ---------------------------------------------------------------- 2. Cinco cortes
agg = {}; cortes_out = []; dias_corte = []
for c in CORTES:
    tr_c, te_c = split(c)
    a_c, _ = alpha_interno(tr_c)
    pr = predecir(tr_c, te_c, a_c)
    yc, pc = te_c[Y].values, te_c[S0].values
    cortes_out.append(dict(corte_utc=c, n_entrenamiento=int(len(tr_c)), n_prueba=int(len(te_c)), alpha=a_c,
                           modelos={k: met(yc, v, pc) for k, v in pr.items()}))
    for k, v in pr.items():
        agg.setdefault(k, {"y": [], "p": [], "per": []})
        agg[k]["y"].append(yc); agg[k]["p"].append(v); agg[k]["per"].append(pc)
    dc = te_c.target_timestamp.dt.tz_convert(TZ).dt.date.astype(str).values
    for d in sorted(set(dc)):
        m = dc == d
        row = dict(corte=c, dia=d, n=int(m.sum()))
        for k, v in pr.items(): row[k] = float(mean_absolute_error(yc[m], v[m]))
        dias_corte.append(row)
agg_out = {}
for k, v in agg.items():
    yy, pp, pe = (np.concatenate(v[x]) for x in ("y", "p", "per"))
    agg_out[k] = met(yy, pp, pe)
    agg_out[k]["gana_dias_corte"] = int(sum(r[k] < r["Persistencia"] for r in dias_corte)) if k != "Persistencia" else None
R["multicorte"] = dict(cortes=cortes_out, agregado=agg_out, n_dias_corte=len(dias_corte), dias_corte=dias_corte)

# ---------------------------------------------------------------- 3. Ablacion
abl = {}
for nombre, feats in [("Suelo y hora", SOIL), ("Suelo, hora y DHT22", SOIL + DHT),
                      ("Suelo, hora y meteorología", SOIL + MET), ("Integración disponible", SOIL + DHT + MET + SAT)]:
    res = {}
    # oficial
    f = usable(feats, tr)
    res["oficial_ridge"] = met(y, per + ridge(a_of).fit(tr[f], tr[Y] - tr[S0]).predict(te[f]), per)
    res["oficial_gb"] = met(y, gb().fit(tr[f], tr[Y]).predict(te[f]), per)
    # agregado 5 cortes (alpha del corte con SOIL)
    ys, prs, pgs, pes = [], [], [], []
    for c, co in zip(CORTES, cortes_out):
        tr_c, te_c = split(c); f = usable(feats, tr_c)
        pc = te_c[S0].values
        prs.append(pc + ridge(co["alpha"]).fit(tr_c[f], tr_c[Y] - tr_c[S0]).predict(te_c[f]))
        pgs.append(gb().fit(tr_c[f], tr_c[Y]).predict(te_c[f]))
        ys.append(te_c[Y].values); pes.append(pc)
    yy, pe = np.concatenate(ys), np.concatenate(pes)
    res["multicorte_ridge"] = met(yy, np.concatenate(prs), pe)
    res["multicorte_gb"] = met(yy, np.concatenate(pgs), pe)
    abl[nombre] = res
R["ablacion"] = abl

# ---------------------------------------------------------------- 4. Diagnostico del error
dabs = (p[Y] - p[S0]).abs()
orden = dabs.sort_values(ascending=False)
top10 = orden.iloc[: int(np.ceil(0.10 * len(orden)))]
R["diagnostico"] = dict(
    cambio_24h=dict(n=int(len(dabs)), media=float(dabs.mean()), mediana=float(dabs.median()),
                    p75=float(dabs.quantile(.75)), p90=float(dabs.quantile(.90)), maximo=float(dabs.max()),
                    pares_cambio_mayor_10=int((dabs > 10).sum()), pares_cambio_menor_5=int((dabs < 5).sum()),
                    pct_cambio_total_del_10pct_mayor=float(100 * top10.sum() / dabs.sum())),
)
# en el bloque oficial: completos vs incompletos (mismo modelo Ridge variacion, sin reentrenar)
completo = te[LAGS].notna().all(axis=1).values
rv = pred["Ridge (variación)"]
R["diagnostico"]["oficial_por_completitud"] = dict(
    completas=dict(n=int(completo.sum()), mae_ridge=float(mean_absolute_error(y[completo], rv[completo])),
                   mae_persistencia=float(mean_absolute_error(y[completo], per[completo]))),
    incompletas=dict(n=int((~completo).sum()), mae_ridge=float(mean_absolute_error(y[~completo], rv[~completo])),
                     mae_persistencia=float(mean_absolute_error(y[~completo], per[~completo]))))
# cambio grande vs chico: distribucion en entrenamiento y en prueba
def stats_cambio(df):
    c = (df[Y] - df[S0]).abs()
    return dict(n=int(len(c)), media=float(c.mean()), mediana=float(c.median()),
                pct_mayor_10=float(100 * (c > 10).mean()), pct_menor_5=float(100 * (c < 5).mean()))
R["diagnostico"]["cambio_entrenamiento_oficial"] = stats_cambio(tr)
R["diagnostico"]["cambio_prueba_oficial"] = stats_cambio(te)
cambio_all = (p[Y] - p[S0]).abs().values
yp_all, per_all = p[Y].values, p[S0].values
R["diagnostico"]["persistencia_por_regimen_153"] = dict(
    cambio_hasta_10=dict(n=int((cambio_all <= 10).sum()), mae=float(mean_absolute_error(yp_all[cambio_all <= 10], per_all[cambio_all <= 10]))),
    cambio_mayor_10=dict(n=int((cambio_all > 10).sum()), mae=float(mean_absolute_error(yp_all[cambio_all > 10], per_all[cambio_all > 10]))))

# ---------------------------------------------------------------- 5. Decision de riego
def acierto(yv, pv):
    real, pr_ = yv < UMBRAL, pv < UMBRAL
    return dict(acierto_pct=float(100 * (real == pr_).mean()), riega_de_mas=int((pr_ & ~real).sum()),
                riega_de_menos=int((~pr_ & real).sum()), requerian_riego=int(real.sum()), n=int(len(yv)))
R["decision"] = dict(umbral=UMBRAL, oficial={k: acierto(y, pred[k]) for k in
                     ("Persistencia", "Media del entrenamiento", "Ridge (variación)", "Gradient boosting (nivel)")})
yy = np.concatenate(agg["Persistencia"]["y"])
R["decision"]["multicorte"] = {k: acierto(yy, np.concatenate(agg[k]["p"])) for k in
                               ("Persistencia", "Media del entrenamiento", "Ridge (variación)", "Gradient boosting (nivel)")}
rng = np.random.default_rng(7)
curva = []
for mae_obj in (1, 2, 3, 5, 8, 12, 15, 20, 30, 40):
    accs = [((np.clip(yy + rng.laplace(0, mae_obj, len(yy)), 0, 100) < UMBRAL) == (yy < UMBRAL)).mean()
            for _ in range(500)]
    curva.append(dict(mae=mae_obj, acierto_pct=float(100 * np.mean(accs))))
R["decision"]["curva_mae_acierto"] = curva

# ---------------------------------------------------------------- 6. Interpolacion de huecos (sugerencia de la catedra)
s = pd.read_csv(DATA / "serie_horaria.csv", parse_dates=["timestamp"]).sort_values("timestamp").set_index("timestamp").asfreq("h")
real = s.soil_moisture.copy()
g = real.isna().astype(int).groupby(real.notna().cumsum()).sum(); g = g[g > 0]
interp = dict(horas=int(len(s)), medidas=int(real.notna().sum()), faltantes=int(real.isna().sum()),
              tramos=int(len(g)), tramos_1h=int((g == 1).sum()), tramos_2h=int((g == 2).sum()),
              tramos_3a6h=int(((g >= 3) & (g <= 6)).sum()), tramos_mas_6h=int((g > 6).sum()),
              tramo_max_h=int(g.max()), horas_en_tramos_mas_6h=int(g[g > 6].sum()), resultados=[])
FZ = pd.Timestamp(OFICIAL, tz="UTC")
for mg in (0, 1, 2, 3, 6, 12):
    soil = real if mg == 0 else real.interpolate(method="time", limit=mg, limit_area="inside")
    d = pd.DataFrame(dict(soil_moisture=soil))
    d["soil_lag_6h"] = soil.shift(6); d["soil_lag_24h"] = soil.shift(24)
    d["soil_mean_24h"] = soil.rolling(24, min_periods=24).mean()
    hh = d.index.hour; d["hour_sin"] = np.sin(2 * np.pi * hh / 24); d["hour_cos"] = np.cos(2 * np.pi * hh / 24)
    d["y"] = real.shift(-24)
    d = d[real.notna() & d.y.notna()]
    trd = d[(d.index + pd.Timedelta(hours=24)) < FZ]
    ted = d[(d.index > FZ) & (d.index <= FZ + pd.Timedelta(hours=72))]
    yd, pdd = ted.y.values, ted.soil_moisture.values
    interp["resultados"].append(dict(
        max_hueco_h=mg, pares=int(len(d)), valores_interpolados=int((real.isna() & soil.notna()).sum()),
        pares_con_lag24=int(d.soil_lag_24h.notna().sum()), pares_con_media24=int(d.soil_mean_24h.notna().sum()),
        ridge=met(yd, pdd + ridge(a_of).fit(trd[SOIL], trd.y - trd.soil_moisture).predict(ted[SOIL]), pdd),
        gb=met(yd, gb().fit(trd[SOIL], trd.y).predict(ted[SOIL]), pdd)))
R["interpolacion"] = interp

# ---------------------------------------------------------------- 7. Artefacto final (Ridge variacion, 153 pares)
a_fin, _ = alpha_interno(p)
art = ridge(a_fin).fit(p[SOIL], p[Y] - p[S0])
joblib.dump(dict(modelo=art, variables=SOIL, objetivo="humedad(t+24h) - humedad(t)", alpha=a_fin,
                 n_pares=int(len(p)), semilla=SEED), OUT / "modelo_ridge_variacion_153.joblib")
R["artefacto"] = dict(familia="Ridge sobre la variación a 24 h, con imputación por mediana de rezagos",
                      alpha=a_fin, n_pares=int(len(p)),
                      sha256=hashlib.sha256(open(OUT / "modelo_ridge_variacion_153.joblib", "rb").read()).hexdigest(),
                      desplegado=False)

# ---------------------------------------------------------------- 8. Simulacion declarada
sv = pd.read_csv(DATA / "serie_horaria.csv", parse_dates=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
sv = sv[sv.soil_moisture.notna()].reset_index(drop=True)
dd = sv.soil_moisture.diff(); dt = sv.timestamp.diff().dt.total_seconds() / 3600
sec = dd[(dt.between(.9, 1.1)) & (dd < 0)]
k_sec = float(-sec.median())
met_df = pd.read_csv(DATA / "meteorologia_original.csv")
et0 = met_df["et0_mm"].dropna().to_numpy()
rs = np.random.default_rng(20261028)
DIAS, VOL, DOSIS = 120, 40.0, 1.5
n = DIAS * 24; e0 = rs.choice(et0, DIAS)
th = np.empty(n); rg = np.zeros(n); et = np.empty(n); th[0] = 55.0
for t in range(1, n):
    hora = t % 24; f_h = 0.4 + 0.6 * max(0.0, np.sin(np.pi * (hora - 6) / 12))
    et[t] = e0[t // 24] * f_h / 12.0
    x = th[t - 1] - k_sec * et[t] / (et0.mean() / 12.0)
    if x < UMBRAL and hora % 2 == 0:
        x += (DOSIS / VOL) * 100 * 1.6; rg[t] = DOSIS
    th[t] = float(np.clip(x + rs.normal(0, 0.35), 0, 100))
et[0] = et[1]
sm = pd.DataFrame(dict(soil_moisture=th, riego=rg, et=et))
sm["soil_lag_6h"] = sm.soil_moisture.shift(6); sm["soil_lag_24h"] = sm.soil_moisture.shift(24)
sm["soil_mean_24h"] = sm.soil_moisture.rolling(24).mean()
hh = np.arange(n) % 24; sm["hour_sin"] = np.sin(2 * np.pi * hh / 24); sm["hour_cos"] = np.cos(2 * np.pi * hh / 24)
sm[Y] = sm.soil_moisture.shift(-24); sm = sm.dropna().reset_index(drop=True)
cut = int(len(sm) * .7); trs, tes = sm.iloc[:cut], sm.iloc[cut + 24:]
ps = tes.soil_moisture.values; ys = tes[Y].values
sim_m = {"Persistencia": met(ys, ps),
         "Ridge (variación)": met(ys, ps + ridge(30).fit(trs[SOIL], trs[Y] - trs.soil_moisture).predict(tes[SOIL]), ps),
         "Gradient boosting (nivel)": met(ys, gb().fit(trs[SOIL], trs[Y]).predict(tes[SOIL]), ps)}
R["simulacion"] = dict(declarada_como_sintetica=True, dias=DIAS, horas=n, riegos=int((rg > 0).sum()),
                       litros=float(rg.sum()), tasa_secado_mediana_real=k_sec, n_tasa=int(len(sec)),
                       et0_fechas=int(len(et0)), et0_media=float(et0.mean()),
                       n_entrenamiento=int(len(trs)), n_prueba=int(len(tes)),
                       humedad_min=float(th.min()), humedad_max=float(th.max()), modelos=sim_m)
sim_series = sm.iloc[cut + 24: cut + 24 + 24 * 10].copy()

# ---------------------------------------------------------------- 9. Equivalencia agronomica
R["escala"] = dict(area_maqueta_m2=0.20, volumen_sustrato_l=40.0, area_cepa_m2=3.0, factor=15.0,
                   dosis_maqueta_l=1.5, lamina_mm=7.5, dosis_cepa_l=22.5, cepas_ha=round(10000 / 3.0),
                   m3_por_ha_por_evento=75.0, apertura_s=round(1.5 / 3.9 * 60, 1))

json.dump(R, open(OUT / "resultados.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2, default=str)
serie_oficial.to_csv(OUT / "serie_oficial.csv", index=False)
pd.DataFrame(dias_corte).to_csv(OUT / "dias_corte.csv", index=False)
sim_series.to_csv(OUT / "simulacion_muestra.csv", index=False)
dabs.to_frame("cambio_abs_24h").to_csv(OUT / "cambio_24h.csv", index=False)
print("ok")
