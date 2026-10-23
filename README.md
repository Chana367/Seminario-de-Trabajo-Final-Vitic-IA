# VitiAlert

Prototipo de monitoreo y soporte a la gestión del riego. Integra un nodo ESP32, persistencia de telemetría, fuentes meteorológicas y satelitales, y un análisis experimental de humedad del suelo a 24 horas.

## Componentes

| Carpeta | Responsabilidad |
| --- | --- |
| [backend](backend/README.md) | API Spring Boot, PostgreSQL, calidad de datos y eventos de riego. |
| [satellite-api](satellite-api/README.md) | API FastAPI para GOES/Sentinel y Data Miner meteorológico. |
| [firmware](firmware/README.md) | Programa habitual del ESP32 y plantilla de configuración. |
| [analysis](analysis/README.md) | Preparación horaria, entrenamiento y evaluación temporal sobre suelo medido. |
| [research](research/README.md) | Recolección histórica y experimentos de construcción de datasets, separados de producción. |
| [docs](docs/arquitectura.md) | Arquitectura, contrato de datos y operación. |

El ESP32 envía telemetría a `POST /api/data`. El backend guarda las lecturas y devuelve la orden de válvula en esa respuesta. El Data Miner importa meteorología y solicita el refresco satelital. El entrenamiento se ejecuta por separado y no despliega un controlador de riego.

## Desarrollo

- Backend: Java 21, Maven y PostgreSQL. Las pruebas utilizan H2 en memoria.
- API satelital: Python 3.11 en un entorno independiente.
- Análisis e investigación: Python 3.12 en otro entorno independiente.
- Firmware: soporte ESP32, ArduinoJson 7 y DHT de Adafruit.

Los comandos de instalación y prueba están en el README de cada componente. GitHub Actions ejecuta las pruebas sin acceder a la maqueta ni a producción.

La [verificación local](docs/verificacion.md) registra las pruebas ejecutadas y los límites de esa revisión.

## Configuración y publicación

Las plantillas `.env.example` y `secrets.example.h` no contienen credenciales reales. El código del backend lee variables de entorno; un archivo `.env` por sí solo no configura Spring Boot.

No se incluyen datos de campo, volcados de PostgreSQL, artefactos entrenados, entornos virtuales ni resultados de ejecuciones anteriores. Los datos y modelos generados se mantienen fuera del control de versiones. La publicación del código no modifica los servicios existentes en Render.

Consultar [despliegue](docs/despliegue.md), [datos y modelo](docs/datos-y-modelo.md) y [revisión antes de publicar](docs/publicacion.md).

## Alcance

El sistema registra variables y calcula eventos de riego a partir de la telemetría. Los litros requieren contraste físico del caudalímetro. La escala del suelo requiere calibración con el sustrato. Las métricas de un experimento no demuestran ahorro de agua ni generalización agronómica.

Los datos meteorológicos de grilla, las observaciones satelitales, las mediciones del ESP32 y las simulaciones mantienen identificada su procedencia.
