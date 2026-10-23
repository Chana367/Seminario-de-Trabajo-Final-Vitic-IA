# Despliegue

Este repositorio agrupa componentes antes separados. Subirlo a GitHub no cambia las conexiones ni los despliegues actuales. La configuración de Render debe revisarse explícitamente antes de conectar un servicio a este repositorio.

## Servicios existentes

En Render, seleccionar el repositorio y rama correctos y configurar:

| Servicio | Root Directory | Dockerfile | Docker Build Context |
| --- | --- | --- | --- |
| Backend | `backend` | `./Dockerfile` | `.` |
| API satelital | `satellite-api` | `./Dockerfile` | `.` |

Los valores Docker se interpretan respecto del directorio raíz del servicio. Referencia: [Render, monorepos](https://render.com/docs/monorepo-support).

Conservar las variables y la base existentes. No crear otra base ni aplicar un Blueprint de recursos nuevos como sustituto de una migración. El [ejemplo de Blueprint](../deploy/render.example.yaml) no es leído automáticamente como `render.yaml` y no certifica la configuración, plan o región actuales.

El backend necesita host, puerto, base, usuario y contraseña válidos. El hostname interno de PostgreSQL requiere conectividad compatible en Render; un fallo DNS no se resuelve modificando tablas. Mantener las migraciones Flyway originales y respaldar antes de cualquier migración deliberada.

## GitHub Actions

- `ci.yml`: pruebas de backend, API y pipelines; no despliega ni controla hardware.
- `data-miner.yml`: importa clima y solicita refresco satelital. Necesita secretos `BACKEND_BASE_URL` y `VITIALERT_API_KEY`.

El Data Miner se ejecuta desde `satellite-api`; su instalación de dependencias es mínima (`requests`). La API completa requiere las dependencias geoespaciales de su propio `requirements.txt`.

Los workflows fijan Ubuntu 24.04, Java 21 y versiones de Python por componente. La programación diaria no garantiza que los proveedores respondan ni que cada ejecución finalice correctamente. Revisar logs y datos recibidos, no solo el color del workflow.

`ML_ENABLED` se mantiene deshabilitado en el ejemplo. El candidato experimental no tiene autorización de despliegue ni un servicio de inferencia implementado en esta carpeta.
