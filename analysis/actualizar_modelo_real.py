"""Snapshot GET y ensayo retrospectivo de suelo real. Nunca escribe en produccion."""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import math
import shutil
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

import joblib
import matplotlib
matplotlib.use('Agg')
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

TZ = 'America/Argentina/Buenos_Aires'
FEATURES = ['soil_moisture', 'soil_lag_6h', 'soil_lag_24h', 'soil_mean_24h', 'hour_sin', 'hour_cos']
TARGET = 'soil_moisture_t_plus_24h'
PARAMS = dict(max_iter=100, max_depth=2, max_leaf_nodes=5, min_samples_leaf=15,
              learning_rate=.05, l2_regularization=5., early_stopping=False, random_state=20261014)


def save_json(path, value):
    def convert(x):
        if isinstance(x, (np.integer, np.floating)):
            return x.item()
        if isinstance(x, (pd.Timestamp, Path)):
            return str(x)
        raise TypeError(type(x).__name__)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False, default=convert), encoding='utf-8')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fetch_pages(base, endpoint, cutoff, folder):
    rows, requests, totals = [], [], []
    page = 0
    while True:
        params = dict(page=page, size=500, **{'from': '2026-09-17T00:00:00Z', 'to': cutoff.isoformat()})
        url = f'{base}/api/nodes/1/{endpoint}?' + urlencode(params)
        with urlopen(url, timeout=45) as response:
            raw = response.read()
        path = folder / f'{endpoint}_{page:03d}.json'
        path.write_bytes(raw)
        body = json.loads(raw)
        requests.append(dict(url=url, file=path.name, sha256=digest(path)))
        totals.append(body['total_elements'])
        rows.extend(body['content'])
        page += 1
        if page >= body['total_pages']:
            break
    if len(set(totals)) != 1 or len(rows) != totals[0] or len({x['id'] for x in rows}) != len(rows):
        raise ValueError('La paginacion cambio durante el snapshot o hay duplicados. Repetir con otro corte.')
    return rows, requests


def load_snapshot(source, destination):
    manifest_path = source/'MANIFIESTO_FUENTES.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    readings, events = [], []
    for item in manifest['requests']:
        filename = item['file']
        if Path(filename).name != filename:
            raise ValueError('Nombre inseguro en snapshot.')
        path = source/filename
        if digest(path) != item['sha256']:
            raise ValueError(f'Snapshot modificado: {filename}')
        body = json.loads(path.read_text(encoding='utf-8'))
        if filename.startswith('telemetry_'):
            readings.extend(body['content'])
        elif filename.startswith('irrigation-events_'):
            events.extend(body['content'])
        else:
            raise ValueError('Fuente inesperada.')
        shutil.copyfile(path,destination/filename)
    shutil.copyfile(manifest_path,destination/manifest_path.name)
    return readings,events,pd.Timestamp(manifest['cutoff_utc']),manifest['requests']


def prepare_hourly(raw, cutoff):
    raw = raw.copy()
    raw['timestamp'] = pd.to_datetime(raw.timestamp, format='mixed', utc=True)
    raw = raw.sort_values(['timestamp', 'id'])
    if raw.id.duplicated().any() or raw.timestamp.gt(cutoff).any():
        raise ValueError('IDs duplicados o registros posteriores al corte.')
    rebuilt = raw.quality_notes.fillna('').str.contains(r'RECONSTRUIDO|SEMISYNTH|SIMULAD', case=False, regex=True)
    measured = raw.loc[~rebuilt].copy()
    measured.index = pd.DatetimeIndex(measured.timestamp)
    soil = pd.to_numeric(measured.humedad_suelo_pct, errors='coerce')
    measured['usable'] = soil.where(soil.between(0, 100, inclusive='neither'))
    measured['clock'] = measured.index
    usable = measured.loc[measured.usable.notna()]
    def internal_gap(series):
        return series.sort_values().diff().dt.total_seconds().max() / 60 if len(series) >= 2 else np.nan
    hourly = usable.resample('h', closed='right', label='right').agg(
        soil_moisture=('usable', 'mean'), sample_count=('usable', 'count'),
        first=('clock', 'min'), last=('clock', 'max'), max_gap_minutes=('clock', internal_gap))
    hourly['covered_minutes'] = (hourly['last'] - hourly['first']).dt.total_seconds() / 60
    grid = pd.date_range(raw.timestamp.min().floor('h'), cutoff.floor('h'), freq='h')
    hourly = hourly.reindex(grid)
    good = (hourly.sample_count.ge(6) & hourly.covered_minutes.ge(45) & hourly.max_gap_minutes.le(10))
    hourly['coverage_usable'] = good
    hourly.loc[~good, 'soil_moisture'] = np.nan
    hourly = hourly.drop(columns=['first', 'last'])
    for lag in (6, 24):
        hourly[f'soil_lag_{lag}h'] = hourly.soil_moisture.reindex(hourly.index - pd.Timedelta(hours=lag)).to_numpy()
    hourly['soil_mean_24h'] = hourly.soil_moisture.rolling(24, min_periods=24).mean()
    local = hourly.index.tz_convert(TZ)
    hourly['hour_sin'] = np.sin(local.hour * 2 * np.pi / 24)
    hourly['hour_cos'] = np.cos(local.hour * 2 * np.pi / 24)
    hourly['target_timestamp'] = hourly.index + pd.Timedelta(hours=24)
    hourly[TARGET] = hourly.soil_moisture.reindex(hourly.target_timestamp).to_numpy()
    hourly.loc[hourly.target_timestamp.gt(cutoff), TARGET] = np.nan
    hourly['origin'] = 'REAL_BACKEND_SOIL_HOURLY_NOT_CALIBRATED_VWC'
    hourly['target_origin'] = 'MEASURED_SOIL_HOURLY_MEAN'
    hourly.index.name = 'timestamp'
    hourly = hourly[hourly.index >= pd.Timestamp('2026-10-01T00:00:00-03:00')]
    stats = dict(reconstructed_rows_excluded=int(rebuilt.sum()),
                 soil_missing_or_saturated_excluded=int(measured.usable.isna().sum()))
    return measured, hourly, stats


def score(y, prediction):
    y, prediction = np.asarray(y, float), np.asarray(prediction, float)
    if not len(y) or not np.isfinite(y).all() or not np.isfinite(prediction).all():
        raise ValueError('Metricas sin vectores finitos.')
    error = prediction - y
    variance = float(np.square(y - y.mean()).sum())
    return dict(n=len(y), mae_pp=float(abs(error).mean()), rmse_pp=float(np.sqrt(np.square(error).mean())),
                r2=float(1 - np.square(error).sum() / variance) if variance > 1e-12 else None,
                target_min=float(y.min()), target_max=float(y.max()))


def eligible_pairs(hourly):
    result = hourly.dropna(subset=['soil_moisture', TARGET]).copy()
    if not (result.target_timestamp - result.index == pd.Timedelta(hours=24)).all():
        raise ValueError('Target fuera de horizonte.')
    return result


def causal_training(pairs, at):
    return pairs[pairs.target_timestamp < at]


def available_features(train):
    # Una columna totalmente vacia no contiene informacion ajustable en ese origen.
    # La decision se toma solo con el entrenamiento, nunca mirando el bloque futuro.
    return [name for name in FEATURES if train[name].notna().any()]


def walk_forward(pairs, minimum=24):
    predictions = []
    for at, row in pairs.iterrows():
        train = causal_training(pairs, at)
        if len(train) < minimum:
            continue
        assert train.target_timestamp.max() < at
        active_features = available_features(train)
        model = HistGradientBoostingRegressor(**PARAMS).fit(train[active_features], train[TARGET])
        predicted = float(np.clip(model.predict(pairs.loc[[at], active_features])[0], 0, 100))
        predictions.append(dict(timestamp=at, target_timestamp=row.target_timestamp, target=float(row[TARGET]),
                                gradient_boosting=predicted, persistence=float(row.soil_moisture),
                                n_train=len(train), last_training_target=train.target_timestamp.max(),
                                active_features='|'.join(active_features)))
    return pd.DataFrame(predictions, columns=['timestamp','target_timestamp','target','gradient_boosting','persistence','n_train','last_training_target','active_features'])


def plot_results(hourly, daily, predictions, out):
    fig, axes = plt.subplots(2, 1, figsize=(12, 7), constrained_layout=True)
    dates = pd.to_datetime(daily.index)
    axes[0].bar(dates, daily.lecturas, color='#215b78')
    axes[0].set(title='Lecturas reales recibidas por día', ylabel='Lecturas')
    x = hourly.index.tz_convert(TZ)
    axes[1].plot(x, hourly.soil_moisture, color='#215b78', lw=1.6)
    axes[1].set(title='Humedad horaria con cobertura suficiente. Los huecos permanecen vacíos', ylabel='Escala relativa del sensor (%)')
    for ax in axes:
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%d/%m'))
        ax.spines[['top','right']].set_visible(False)
        ax.grid(axis='y', alpha=.15)
    fig.suptitle('Cobertura del corte de mediciones de suelo', fontsize=14)
    fig.savefig(out / '01_cobertura_real.png', dpi=160)
    plt.close(fig)
    if not predictions.empty:
        pred = predictions.set_index('target_timestamp')
        groups = list(pred.groupby(pred.index.tz_convert(TZ).strftime('%d/%m')))
        fig, axes = plt.subplots(1,len(groups),figsize=(12,4.8),constrained_layout=True,sharey=True,squeeze=False)
        for ax,(day,group) in zip(axes.flat,groups):
            group = group.reindex(pd.date_range(group.index.min(),group.index.max(),freq='h'))
            x=group.index.tz_convert(TZ)
            ax.plot(x,group.target,label='Suelo medido a +24 h',color='#263238',lw=2,marker='o',ms=4)
            ax.plot(x,group.gradient_boosting,label='Gradient Boosting',color='#215b78',lw=1.7,marker='s',ms=3)
            ax.plot(x,group.persistence,label='Persistencia',color='#d47b28',ls='--',lw=1.3,marker='.',ms=4)
            ax.set(title=f'{day}: {group.target.notna().sum()} predicciones',xlabel='Hora del target, Argentina')
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M',tz=TZ))
            ax.spines[['top','right']].set_visible(False)
            ax.grid(axis='y',alpha=.15)
        axes.flat[0].set_ylabel('Escala relativa del sensor (%)')
        handles,labels=axes.flat[0].get_legend_handles_labels()
        fig.legend(handles,labels,loc='outside lower center',ncol=3,frameon=False)
        fig.suptitle('Predicciones retrospectivas sobre suelo medido. Días con evaluación disponible',fontsize=13)
        fig.savefig(out / '02_predicciones_reales.png', dpi=160)
        plt.close(fig)


def report(out, summary):
    model = summary['metrics'].get('gradient_boosting')
    baseline = summary['metrics'].get('persistence')
    metric_text = 'No hubo filas suficientes para emitir predicciones retrospectivas con el protocolo fijado.'
    if model:
        r2 = 'no definido' if model['r2'] is None else f"{model['r2']:.3f}"
        metric_text = (f"Sobre **{model['n']} predicciones** y **{summary['evaluation_target_days']} días de targets**, "
                       f"Gradient Boosting obtuvo **MAE {model['mae_pp']:.3f} puntos**, RMSE {model['rmse_pp']:.3f} y R² {r2}. "
                       f"Persistencia obtuvo **MAE {baseline['mae_pp']:.3f} puntos** sobre exactamente las mismas filas. "
                       f"Los targets de ese bloque abarcan de {model['target_min']:.2f} a {model['target_max']:.2f} en la escala del sensor.")
        metric_text += (f" El mayor error del candidato fue **{summary['max_absolute_error_pp']:.2f} puntos**. "
                        'El menor MAE global que persistencia describe este bloque concreto y no acredita precisión estable.'
                        if model['mae_pp']<baseline['mae_pp'] else
                        ' El candidato no superó la referencia de persistencia en este bloque.')
        metric_text += '\n\n| Día del target (Argentina) | Predicciones | MAE Gradient Boosting | MAE persistencia |\n|---|---:|---:|---:|\n'
        for item in summary['metrics_by_target_day']:
            metric_text += f"| {item['day']} | {item['n']} | {item['mae_gb']:.3f} | {item['mae_persistence']:.3f} |\n"
        metric_text += '\nLos errores por día muestran si el promedio global oculta diferencias entre condiciones. No se eliminaron los casos de mayor error para mejorar la cifra.'
    text = f'''# Resultados del análisis de humedad del suelo

## Qué se ejecutó

Se procesó un corte del backend y se ejecutó el protocolo de Gradient Boosting con **mediciones reales del suelo**. La ejecución es de solo lectura respecto de producción y no despliega el artefacto.

Las métricas corresponden al origen de datos, variables y período de este corte. No son intercambiables con resultados de escenarios reconstruidos o simulados.

## Datos de este corte

- Corte: **{summary['cutoff_local']}**.
- Registros descargados desde septiembre: **{summary['raw_records']}**. Registros desde el 01/10: **{summary['october_records']}**.
- Última lectura: **{summary['last_reading_local']}**. Días de octubre con al menos una lectura: **{summary['october_days_with_records']}**.
- Horas de suelo con cobertura suficiente desde el 01/10: **{summary['usable_hours']}**.
- Pares medidos de suelo actual y suelo a exactamente 24 h: **{summary['eligible_pairs']}**.
- Temperatura ausente en **{summary['temperature_missing']}** registros descargados. Humedad ambiental ausente en **{summary['humidity_missing']}**.
- Eventos de riego: **{summary['irrigation_events']}**, de los cuales **{summary['positive_recorded_volume_events']}** tienen volumen aplicado positivo registrado. Esto no demuestra ausencia de circulación física.

La tabla `02_datos/horas_reales.csv` conserva los huecos. Las respuestas originales están en `01_fuentes`. Una marca MISSING del DHT no invalida automáticamente el suelo cuando ese sensor sí responde.

## Qué modelo se entrenó

Se mantiene la familia **Gradient Boosting** y el horizonte de **24 horas**. Esta variante recibe seis variables de suelo y horario. Los antecedentes pueden faltar y el estimador los maneja como ausentes. No usa litros sin calibrar, clima diario con posible información futura ni variables satelitales sin serie suficiente. No inventa valores para completar esos campos.

Artefacto final: **{summary['final_model_status']}**, con **{summary['eligible_pairs']} pares** disponibles. El ajuste final usa los pares conocidos al corte. Sus métricas NO se calculan sobre sus propias filas de entrenamiento como si fueran prueba.

## Evaluación retrospectiva

{metric_text}

Cada predicción se obtuvo de un ajuste que utilizaba solo targets anteriores a su hora de emisión. Se conservaron los timestamps, el tamaño del entrenamiento y su última etiqueta para comprobarlo. El modelo se volvió a ajustar en cada origen temporal. No es la evaluación de un único modelo fijo sobre un conjunto ciego.

**Cobertura de evaluación: muy limitada** si no alcanza 24 predicciones y tres días distintos. En este corte: **{summary['evaluation_rows']} predicciones en {summary['evaluation_target_days']} días**. Aunque haya muchas lecturas por minuto, las horas y sus targets cercanos están correlacionados. Un error bajo sobre un tramo corto y estable no demuestra generalización a riegos diferentes ni a un viñedo.

MAE mide puntos de la escala relativa del sensor. No es porcentaje de acierto. El porcentaje del sensor todavía no equivale a contenido volumétrico de agua.

## Alcance de los resultados

El pipeline construye pares horarios, ajusta el candidato cuando hay datos suficientes y evalúa cronológicamente frente a persistencia. Los tamaños, períodos y errores publicados describen únicamente la evaluación disponible.

![Cobertura de las mediciones reales](03_graficos/01_cobertura_real.png)

'''
    if model:
        text += '![Predicciones retrospectivas sobre suelo medido](03_graficos/02_predicciones_reales.png)\n\n'
    text += '''## Qué todavía no demostramos

- Precisión estable sobre un período futuro reservado y diferentes condiciones de riego.
- Consumo físico de agua o ahorro: faltan caudal y volumen contrastados.
- Eficiencia agronómica, respuesta del cultivo o generalización a una parcela productiva.
- Control de la válvula mediante el modelo. La decisión actual sigue siendo local.
- Que los días sin telemetría hayan sido medidos. No se reconstruyeron para esta evaluación.

## Validación pendiente

1. Contrastar el volumen del circuito hidráulico con mediciones físicas por ciclo.
2. Verificar la calibración de suelo y recuperar continuidad. Registrar bomba, presión/configuración e intervenciones con hora.
3. Conservar este artefacto como referencia. Una bomba nueva cambia el régimen físico, por lo que no valida caudales pasados.
4. Congelar un candidato usando exclusivamente etiquetas conocidas antes del período reservado.
5. Guardar predicciones con su hora de emisión, sin reajustar el candidato usando sus respuestas futuras.
6. Evaluar etiquetas conocidas al corte sobre las mismas filas para candidato y persistencia e informar los faltantes.

El protocolo, las tablas de evaluación y el manifiesto acompañan este informe. No se cambian hiperparámetros para favorecer los resultados de este corte.
'''
    (out / 'RESULTADOS.md').write_text(text, encoding='utf-8')


def run(output, base, snapshot=None):
    if output.exists():
        raise FileExistsError('Usar una carpeta de salida nueva para conservar cada corte.')
    for sub in ('01_fuentes','02_datos','03_graficos','04_modelo'):
        (output / sub).mkdir(parents=True, exist_ok=True)
    cutoff = pd.Timestamp(datetime.now(timezone.utc)).floor('s')
    sources = output / '01_fuentes'
    if snapshot:
        readings,events,cutoff,all_requests = load_snapshot(snapshot,sources)
    else:
        readings, requests = fetch_pages(base, 'telemetry', cutoff, sources)
        events, event_requests = fetch_pages(base, 'irrigation-events', cutoff, sources)
        all_requests=requests+event_requests
        save_json(sources/'MANIFIESTO_FUENTES.json', dict(cutoff_utc=cutoff.isoformat(),requests=all_requests))
    raw = pd.DataFrame(readings)
    if raw.empty:
        raise ValueError('No hay lecturas originales.')
    measured, hourly, quality_stats = prepare_hourly(raw, cutoff)
    raw.to_csv(output / '02_datos/telemetria_original.csv', index=False)
    pd.DataFrame(events).to_csv(output / '02_datos/eventos_originales.csv', index=False)
    hourly.to_csv(output / '02_datos/horas_reales.csv')
    pairs = eligible_pairs(hourly)
    pairs.to_csv(output / '02_datos/pares_24h_reales.csv')
    predictions = walk_forward(pairs)
    if not predictions.empty:
        predictions['error_gb_pp']=predictions.gradient_boosting-predictions.target
        predictions['error_persistence_pp']=predictions.persistence-predictions.target
    predictions.to_csv(output / '02_datos/predicciones_retrospectivas.csv', index=False)
    october = measured[measured.index >= pd.Timestamp('2026-10-01T00:00:00-03:00')].copy()
    october['day'] = october.index.tz_convert(TZ).strftime('%Y-%m-%d')
    daily = october.groupby('day').agg(lecturas=('id','size'), temperatura_presente=('temperatura_ambiente_c','count'),
                                     humedad_ambiente_presente=('humedad_relativa_pct','count'))
    daily = daily.reindex(pd.date_range('2026-10-01', cutoff.tz_convert(TZ).normalize().tz_localize(None), freq='D').strftime('%Y-%m-%d'), fill_value=0)
    daily.index.name = 'fecha_argentina'
    daily.to_csv(output / '02_datos/cobertura_diaria.csv')
    metrics = {}
    target_days = 0
    by_day=[]
    if not predictions.empty:
        metrics = {name: score(predictions.target, predictions[name]) for name in ('gradient_boosting','persistence')}
        target_days = int(pd.to_datetime(predictions.target_timestamp, utc=True).dt.tz_convert(TZ).dt.date.nunique())
        for day,group in predictions.groupby(pd.to_datetime(predictions.target_timestamp,utc=True).dt.tz_convert(TZ).dt.strftime('%Y-%m-%d')):
            by_day.append(dict(day=day,n=len(group),mae_gb=float(group.error_gb_pp.abs().mean()),mae_persistence=float(group.error_persistence_pp.abs().mean())))
        pd.DataFrame(by_day).to_csv(output/'02_datos/metricas_por_dia.csv',index=False)
    final_status = 'NO_ENTRENADO_MENOS_DE_48_PARES'
    if len(pairs) >= 48:
        final_features = available_features(pairs)
        final = HistGradientBoostingRegressor(**PARAMS).fit(pairs[final_features], pairs[TARGET])
        payload = dict(estimator=final, features=final_features, target=TARGET, horizon_hours=24,
                       origin='REAL_SOIL_MEASUREMENTS_NOT_RECONSTRUCTED', cutoff_utc=cutoff.isoformat(),
                       training_rows=len(pairs), latest_training_target=str(pairs.target_timestamp.max()),
                       independent_field_validation=False, deployment_authorized=False, params=PARAMS)
        artifact = output / '04_modelo/gradient_boosting_suelo_real.joblib'
        joblib.dump(payload, artifact)
        reloaded = joblib.load(artifact)
        assert np.allclose(final.predict(pairs[final_features].tail(5)), reloaded['estimator'].predict(pairs[final_features].tail(5)))
        final_status = 'ENTRENADO_OFFLINE_NO_DESPLEGADO'
    summary = dict(cutoff_utc=cutoff.isoformat(), cutoff_local=cutoff.tz_convert(TZ).isoformat(),
                   raw_records=len(raw), october_records=len(october), last_reading_local=measured.index.max().tz_convert(TZ).isoformat(),
                   october_days_with_records=int((daily.lecturas > 0).sum()), usable_hours=int(hourly.soil_moisture.notna().sum()),
                   eligible_pairs=len(pairs), temperature_missing=int(raw.temperatura_ambiente_c.isna().sum()),
                   humidity_missing=int(raw.humedad_relativa_pct.isna().sum()), irrigation_events=len(events),
                   positive_recorded_volume_events=sum(e.get('volumen_aplicado_l') is not None and float(e['volumen_aplicado_l']) > 0 for e in events),
                   evaluation_rows=len(predictions), evaluation_target_days=target_days, metrics=metrics,
                   metrics_by_target_day=by_day,
                   max_absolute_error_pp=float(predictions.error_gb_pp.abs().max()) if not predictions.empty else None,
                   evaluation_coverage_status='MUY_LIMITADA_MENOS_DE_24_PREDICCIONES_O_3_DIAS' if len(predictions)<24 or target_days<3 else 'RETROSPECTIVA_NO_INDEPENDIENTE',
                   final_model_status=final_status, production_modified=False, independent_field_validation=False,
                   recent_prediction_emitted=False, excluded_inputs=['uncalibrated_irrigation','historical_daily_weather','satellite'], **quality_stats)
    save_json(output / 'RESUMEN_RESULTADOS.json', summary)
    save_json(output / 'MANIFIESTO_EJECUCION.json', dict(created_utc=datetime.now(timezone.utc).isoformat(), requests=all_requests,
              feature_contract=FEATURES, params=PARAMS, walk_forward_min_training=24, final_min_pairs=48,
              production_modified=False, code_sha256=digest(Path(__file__)),
              protocol_sha256=digest(Path(__file__).parent/'PROTOCOLO.md'),
              packages={name:importlib.metadata.version(name) for name in ('numpy','pandas','scikit-learn','matplotlib','joblib')}))
    plot_results(hourly, daily, predictions, output/'03_graficos')
    report(output, summary)
    save_json(output / 'SHA256_RESULTADOS.json', {p.relative_to(output).as_posix():digest(p) for p in sorted(output.rglob('*')) if p.is_file()})
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--backend-url', default='https://vitialert-backend.onrender.com')
    parser.add_argument('--snapshot',type=Path,help='Repetir sin red desde 01_fuentes de un corte conservado.')
    args = parser.parse_args()
    run(args.output, args.backend_url.rstrip('/'),args.snapshot)
