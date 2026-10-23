package com.vitialert.backend.service;

import com.vitialert.backend.TestSupport;
import com.vitialert.backend.domain.Node;
import com.vitialert.backend.domain.WeatherObservation;
import com.vitialert.backend.domain.SatelliteObservation;
import com.vitialert.backend.dto.FeatureVector;
import com.vitialert.backend.dto.SatelliteFeaturesDto;
import com.vitialert.backend.repository.NodeRepository;
import com.vitialert.backend.repository.TelemetryReadingRepository;
import com.vitialert.backend.repository.WeatherObservationRepository;
import com.vitialert.backend.repository.SatelliteObservationRepository;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.transaction.annotation.Transactional;

import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.within;

/**
 * La pieza metodologicamente mas importante: lags y target por TIMESTAMP REAL sobre la serie
 * horaria, y celda VACIA (nunca cero) cuando el bucket no existe.
 *
 * <p>Si alguien reimplementara los lags por posicion de fila (el {@code shift(n)} del
 * prototipo Python), el test {@code elLagCaeEnUnHuecoDeDatosYQuedaNulo} falla: ahi hay un
 * hueco de dos horas y un desplazamiento por posicion lo saltaria en silencio.</p>
 */
@SpringBootTest
@ActiveProfiles("test")
@Transactional
class DatasetServiceTest {

    private static final Instant START = Instant.parse("2026-09-01T00:00:00Z");
    private static final int HOURS = 30;

    @Autowired
    private DatasetService datasetService;

    @Autowired
    private TelemetryReadingRepository telemetryReadingRepository;

    @Autowired
    private WeatherObservationRepository weatherObservationRepository;

    @Autowired
    private NodeRepository nodeRepository;

    @Autowired
    private SatelliteObservationRepository satelliteObservationRepository;

    /** 30 horas continuas, una lectura cada 5 minutos: 12 muestras por bucket horario. */
    private Node buildSeries(String externalId) {
        Node node = nodeRepository.save(new Node(externalId));
        for (int step = 0; step < HOURS * 12; step++) {
            telemetryReadingRepository.save(TestSupport.reading(
                    node, START.plus(Duration.ofMinutes(5L * step)), 60.0 - step * 0.05));
        }
        return node;
    }

    @Test
    void laCabeceraDelCsvCoincideConElVectorDeFeatures() {
        Node node = buildSeries("ds-1");

        String csv = datasetService.exportCsv(node, START, START.plus(Duration.ofHours(HOURS)));

        String header = csv.lines().findFirst().orElseThrow();
        assertThat(header).isEqualTo(String.join(",", FeatureVector.csvHeader()));
        assertThat(header).contains("soil_moisture_lag_24h", "soil_moisture_slope_12h",
                "irrigation_volume_24h", "et0_mm", "sample_count", "soil_moisture_t_plus_24h");
    }

    @Test
    void resuelveLagsYTargetPorTimestampYDejaVaciasLasCeldasSinDato() {
        Node node = buildSeries("ds-2");

        Map<String, Map<String, String>> rows =
                parse(datasetService.exportCsv(node, START, START.plus(Duration.ofHours(HOURS))));
        assertThat(rows).hasSize(HOURS);

        // Primera fila: no hay pasado, asi que todos los lags estan VACIOS (no en cero).
        Map<String, String> first = rows.get(START.toString());
        assertThat(first).isNotNull();
        assertThat(first.get("soil_moisture_lag_1h")).isEmpty();
        assertThat(first.get("soil_moisture_lag_24h")).isEmpty();
        assertThat(first.get("soil_moisture_slope_3h")).isEmpty();
        // El target si existe: hay datos 24 h despues.
        assertThat(first.get("soil_moisture_t_plus_24h")).isNotEmpty();

        // Con 3 horas de historia se resuelven los lags de 1 h y 3 h, pero no el de 6 h.
        Map<String, String> hour3 = rows.get(START.plus(Duration.ofHours(3)).toString());
        assertThat(hour3.get("soil_moisture_lag_1h")).isNotEmpty();
        assertThat(hour3.get("soil_moisture_lag_3h")).isNotEmpty();
        assertThat(hour3.get("soil_moisture_lag_6h")).isEmpty();
        // El lag de 1 h es exactamente el valor del bucket de la hora anterior.
        assertThat(Double.parseDouble(hour3.get("soil_moisture_lag_1h")))
                .isEqualTo(Double.parseDouble(
                        rows.get(START.plus(Duration.ofHours(2)).toString()).get("soil_moisture_pct")));

        // Ultimas filas: el target t+24h cae fuera de la serie y queda vacio.
        Map<String, String> hour29 = rows.get(START.plus(Duration.ofHours(29)).toString());
        assertThat(hour29.get("soil_moisture_lag_24h")).isNotEmpty();
        assertThat(hour29.get("soil_moisture_t_plus_24h")).isEmpty();

        assertThat(rows.values()).allSatisfy(row -> assertThat(row.get("sample_count")).isEqualTo("12"));
    }

    @Test
    void elLagCaeEnUnHuecoDeDatosYQuedaNulo() {
        Node node = nodeRepository.save(new Node("ds-3"));
        // Horas 0 a 5 y 8 a 12. Las horas 6 y 7 no existen: el nodo estuvo offline.
        for (int hour : new int[]{0, 1, 2, 3, 4, 5, 8, 9, 10, 11, 12}) {
            for (int minute = 0; minute < 60; minute += 10) {
                telemetryReadingRepository.save(TestSupport.reading(node,
                        START.plus(Duration.ofHours(hour)).plus(Duration.ofMinutes(minute)),
                        50.0 - hour));
            }
        }

        FeatureVector features = datasetService.features(node, START.plus(Duration.ofHours(9)));

        assertThat(features.soilMoisturePct()).isCloseTo(41.0, within(1e-9));
        // t-1h = hora 8: existe.
        assertThat(features.soilMoistureLag1h()).isCloseTo(42.0, within(1e-9));
        // t-3h = hora 6: cae en el hueco. Faltante, NO cero.
        assertThat(features.soilMoistureLag3h()).isNull();
        assertThat(features.soilMoistureSlope3h()).isNull();
        // t-6h = hora 3: existe, aunque en el medio haya un hueco.
        assertThat(features.soilMoistureLag6h()).isCloseTo(47.0, within(1e-9));
    }

    @Test
    void incorporaLaMeteorologiaDiariaImportadaDelDataMiner() {
        Node node = buildSeries("ds-4");

        WeatherObservation observation = new WeatherObservation(LocalDate.of(2026, 9, 1), "OPEN_METEO_ERA5");
        observation.setPrecipitationMm(12.5);
        observation.setEt0Mm(4.2);
        observation.setVpdMaxKpa(1.8);
        observation.setSolarRadiationMjM2(22.0);
        weatherObservationRepository.save(observation);

        Map<String, Map<String, String>> rows =
                parse(datasetService.exportCsv(node, START, START.plus(Duration.ofHours(HOURS))));

        Map<String, String> firstDay = rows.get(START.plus(Duration.ofHours(5)).toString());
        assertThat(firstDay.get("precipitation_mm")).isEqualTo("12.5");
        assertThat(firstDay.get("et0_mm")).isEqualTo("4.2");
        assertThat(firstDay.get("vpd_kpa")).isEqualTo("1.8");
        assertThat(firstDay.get("solar_radiation")).isEqualTo("22");

        // El dia 2 no fue importado: las celdas quedan vacias, nunca en cero.
        Map<String, String> secondDay = rows.get(START.plus(Duration.ofHours(26)).toString());
        assertThat(secondDay.get("precipitation_mm")).isEmpty();
        assertThat(secondDay.get("et0_mm")).isEmpty();
    }

    @Test
    void incorporaGoesYSentinelPersistidosSinInventarHistorico() {
        Node node = buildSeries("ds-satellite");
        SatelliteFeaturesDto dto = new SatelliteFeaturesDto(
                START.plus(Duration.ofHours(5).plusMinutes(40)),
                new SatelliteFeaturesDto.Goes(
                        START.plus(Duration.ofHours(5).plusMinutes(30)), -48.2, -3.1, 0.72, 1.4),
                new SatelliteFeaturesDto.Sentinel(LocalDate.of(2026, 8, 28), 0.51, 0.18),
                "good");
        satelliteObservationRepository.save(SatelliteObservation.from(node, dto));

        Map<String, Map<String, String>> rows =
                parse(datasetService.exportCsv(node, START, START.plus(Duration.ofHours(HOURS))));

        Map<String, String> hour5 = rows.get(START.plus(Duration.ofHours(5)).toString());
        assertThat(hour5.get("cloud_top_temperature_c")).isEqualTo("-48.2");
        assertThat(hour5.get("cloud_temperature_delta_c")).isEqualTo("-3.1");
        assertThat(hour5.get("cloud_fraction")).isEqualTo("0.72");
        assertThat(hour5.get("rainfall_rate_mm_h")).isEqualTo("1.4");
        assertThat(hour5.get("ndvi_mean")).isEqualTo("0.51");
        assertThat(hour5.get("ndmi_mean")).isEqualTo("0.18");

        // GOES no se arrastra fuera de su ventana de 2 h; Sentinel si conserva su fecha real.
        Map<String, String> hour10 = rows.get(START.plus(Duration.ofHours(10)).toString());
        assertThat(hour10.get("cloud_fraction")).isEmpty();
        assertThat(hour10.get("ndvi_mean")).isEqualTo("0.51");
    }

    @Test
    void elEndpointDeFeaturesDevuelveLaMismaFilaQueElCsv() {
        Node node = buildSeries("ds-5");
        Instant hour = START.plus(Duration.ofHours(10));

        FeatureVector features = datasetService.features(node, hour.plus(Duration.ofMinutes(37)));
        Map<String, String> csvRow =
                parse(datasetService.exportCsv(node, START, START.plus(Duration.ofHours(HOURS))))
                        .get(hour.toString());

        // Un unico calculo de features para el entrenamiento y para la inferencia:
        // asi no puede aparecer training/serving skew.
        assertThat(features.timestamp()).isEqualTo(hour);
        // El CSV redondea a 6 decimales, de ahi la tolerancia.
        assertThat(features.soilMoisturePct())
                .isCloseTo(Double.parseDouble(csvRow.get("soil_moisture_pct")), within(1e-6));
        assertThat(features.soilMoistureLag6h())
                .isCloseTo(Double.parseDouble(csvRow.get("soil_moisture_lag_6h")), within(1e-6));
        assertThat(features.predictorMap()).containsKeys(
                "soil_moisture_pct", "soil_moisture_lag_24h", "et0_mm");
        assertThat(features.predictorMap()).doesNotContainKeys(
                "timestamp", "node_id", "sample_count", "soil_moisture_t_plus_24h");
    }

    private static Map<String, Map<String, String>> parse(String csv) {
        List<String> lines = new ArrayList<>(csv.lines().toList());
        String[] header = lines.remove(0).split(",", -1);

        Map<String, Map<String, String>> rows = new LinkedHashMap<>();
        for (String line : lines) {
            if (line.isBlank()) {
                continue;
            }
            String[] values = line.split(",", -1);
            Map<String, String> row = new LinkedHashMap<>();
            for (int i = 0; i < header.length; i++) {
                row.put(header[i], i < values.length ? values[i] : "");
            }
            rows.put(row.get("timestamp"), row);
        }
        return rows;
    }
}
