# Revisión antes de publicar

1. Ejecutar `python tools/verify_repository.py` desde la raíz. El verificador es una revisión preventiva, no una garantía de ausencia de secretos en cualquier formato.
2. Ejecutar las pruebas de cada componente. No usar la base de producción para CI.
3. Confirmar que no se agreguen `.env`, `secrets.h`, claves, dumps, datos de campo, resultados binarios ni entornos virtuales.
4. Revisar manualmente `git diff --cached`, especialmente cualquier archivo de configuración nuevo. `.gitignore` no elimina archivos previamente versionados.
5. Revisar la licencia del proyecto y obligaciones de atribución de componentes y fuentes antes de hacerlo público. No se añade una licencia ni se atribuye autoría que no haya sido definida por los responsables.
6. Configurar secretos en GitHub, no en YAML ni en documentación.
7. Revisar la conexión a Render de cada servicio antes de publicar cambios sobre ramas con despliegue automático.

La carpeta es una copia organizada del código vigente. No incluye ni reescribe los historiales de los repositorios de origen. Para mantener sus historiales en un monorepo, planificar una importación explícita; copiar archivos no conserva esa historia.

Las comprobaciones locales realizadas están en [verificacion.md](verificacion.md).

Quedan fuera de este repositorio los documentos de presentación, planes de conversación, recursos web descargados, duplicados del firmware, experimentos antiguos de comparación, snapshots y resultados. Los archivos originales se conservan en el espacio de trabajo.

No se han publicado resultados de campo, añadido una licencia, creado un repositorio remoto ni cambiado servicios de producción como parte de esta organización.
