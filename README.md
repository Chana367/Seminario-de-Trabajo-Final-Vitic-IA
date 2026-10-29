# Vitic AI (VitiAlert)

Sistema de soporte de decisiones para la gestión hídrica vitivinícola en San Juan. Integra un nodo IoT de bajo costo con meteorología y teledetección satelital, y evalúa un pronóstico de la humedad del suelo a 24 horas.

Código del Trabajo Final de Grado *«Vitic AI: sistema de soporte de decisiones para la gestión hídrica vitivinícola en San Juan a partir de la integración de datos IoT, meteorológicos y satelitales»*, Licenciatura en Ciencia de Datos, Universidad del Gran Rosario (2026).

- **Autores:** Jorge Mathias Sosa, Axel Nahuel Ruiz Valdez y Francisco Eduardo Paredes Fonseca.
- **Director:** Lic. Germán Giro.

## Componentes

| Carpeta | Responsabilidad |
| --- | --- |
| [backend](backend/README.md) | API Spring Boot y PostgreSQL. Recibe y valida la telemetría, marca su calidad, reconstruye los eventos de riego y exporta el dataset horario. |
| [satellite-api](satellite-api/README.md) | VitiAlert IA, API FastAPI para GOES-19 y Sentinel-2, y el Data Miner meteorológico. |
| [firmware](firmware/README.md) | Programa del ESP32 en modo maqueta, con bomba y simulador de viento, y plantilla de configuración. |
| [analysis](analysis/README.md) | Pronóstico de humedad del suelo a 24 h en tres etapas: corte del 22/10, protocolo de cierre del 28/10 y ampliación. |
| [research](research/README.md) | Recolección histórica y experimentos de construcción de datasets, separados de producción. |
| [docs](docs/arquitectura.md) | Arquitectura, datos, despliegue, verificación y publicación. |
| `deploy`, `tools`, `.github/workflows` | Definición de despliegue, verificador del repositorio, pruebas automáticas y sincronización diaria. |

El ESP32 envía telemetría a `POST /api/data`. El backend guarda las lecturas y devuelve la orden de válvula en esa respuesta. El Data Miner importa la meteorología a diario y solicita el refresco satelital. El análisis se ejecuta por separado y no despliega ningún controlador de riego.

## Resultados del trabajo

- **Campaña:** cerró el 28/10/2026 a las 16:00 con 21.180 lecturas del nodo, 233 horas utilizables de humedad del suelo y 153 pares con objetivo medido a 24 horas.
  - Hasta el 22/10 la maqueta no tuvo agua.
  - Desde esa fecha registró 333 riegos con volumen positivo, en un circuito que recircula.
- **Bloque fijo:** Ridge sobre la variación redujo el error absoluto medio de 49,88 puntos (persistencia) a 32,85.
- **Cinco cortes:** el error agregado fue de 30,24 frente a 44,29, con mejora en 13 de 15 combinaciones de corte y fecha.
- **Ablación:** la meteorología y el satélite no mejoraron la estimación, porque en la campaña no tuvieron variación suficiente.
- **Diagnóstico:** el modelo se entrenó en un régimen sin agua (cambio mediano de 1 punto en 24 h) y se evaluó en otro con agua e intervenciones manuales (51 puntos).
- **Conclusión:** la hipótesis queda apoyada de manera parcial. El aprendizaje supervisado supera de forma consistente a la persistencia, pero la mejora no proviene de la integración multimodal y su magnitud no alcanza un nivel operativo.

El detalle y la reproducción están en [analysis](analysis/README.md).

## Desarrollo

- Backend: Java 21, Maven y PostgreSQL. Las pruebas utilizan H2 en memoria.
- API satelital: Python 3.11 en un entorno independiente.
- Análisis e investigación: Python 3.12 en otro entorno independiente.
- Firmware: soporte ESP32, ArduinoJson 7 y DHT de Adafruit.

Los comandos de instalación y prueba están en el README de cada componente. GitHub Actions ejecuta las pruebas sin acceder a la maqueta ni a producción. La [verificación](docs/verificacion.md) registra las pruebas ejecutadas y sus límites.

## Configuración y publicación

Las plantillas `.env.example` y `secrets.example.h` no contienen credenciales reales. El código del backend lee variables de entorno; un archivo `.env` por sí solo no configura Spring Boot.

No se incluyen datos de campo, volcados de PostgreSQL, artefactos entrenados, entornos virtuales ni resultados de ejecuciones. La publicación del código no modifica los servicios existentes en Render.

Consultar [despliegue](docs/despliegue.md), [datos y modelo](docs/datos-y-modelo.md) y [revisión antes de publicar](docs/publicacion.md).

## Alcance

El sistema registra variables y calcula eventos de riego a partir de la telemetría.

- **Litros:** requieren contraste físico del caudalímetro, y en la maqueta describen circulación, no consumo.
- **Suelo:** su escala requiere calibración con el sustrato.
- **Viento:** el de la maqueta lo produce un motor y no es una medición de viento natural.
- **Métricas:** no demuestran ahorro de agua ni generalización agronómica.

Los datos meteorológicos de grilla, las observaciones satelitales, las mediciones del ESP32 y las simulaciones mantienen identificada su procedencia.
