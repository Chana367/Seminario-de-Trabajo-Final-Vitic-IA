# Verificación de la copia de código

Revisión local del 23/10/2026, sin desplegar servicios ni accionar hardware.

| Componente | Comprobación | Resultado |
| --- | --- | --- |
| Backend | Maven, Java 21, perfil de pruebas con H2 | 34 pruebas aprobadas. |
| API satelital y Data Miner | Pytest en Python 3.11, proveedores simulados | 72 pruebas aprobadas. |
| Análisis de suelo | Unittest en Python 3.12 | 10 pruebas aprobadas. |
| Investigación histórica | Unittest en Python 3.12, datos de prueba temporales | 14 pruebas aprobadas. |
| Verificador del repositorio | Archivos temporales válidos e inválidos | 6 pruebas aprobadas. |

Total: **136 pruebas**. Los datos simulados de estas pruebas verifican código y no representan resultados de campo.

También se comprobaron:

- Sintaxis de cinco documentos YAML y existencia de las rutas Docker indicadas.
- Enlaces Markdown locales y patrones de credenciales del verificador.
- Identidad byte a byte de las cuatro migraciones Flyway respecto del código de origen.
- Identidad de los tokens ejecutables del firmware: sus cambios son comentarios, no lógica.
- Conservación de la lógica del backend y servicios Python. Los cambios del pipeline de análisis se limitan a textos del informe, título de figura y selección explícita de la carpeta a verificar.
- Repetición offline del corte conservado del 22/10: mismo resumen y mismas 22 predicciones. Los datos y artefactos de esa repetición permanecen fuera del repositorio.

Las pruebas locales no equivalen a una ejecución de GitHub Actions. No se verificó un despliegue Docker/Render nuevo, la placa física ni las credenciales de producción. Maven puede emitir advertencias de instrumentación de Mockito/Byte Buddy con Java 21; las pruebas finalizan sin fallos.

El escaneo de secretos es limitado a los patrones implementados. Revisar manualmente el contenido que vaya a publicarse y definir licencias y atribuciones antes de hacer público el repositorio.
