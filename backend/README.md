# Backend

API Spring Boot 3.3.5 con Java 21, Spring Data JPA, PostgreSQL y Flyway.

## Ejecutar

Crear una base PostgreSQL de desarrollo vacía. Configurar las variables de [`.env.example`](.env.example) en el proceso que ejecuta Java. No apuntar las pruebas manuales de desarrollo a una base productiva.

```powershell
mvn test
mvn spring-boot:run
```

```bash
docker build -t vitialert-backend .
docker run --rm --env-file .env -p 8080:8080 vitialert-backend
```

El segundo ejemplo usa el lector de archivos de entorno de Docker. Las migraciones Flyway se ejecutan al arrancar. No modificar migraciones ya aplicadas: incluso cambiar sus comentarios puede alterar el checksum registrado.

## Rutas

| Método y ruta | Uso |
| --- | --- |
| `POST /api/data` | Ingesta del ESP32 y respuesta con `abrir_valvula`/`encender_luz`. |
| `GET /api/nodes` | Nodos registrados. |
| `GET /api/nodes/{nodeId}/telemetry/latest` | Última lectura. |
| `GET /api/nodes/{nodeId}/telemetry` | Lecturas paginadas por período. |
| `GET /api/nodes/{nodeId}/irrigation-events` | Eventos derivados de transiciones de válvula. |
| `GET /api/nodes/{nodeId}/features` | Variables de una hora. |
| `GET /api/nodes/{nodeId}/satellite` | Consulta de contexto a VitiAI, no listado histórico persistido. |
| `GET /api/dataset/export` | Exportación del dataset del backend. |
| `POST /api/weather/import` | Importación meteorológica. |
| `POST /api/satellite/refresh` | Persistencia de observaciones satelitales disponibles. |
| `GET /health` | Estado de la aplicación e integraciones habilitadas. |

Swagger: `/swagger-ui.html`. El contrato detallado está en `/v3/api-docs`.

## Comportamiento

- Los timestamps de telemetría se asignan en UTC al recibir cada POST.
- Los faltantes se conservan como `null` y se marcan `MISSING`; una lectura parcial puede persistirse.
- Las transacciones incluyen el acceso necesario a relaciones JPA diferidas. Open Session in View permanece desactivado.
- `ML_ENABLED=false` conserva la decisión local informada por el ESP32. El modelo de `analysis` no se publica automáticamente en una API de inferencia.
- `/health` no certifica por sí solo conexión a la base ni disponibilidad de los proveedores externos.

Las pruebas de `src/test` utilizan el perfil `test`, con H2 en memoria e integraciones externas deshabilitadas o simuladas.
