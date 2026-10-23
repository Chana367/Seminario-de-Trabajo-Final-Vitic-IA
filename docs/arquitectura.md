# Arquitectura

## Flujo de operación

1. El ESP32 lee sensores, mantiene el contador de volumen y envía `POST /api/data`.
2. El backend valida rangos, registra calidad y persiste la lectura en PostgreSQL.
3. Las transiciones de válvula abren o cierran eventos de riego. El volumen se calcula por diferencia del contador cuando es posible.
4. El backend devuelve `abrir_valvula` y `encender_luz` al ESP32 que hizo el POST. No existe un canal de apertura remota independiente en el contrato actual.
5. El nodo aplica la respuesta respetando sus bloqueos locales. Ante fallo de red usa el respaldo local.

El firmware habitual tiene llamadas de red bloqueantes. Los bloqueos por falta de caudal no sustituyen una verificación del cierre físico ni un corte eléctrico independiente.

## Fuentes externas

El Data Miner obtiene clima de Open-Meteo, importa meteorología al backend y solicita refresco satelital. La API satelital consulta GOES-19 y Sentinel-2 independientemente. El backend persiste las observaciones disponibles y evita duplicados de una misma captura.

La consulta `GET /api/nodes/{nodeId}/satellite` consulta VitiAI; no exporta por sí misma la tabla histórica almacenada. Los índices representan el área consultada, no una medición puntual de la maceta.

## Análisis

El pipeline de `analysis` obtiene un corte de solo lectura, prepara series horarias, ajusta Gradient Boosting y evalúa predicciones de humedad a 24 h. Mantiene trazabilidad y produce resultados fuera del código versionado. No existe una automatización de entrenamiento/despliegue en el workflow del Data Miner.

`research` conserva la recolección histórica y escenarios de experimentación separados del pipeline de suelo medido.
