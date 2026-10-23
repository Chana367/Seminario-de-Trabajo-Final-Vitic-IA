package com.vitialert.backend.service;

import com.vitialert.backend.domain.Node;
import com.vitialert.backend.domain.SatelliteObservation;
import com.vitialert.backend.domain.WeatherObservation;
import com.vitialert.backend.dto.FeatureVector;
import com.vitialert.backend.repository.WeatherObservationRepository;
import com.vitialert.backend.repository.SatelliteObservationRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Construccion de features y exportacion del dataset.
 *
 * <p><b>Decision metodologica central.</b> Los lags y el target se resuelven por TIMESTAMP
 * REAL sobre la serie horaria, nunca por posicion de fila:</p>
 * <ul>
 *   <li>{@code soil_moisture_lag_3h} en la hora {@code t} es el bucket cuyo inicio es
 *       exactamente {@code t - 3h}. Si ese bucket no existe (nodo offline, hueco de datos),
 *       la celda queda VACIA, nunca en cero.</li>
 *   <li>{@code soil_moisture_t_plus_24h} es el bucket {@code t + 24h}. Al obtenerse por
 *       timestamp, un hueco produce un target faltante en lugar de un target corrido, que es
 *       exactamente el error que introduce {@code shift(-24)} sobre una serie con huecos.</li>
 * </ul>
 *
 * <p>El prototipo Python usaba {@code shift(n)}, que desplaza n POSICIONES de fila. Con el
 * ESP32 transmitiendo cada pocos segundos, {@code shift(24)} no es "hace 24 horas" sino
 * "hace unos minutos".</p>
 *
 * <p>Esta clase es la unica que calcula features en todo el sistema: el CSV de entrenamiento,
 * el endpoint de inspeccion y la consulta al modelo usan exactamente el mismo calculo.</p>
 */
@Service
public class DatasetService {

    private static final Logger log = LoggerFactory.getLogger(DatasetService.class);

    /** Cobertura minima de la ventana de 24 h para publicar la media movil. */
    private static final double MIN_WINDOW_COVERAGE = 0.5;

    private static final Duration DAY = Duration.ofHours(24);

    private final AggregationService aggregationService;
    private final WeatherObservationRepository weatherObservationRepository;
    private final SatelliteObservationRepository satelliteObservationRepository;

    public DatasetService(AggregationService aggregationService,
                          WeatherObservationRepository weatherObservationRepository,
                          SatelliteObservationRepository satelliteObservationRepository) {
        this.aggregationService = aggregationService;
        this.weatherObservationRepository = weatherObservationRepository;
        this.satelliteObservationRepository = satelliteObservationRepository;
    }

    /**
     * Exporta el dataset horario en CSV.
     *
     * <p>Se agrega un margen de 24 h a cada lado del rango pedido: hacia atras para poder
     * resolver los lags de las primeras filas y hacia adelante para el target de las ultimas.
     * Sin ese margen, los bordes del export tendrian celdas vacias artificiales.</p>
     */
    @Transactional(readOnly = true)
    public String exportCsv(Node node, Instant from, Instant to) {
        if (from == null || to == null || !from.isBefore(to)) {
            throw new IllegalArgumentException("Se requiere un rango valido: from debe ser anterior a to.");
        }

        Instant first = AggregationService.floorToHour(from);
        Map<Instant, HourlyPoint> series =
                aggregationService.hourlySeries(node.getId(), first.minus(DAY), to.plus(DAY));
        Map<LocalDate, WeatherObservation> weather = loadWeather(first.minus(DAY), to.plus(DAY));
        List<SatelliteObservation> satellite = loadSatellite(node.getId(), first.minus(DAY), to.plus(DAY));

        StringBuilder csv = new StringBuilder();
        csv.append(String.join(",", FeatureVector.csvHeader())).append('\n');

        int rows = 0;
        for (Instant hour : series.keySet()) {
            if (hour.isBefore(first) || !hour.isBefore(to)) {
                continue;
            }
            csv.append(toCsvLine(buildRow(node, hour, series, weather, satellite))).append('\n');
            rows++;
        }

        log.info("Dataset exportado nodo={} desde={} hasta={} filas={}", node.getExternalId(), from, to, rows);
        return csv.toString();
    }

    /**
     * Vector de features de la hora que contiene a {@code at}.
     *
     * <p>Pensado para inspeccion y para la futura consulta de inferencia. Si {@code at} cae
     * en la hora en curso, el bucket todavia esta incompleto; con humedad de suelo, que se
     * mueve en escala de horas, es irrelevante.</p>
     */
    @Transactional(readOnly = true)
    public FeatureVector features(Node node, Instant at) {
        Instant hour = AggregationService.floorToHour(at);
        Map<Instant, HourlyPoint> series =
                aggregationService.hourlySeries(node.getId(), hour.minus(DAY), hour.plus(DAY).plus(Duration.ofHours(1)));
        Map<LocalDate, WeatherObservation> weather = loadWeather(hour.minus(DAY), hour.plus(DAY));
        List<SatelliteObservation> satellite = loadSatellite(node.getId(), hour.minus(DAY), hour.plus(DAY));
        return buildRow(node, hour, series, weather, satellite);
    }

    // ------------------------------------------------------------------ features

    private FeatureVector buildRow(Node node,
                                   Instant hour,
                                   Map<Instant, HourlyPoint> series,
                                   Map<LocalDate, WeatherObservation> weather,
                                   List<SatelliteObservation> satellite) {

        HourlyPoint point = series.get(hour);

        Double soil = point == null ? null : point.soilMoistureMean();
        Double lag1h = soilAt(series, hour.minus(Duration.ofHours(1)));
        Double lag3h = soilAt(series, hour.minus(Duration.ofHours(3)));
        Double lag6h = soilAt(series, hour.minus(Duration.ofHours(6)));
        Double lag12h = soilAt(series, hour.minus(Duration.ofHours(12)));
        Double lag24h = soilAt(series, hour.minus(DAY));

        WeatherObservation observation = weather.get(hour.atZone(ZoneOffset.UTC).toLocalDate());
        SatelliteValues satelliteValues = satelliteAt(satellite, hour);

        return new FeatureVector(
                hour,
                node.getExternalId(),
                soil,
                lag1h,
                lag3h,
                lag6h,
                lag24h,
                slope(soil, lag3h, 3.0),
                slope(soil, lag12h, 12.0),
                meanSoil24h(series, hour),
                point == null ? null : point.temperatureMean(),
                point == null ? null : point.humidityMean(),
                point == null ? null : point.windMean(),
                point == null ? null : point.flowMean(),
                volumeWindow(series, hour, 1),
                volumeWindow(series, hour, 24),
                observation == null ? null : observation.getPrecipitationMm(),
                observation == null ? null : observation.getEt0Mm(),
                observation == null ? null : observation.getVpdMaxKpa(),
                observation == null ? null : observation.getSolarRadiationMjM2(),
                satelliteValues.cloudTopTemperatureC(),
                satelliteValues.cloudTemperatureDeltaC(),
                satelliteValues.cloudFraction(),
                satelliteValues.rainfallRateMmH(),
                satelliteValues.ndviMean(),
                satelliteValues.ndmiMean(),
                point == null ? null : point.sampleCount(),
                soilAt(series, hour.plus(DAY)));
    }

    /** Humedad de suelo en un instante exacto de la serie. Null si ese bucket no existe. */
    private static Double soilAt(Map<Instant, HourlyPoint> series, Instant hour) {
        HourlyPoint point = series.get(hour);
        return point == null ? null : point.soilMoistureMean();
    }

    /** Pendiente en puntos porcentuales por hora. Null si falta alguno de los extremos. */
    private static Double slope(Double current, Double past, double hours) {
        if (current == null || past == null) {
            return null;
        }
        return (current - past) / hours;
    }

    /**
     * Media movil de 24 h terminada en {@code hour} (inclusive). Null si hay menos de la mitad
     * de los buckets: una media de 24 h calculada sobre 3 horas no es una media de 24 h.
     */
    private static Double meanSoil24h(Map<Instant, HourlyPoint> series, Instant hour) {
        double sum = 0;
        int found = 0;
        for (int i = 0; i < 24; i++) {
            HourlyPoint point = series.get(hour.minus(Duration.ofHours(i)));
            if (point != null && point.soilMoistureMean() != null) {
                sum += point.soilMoistureMean();
                found++;
            }
        }
        return found < 24 * MIN_WINDOW_COVERAGE ? null : sum / found;
    }

    /**
     * Volumen regado en la ventana que termina en {@code hour} (inclusive).
     * Null si ningun bucket de la ventana tiene informacion de volumen.
     */
    private static BigDecimal volumeWindow(Map<Instant, HourlyPoint> series, Instant hour, int hours) {
        BigDecimal total = BigDecimal.ZERO;
        boolean observed = false;
        for (int i = 0; i < hours; i++) {
            HourlyPoint point = series.get(hour.minus(Duration.ofHours(i)));
            if (point != null && point.waterVolumeUsed() != null) {
                total = total.add(point.waterVolumeUsed());
                observed = true;
            }
        }
        return observed ? total : null;
    }

    /**
     * Meteorologia diaria del Data Miner indexada por fecha UTC. Es DIARIA: el mismo valor se
     * replica en las 24 filas del dia. No se interpola, porque desagregarla exigiria inventar
     * una distribucion temporal que nadie midio.
     */
    private Map<LocalDate, WeatherObservation> loadWeather(Instant from, Instant to) {
        LocalDate fromDate = from.atZone(ZoneOffset.UTC).toLocalDate().minusDays(1);
        LocalDate toDate = to.atZone(ZoneOffset.UTC).toLocalDate().plusDays(1);

        Map<LocalDate, WeatherObservation> byDate = new LinkedHashMap<>();
        for (WeatherObservation observation : weatherObservationRepository
                .findByObservationDateBetweenOrderByObservationDateAscSourceAsc(fromDate, toDate)) {
            byDate.putIfAbsent(observation.getObservationDate(), observation);
        }
        return byDate;
    }

    private List<SatelliteObservation> loadSatellite(Long nodeId, Instant from, Instant to) {
        return satelliteObservationRepository
                .findByNodeIdAndRetrievedAtBetweenOrderByRetrievedAtAsc(
                        nodeId, from.minus(Duration.ofDays(35)), to.plus(Duration.ofHours(2)));
    }

    /** GOES caduca a las 2 h; Sentinel se conserva hasta 30 dias o una imagen mas nueva. */
    private static SatelliteValues satelliteAt(List<SatelliteObservation> observations, Instant hour) {
        SatelliteObservation goes = null;
        SatelliteObservation sentinel = null;
        Instant bucketEnd = hour.plus(Duration.ofHours(1));
        LocalDate day = hour.atZone(ZoneOffset.UTC).toLocalDate();
        for (SatelliteObservation candidate : observations) {
            Instant goesTime = candidate.getGoesObservationTime();
            if (goesTime != null && !goesTime.isAfter(bucketEnd)
                    && !goesTime.isBefore(hour.minus(Duration.ofHours(2)))
                    && (goes == null || goesTime.isAfter(goes.getGoesObservationTime()))) {
                goes = candidate;
            }
            LocalDate imageDate = candidate.getSentinelImageDate();
            if (imageDate != null && !imageDate.isAfter(day)
                    && !imageDate.isBefore(day.minusDays(30))
                    && (sentinel == null || imageDate.isAfter(sentinel.getSentinelImageDate()))) {
                sentinel = candidate;
            }
        }
        return new SatelliteValues(
                goes == null ? null : goes.getCloudTopTemperatureC(),
                goes == null ? null : goes.getCloudTemperatureDeltaC(),
                goes == null ? null : goes.getCloudFraction(),
                goes == null ? null : goes.getRainfallRateMmH(),
                sentinel == null ? null : sentinel.getNdviMean(),
                sentinel == null ? null : sentinel.getNdmiMean());
    }

    private record SatelliteValues(Double cloudTopTemperatureC,
                                   Double cloudTemperatureDeltaC,
                                   Double cloudFraction,
                                   Double rainfallRateMmH,
                                   Double ndviMean,
                                   Double ndmiMean) { }

    // ------------------------------------------------------------------ CSV

    private static String toCsvLine(FeatureVector row) {
        List<Object> values = row.csvValues();
        StringBuilder line = new StringBuilder();
        for (int i = 0; i < values.size(); i++) {
            if (i > 0) {
                line.append(',');
            }
            line.append(formatCell(values.get(i)));
        }
        return line.toString();
    }

    /** Celda vacia para dato faltante. Nunca cero, nunca NaN. */
    private static String formatCell(Object value) {
        if (value == null) {
            return "";
        }
        if (value instanceof Double number) {
            if (number.isNaN() || number.isInfinite()) {
                return "";
            }
            return BigDecimal.valueOf(number)
                    .setScale(6, RoundingMode.HALF_UP)
                    .stripTrailingZeros()
                    .toPlainString();
        }
        if (value instanceof BigDecimal number) {
            return number.stripTrailingZeros().toPlainString();
        }
        String text = value.toString();
        if (text.contains(",") || text.contains("\"")) {
            return '"' + text.replace("\"", "\"\"") + '"';
        }
        return text;
    }
}
