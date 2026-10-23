# Protocolo del análisis de suelo medido

1. Conservar páginas GET y manifiesto de fuentes con corte UTC. La repetición offline valida hashes del snapshot.
2. Rechazar timestamps posteriores al corte. Excluir filas identificadas en las notas como reconstruidas o simuladas, sin modificar las fuentes originales.
3. Usar humedad de suelo estrictamente entre 0 y 100 en la escala relativa del sensor. La exclusión de extremos es un criterio de este experimento y debe revisarse al calibrar la sonda.
4. Agregar por hora con al menos seis lecturas, cobertura de 45 minutos y hueco interno máximo de diez minutos. Mantener vacías las horas sin cobertura suficiente.
5. Construir antecedentes por timestamp, sin desplazar posiciones entre horas ausentes. La media de 24 h requiere 24 horas con valor.
6. La etiqueta es la humedad medida a exactamente 24 horas. Una etiqueta que todavía no se observó permanece ausente.
7. En cada origen de evaluación, ajustar solo con etiquetas anteriores a la hora de emisión. Exigir al menos 24 pares de entrenamiento. Omitir las columnas completamente vacías en ese entrenamiento, sin consultar el futuro para elegirlas.
8. Evaluar candidato y persistencia sobre las mismas filas. Informar MAE, RMSE, R² cuando esté definido, tamaño del conjunto y días evaluados. Mantener los mayores errores.
9. Entrenar el artefacto final solo si existen al menos 48 pares. Este mínimo permite ejecutar el experimento, no garantiza precisión ni suficiencia estadística.
10. Conservar hiperparámetros, dependencias, hashes y procedencia. No desplegar el candidato ni utilizarlo para accionar hardware desde este pipeline.

Las observaciones cercanas están correlacionadas. La prueba prospectiva requiere reservar un período posterior, guardar predicciones antes de sus etiquetas y no reajustar el candidato usando ese período. Los datos climáticos o satelitales solo podrán incorporarse con ubicación, calidad y disponibilidad temporal comprobadas.
