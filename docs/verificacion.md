# Verificación de la copia de código

## Revisión del 29/10/2026

Revisión local sin desplegar servicios ni accionar hardware, después de incorporar el firmware final, el protocolo de cierre y la ampliación del análisis.

| Componente | Comprobación | Resultado |
| --- | --- | --- |
| Backend | Maven, Java 21, perfil de pruebas con H2 | 34 pruebas definidas; código sin cambios desde la revisión del 23/10, en la que se aprobaron todas. No se reejecutó en esta revisión porque el entorno no tenía acceso al repositorio central de Maven; GitHub Actions las ejecuta en cada envío. |
| API satelital y Data Miner | Pytest 8.3 en Python 3.11, proveedores simulados | 72 pruebas aprobadas. |
| Análisis, corte del 22/10 | Unittest en Python 3.12 | 10 pruebas aprobadas. |
| Análisis, protocolo de cierre | Unittest en Python 3.12 | 10 pruebas aprobadas. |
| Investigación histórica | Unittest en Python 3.12, datos de prueba temporales | 14 pruebas aprobadas. |
| Verificador del repositorio | Archivos temporales válidos e inválidos | 6 pruebas aprobadas. |

Total: **146 pruebas**. La tesis cuenta las 116 que respaldan el sistema y su experimento: 34 del backend, 72 de la API satelital y el Data Miner, y 10 del protocolo de cierre. Los datos simulados de estas pruebas verifican código y no representan resultados de campo.

También se comprobó:

- **Reproducción de la ampliación** sobre las tablas del paquete de cierre, con las versiones de `analysis/cierre/codigo/requirements-lock.txt`. Los 925 valores de `resultados.json` coinciden con los publicados en la tesis, incluido el hash SHA-256 del artefacto Ridge (`fe91f281…7127`). `verificar_ampliacion.py` termina sin diferencias.
- **Verificador del repositorio:** `python tools/verify_repository.py` revisa 139 archivos y 21 enlaces locales, sin archivos privados ni coincidencias con los patrones de credenciales.
- **Firmware:** lee las credenciales de `secrets.h`, excluido de Git, y no contiene claves en el código.

Las pruebas locales no equivalen a una ejecución de GitHub Actions. No se verificó un despliegue Docker/Render nuevo, la placa física ni las credenciales de producción.

## Revisión del 23/10/2026

Primera organización del repositorio.

| Componente | Resultado |
| --- | --- |
| Backend | 34 pruebas aprobadas. |
| API satelital y Data Miner | 72 pruebas aprobadas. |
| Análisis de suelo | 10 pruebas aprobadas. |
| Investigación histórica | 14 pruebas aprobadas. |
| Verificador del repositorio | 6 pruebas aprobadas. |

Total: 136 pruebas.

También se comprobó:

- la sintaxis de cinco documentos YAML y la existencia de las rutas Docker indicadas;
- la identidad byte a byte de las cuatro migraciones Flyway respecto del código de origen;
- la repetición offline del corte conservado del 22/10, con el mismo resumen y las mismas 22 predicciones.

Maven puede emitir advertencias de instrumentación de Mockito/Byte Buddy con Java 21; las pruebas finalizan sin fallos.

El escaneo de secretos se limita a los patrones implementados. Revisar manualmente el contenido que vaya a publicarse y definir la licencia y las atribuciones antes de hacer público el repositorio.
