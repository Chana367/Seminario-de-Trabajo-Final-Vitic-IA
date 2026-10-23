package com.vitialert.backend.service;

import java.math.BigDecimal;
import java.time.Instant;

/**
 * Un bucket horario de la serie agregada.
 *
 * <p>Los campos estadisticos son {@code null} cuando ninguna lectura del bucket aporto esa
 * variable. Nunca cero: "no se midio" y "midio cero" son cosas distintas.</p>
 *
 * @param hour             inicio del bucket, siempre en punto y en UTC
 * @param sampleCount      lecturas que lo componen, para descartar horas con poca cobertura
 * @param waterVolumeUsed  suma de los incrementos del contador acumulado dentro del bucket
 * @param valveOpenSeconds segundos con la valvula abierta, integrados sobre los intervalos reales
 */
public record HourlyPoint(
        Instant hour,
        int sampleCount,
        Double soilMoistureMean,
        Double soilMoistureMin,
        Double soilMoistureMax,
        Double temperatureMean,
        Double humidityMean,
        Double windMean,
        Double windMax,
        BigDecimal flowMean,
        BigDecimal waterVolumeUsed,
        long valveOpenSeconds
) {
}
