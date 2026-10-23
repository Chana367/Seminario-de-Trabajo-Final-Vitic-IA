package com.vitialert.backend.service;

import com.vitialert.backend.domain.WeatherObservation;
import com.vitialert.backend.dto.WeatherImportResultDto;
import com.vitialert.backend.repository.WeatherObservationRepository;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.transaction.annotation.Transactional;

import java.io.ByteArrayInputStream;
import java.nio.charset.StandardCharsets;
import java.time.LocalDate;

import static org.assertj.core.api.Assertions.assertThat;

/** Importacion del dataset del Data Miner: idempotente y sin ceros artificiales. */
@SpringBootTest
@ActiveProfiles("test")
@Transactional
class WeatherServiceTest {

    private static final String CSV = """
            fecha,temp_max_c,temp_media_c,humedad_media_pct,humedad_min_pct,velocidad_viento_media_kmh,velocidad_viento_max_kmh,precipitacion_mm,radiacion_solar_mj_m2,et0_mm,vpd_max_kpa
            2026-08-01,31.2,24.1,52.0,28.0,11.4,29.8,0.0,24.6,5.1,2.4
            2026-08-02,28.9,22.7,61.0,35.0,9.2,21.0,4.6,18.2,3.8,1.6
            2026-08-03,33.0,26.4,44.0,,13.1,,0.0,,5.9,3.1
            """;

    @Autowired
    private WeatherService weatherService;

    @Autowired
    private WeatherObservationRepository weatherObservationRepository;

    @Test
    void importaElCsvYDistingueElCeroRealDelDatoFaltante() throws Exception {
        WeatherImportResultDto result = weatherService.importCsv(stream(CSV), "TEST_SOURCE");

        assertThat(result.rowsRead()).isEqualTo(3);
        assertThat(result.inserted()).isEqualTo(3);
        assertThat(result.skipped()).isZero();

        WeatherObservation first = weatherObservationRepository
                .findByObservationDateAndSource(LocalDate.of(2026, 8, 1), "TEST_SOURCE").orElseThrow();
        assertThat(first.getTempMaxC()).isEqualTo(31.2);
        assertThat(first.getEt0Mm()).isEqualTo(5.1);
        // 0.0 mm de lluvia es un dato real: se guarda como cero.
        assertThat(first.getPrecipitationMm()).isEqualTo(0.0);

        WeatherObservation third = weatherObservationRepository
                .findByObservationDateAndSource(LocalDate.of(2026, 8, 3), "TEST_SOURCE").orElseThrow();
        // Celda vacia -> null, nunca cero. La distincion es critica para Ciencia de Datos.
        assertThat(third.getHumidityMinPct()).isNull();
        assertThat(third.getWindMaxKmh()).isNull();
        assertThat(third.getSolarRadiationMjM2()).isNull();
        assertThat(third.getTempMaxC()).isEqualTo(33.0);
    }

    @Test
    void reimportarElMismoArchivoActualizaEnLugarDeDuplicar() throws Exception {
        weatherService.importCsv(stream(CSV), "IDEMPOTENTE");
        WeatherImportResultDto second =
                weatherService.importCsv(stream(CSV.replace("31.2", "35.9")), "IDEMPOTENTE");

        assertThat(second.inserted()).isZero();
        assertThat(second.updated()).isEqualTo(3);

        assertThat(weatherObservationRepository
                .findByObservationDateAndSource(LocalDate.of(2026, 8, 1), "IDEMPOTENTE").orElseThrow()
                .getTempMaxC()).isEqualTo(35.9);
    }

    private static ByteArrayInputStream stream(String content) {
        return new ByteArrayInputStream(content.getBytes(StandardCharsets.UTF_8));
    }
}
