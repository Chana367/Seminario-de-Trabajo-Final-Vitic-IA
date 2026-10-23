package com.vitialert.backend.service;

import com.vitialert.backend.config.VitiAlertProperties;
import com.vitialert.backend.domain.TelemetryReading;
import com.vitialert.backend.repository.TelemetryReadingRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.Duration;
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;

/**
 * Serie horaria a partir de la telemetria cruda.
 *
 * <p>El ESP32 transmite con frecuencia irregular, asi que nunca se asume "una fila = una
 * hora": cada lectura se ubica en su bucket truncando su timestamp real a la hora en punto
 * (UTC como origen). Dos exportaciones de rangos distintos producen exactamente los mismos
 * buckets para el periodo que comparten.</p>
 *
 * <p>El tiempo de valvula abierta no es una agregacion de filas sino una integracion sobre
 * los intervalos entre lecturas consecutivas. Un hueco mayor a
 * {@code vitialert.dataset.max-gap-seconds} significa nodo offline y no se contabiliza: si
 * el nodo estuvo caido media hora con la valvula abierta, no se puede afirmar que rego media
 * hora.</p>
 */
@Service
public class AggregationService {

    private static final Duration BUCKET = Duration.ofHours(1);

    private final TelemetryReadingRepository telemetryReadingRepository;
    private final VitiAlertProperties properties;

    public AggregationService(TelemetryReadingRepository telemetryReadingRepository,
                              VitiAlertProperties properties) {
        this.telemetryReadingRepository = telemetryReadingRepository;
        this.properties = properties;
    }

    /** Trunca un instante al inicio de su hora. */
    public static Instant floorToHour(Instant instant) {
        long seconds = BUCKET.getSeconds();
        return Instant.ofEpochSecond(Math.floorDiv(instant.getEpochSecond(), seconds) * seconds);
    }

    /**
     * Serie horaria del nodo, indexada por el inicio de cada bucket y en orden cronologico.
     * Solo aparecen las horas que tienen al menos una lectura: un hueco es una hora ausente,
     * no una hora en cero.
     */
    @Transactional(readOnly = true)
    public Map<Instant, HourlyPoint> hourlySeries(Long nodeId, Instant from, Instant to) {
        validateRange(from, to);

        List<TelemetryReading> readings = telemetryReadingRepository.findRangeAsc(nodeId, from, to);
        Map<Instant, Accumulator> buckets = new TreeMap<>();

        TelemetryReading previous = null;
        Accumulator previousBucket = null;
        long maxGap = properties.dataset().maxGapSeconds();

        for (TelemetryReading reading : readings) {
            Accumulator accumulator = buckets.computeIfAbsent(
                    floorToHour(reading.getTimestampReceived()), key -> new Accumulator());
            accumulator.add(reading);

            if (previous != null && previousBucket != null) {
                long gapSeconds = Duration.between(previous.getTimestampReceived(),
                        reading.getTimestampReceived()).getSeconds();
                if (gapSeconds > 0 && gapSeconds <= maxGap) {
                    // El intervalo se atribuye al bucket de la lectura ANTERIOR, que es la que
                    // declara el estado de la valvula durante ese intervalo.
                    if (previous.isValveOpen()) {
                        previousBucket.valveOpenSeconds += gapSeconds;
                    }
                    BigDecimal before = previous.getVolumenTotalL();
                    BigDecimal after = reading.getVolumenTotalL();
                    if (before != null && after != null) {
                        BigDecimal delta = after.subtract(before);
                        // Un delta negativo es un reinicio del contador del ESP32: se computa
                        // como 0 en lugar de inventar un consumo negativo.
                        previousBucket.addVolume(delta.signum() > 0 ? delta : BigDecimal.ZERO);
                    }
                }
            }

            previous = reading;
            previousBucket = accumulator;
        }

        Map<Instant, HourlyPoint> series = new LinkedHashMap<>(buckets.size());
        buckets.forEach((hour, accumulator) -> series.put(hour, accumulator.toPoint(hour)));
        return series;
    }

    private void validateRange(Instant from, Instant to) {
        if (from == null || to == null) {
            throw new IllegalArgumentException("Los parametros from y to son obligatorios.");
        }
        if (!from.isBefore(to)) {
            throw new IllegalArgumentException("El parametro from debe ser anterior a to.");
        }
        long days = Duration.between(from, to).toDays();
        if (days > properties.dataset().maxRangeDays()) {
            throw new IllegalArgumentException("El rango solicitado (" + days + " dias) supera el maximo de "
                    + properties.dataset().maxRangeDays() + " dias.");
        }
    }

    /** Acumulador mutable de un bucket. Vive solo durante el calculo. */
    private static final class Accumulator {

        private int sampleCount;

        private double soilSum;
        private int soilCount;
        private Double soilMin;
        private Double soilMax;

        private double tempSum;
        private int tempCount;

        private double humiditySum;
        private int humidityCount;

        private double windSum;
        private int windCount;
        private Double windMax;

        private BigDecimal flowSum = BigDecimal.ZERO;
        private int flowCount;

        private BigDecimal volumeUsed = BigDecimal.ZERO;
        private boolean volumeObserved;

        private long valveOpenSeconds;

        void add(TelemetryReading reading) {
            sampleCount++;

            Double soil = reading.getHumedadSueloPct();
            if (soil != null) {
                soilSum += soil;
                soilCount++;
                soilMin = soilMin == null ? soil : Math.min(soilMin, soil);
                soilMax = soilMax == null ? soil : Math.max(soilMax, soil);
            }

            Double temp = reading.getTemperaturaAmbienteC();
            if (temp != null) {
                tempSum += temp;
                tempCount++;
            }

            Double humidity = reading.getHumedadRelativaPct();
            if (humidity != null) {
                humiditySum += humidity;
                humidityCount++;
            }

            Double wind = reading.getVelocidadVientoKmh();
            if (wind != null) {
                windSum += wind;
                windCount++;
                windMax = windMax == null ? wind : Math.max(windMax, wind);
            }

            BigDecimal flow = reading.getCaudalLMin();
            if (flow != null) {
                flowSum = flowSum.add(flow);
                flowCount++;
            }
        }

        void addVolume(BigDecimal delta) {
            volumeUsed = volumeUsed.add(delta);
            volumeObserved = true;
        }

        HourlyPoint toPoint(Instant hour) {
            return new HourlyPoint(
                    hour,
                    sampleCount,
                    mean(soilSum, soilCount),
                    soilMin,
                    soilMax,
                    mean(tempSum, tempCount),
                    mean(humiditySum, humidityCount),
                    mean(windSum, windCount),
                    windMax,
                    flowCount == 0 ? null : flowSum.divide(BigDecimal.valueOf(flowCount), 3, RoundingMode.HALF_UP),
                    volumeObserved ? volumeUsed.setScale(3, RoundingMode.HALF_UP) : null,
                    valveOpenSeconds);
        }

        /** Null cuando no hubo ninguna muestra valida: nunca cero artificial. */
        private static Double mean(double sum, int count) {
            return count == 0 ? null : sum / count;
        }
    }
}
