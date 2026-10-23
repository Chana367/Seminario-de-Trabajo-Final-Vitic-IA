package com.vitialert.backend.service;

import com.vitialert.backend.domain.WeatherObservation;
import com.vitialert.backend.dto.WeatherImportResultDto;
import com.vitialert.backend.repository.WeatherObservationRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Optional;

/**
 * Importa el CSV diario que produce nuestro Data Miner Python.
 *
 * <p>El Data Miner sigue siendo un proceso independiente y no se porta a Java. La
 * meteorologia se guarda en su propia tabla porque es otra fuente, con otra frecuencia y
 * otro origen de verdad que la telemetria IoT.</p>
 *
 * <p>El formato es conocido y controlado por nosotros, asi que se aceptan exactamente las
 * columnas oficiales. Se toleran las tres variaciones que produce Excel en configuracion
 * regional espanola: BOM UTF-8, separador {@code ;} y coma decimal.</p>
 *
 * <p>La importacion es idempotente por (fecha, fuente): reimportar el mismo archivo actualiza
 * las filas existentes en lugar de duplicarlas.</p>
 */
@Service
public class WeatherService {

    private static final Logger log = LoggerFactory.getLogger(WeatherService.class);

    private static final DateTimeFormatter DMY = DateTimeFormatter.ofPattern("dd/MM/yyyy");
    private static final String DEFAULT_SOURCE = "OPEN_METEO_ERA5";

    /** Columnas oficiales del dataset del Data Miner. */
    private static final List<String> COLUMNS = List.of(
            "fecha",
            "temp_max_c",
            "temp_media_c",
            "humedad_media_pct",
            "humedad_min_pct",
            "velocidad_viento_media_kmh",
            "velocidad_viento_max_kmh",
            "precipitacion_mm",
            "radiacion_solar_mj_m2",
            "et0_mm",
            "vpd_max_kpa");

    private final WeatherObservationRepository weatherObservationRepository;

    public WeatherService(WeatherObservationRepository weatherObservationRepository) {
        this.weatherObservationRepository = weatherObservationRepository;
    }

    @Transactional
    public WeatherImportResultDto importCsv(InputStream inputStream, String requestedSource) throws IOException {
        String source = (requestedSource == null || requestedSource.isBlank())
                ? DEFAULT_SOURCE : requestedSource.trim();

        int rowsRead = 0;
        int inserted = 0;
        int updated = 0;
        int skipped = 0;
        List<String> errors = new ArrayList<>();

        try (BufferedReader reader = new BufferedReader(new InputStreamReader(inputStream, StandardCharsets.UTF_8))) {
            String headerLine = reader.readLine();
            if (headerLine == null || headerLine.isBlank()) {
                throw new IllegalArgumentException("El archivo CSV esta vacio o no tiene cabecera.");
            }
            // Excel en Windows guarda UTF-8 con BOM: sin quitarlo la primera cabecera seria
            // "﻿fecha" y la importacion fallaria sobre un archivo que si tiene fecha.
            if (headerLine.startsWith("﻿")) {
                headerLine = headerLine.substring(1);
            }

            char delimiter = SimpleCsvParser.detectDelimiter(headerLine);
            Map<String, Integer> index = columnIndex(SimpleCsvParser.parseLine(headerLine, delimiter));
            if (!index.containsKey("fecha")) {
                throw new IllegalArgumentException(
                        "El CSV no tiene columna 'fecha'. Columnas esperadas: " + COLUMNS);
            }

            String line;
            int lineNumber = 1;
            while ((line = reader.readLine()) != null) {
                lineNumber++;
                if (line.isBlank()) {
                    continue;
                }
                rowsRead++;
                List<String> values = SimpleCsvParser.parseLine(line, delimiter);

                Optional<LocalDate> date = parseDate(cell(values, index, "fecha"));
                if (date.isEmpty()) {
                    skipped++;
                    if (errors.size() < 20) {
                        errors.add("Linea " + lineNumber + ": fecha invalida o ausente.");
                    }
                    continue;
                }

                Optional<WeatherObservation> existing =
                        weatherObservationRepository.findByObservationDateAndSource(date.get(), source);
                WeatherObservation observation = existing.orElseGet(
                        () -> new WeatherObservation(date.get(), source));

                observation.setTempMaxC(number(cell(values, index, "temp_max_c")));
                observation.setTempMeanC(number(cell(values, index, "temp_media_c")));
                observation.setHumidityMeanPct(number(cell(values, index, "humedad_media_pct")));
                observation.setHumidityMinPct(number(cell(values, index, "humedad_min_pct")));
                observation.setWindMeanKmh(number(cell(values, index, "velocidad_viento_media_kmh")));
                observation.setWindMaxKmh(number(cell(values, index, "velocidad_viento_max_kmh")));
                observation.setPrecipitationMm(number(cell(values, index, "precipitacion_mm")));
                observation.setSolarRadiationMjM2(number(cell(values, index, "radiacion_solar_mj_m2")));
                observation.setEt0Mm(number(cell(values, index, "et0_mm")));
                observation.setVpdMaxKpa(number(cell(values, index, "vpd_max_kpa")));

                weatherObservationRepository.save(observation);
                if (existing.isPresent()) {
                    updated++;
                } else {
                    inserted++;
                }
            }
        }

        log.info("Importacion meteorologica source={} leidas={} insertadas={} actualizadas={} descartadas={}",
                source, rowsRead, inserted, updated, skipped);
        return new WeatherImportResultDto(source, rowsRead, inserted, updated, skipped, errors);
    }

    /**
     * Mapea las columnas por NOMBRE, no por posicion: agregar una columna al principio del CSV
     * no corre los valores ni guarda temperaturas en la columna de humedad.
     */
    private static Map<String, Integer> columnIndex(List<String> header) {
        Map<String, Integer> index = new HashMap<>();
        for (int i = 0; i < header.size(); i++) {
            String name = header.get(i).trim().toLowerCase(Locale.ROOT);
            if (COLUMNS.contains(name)) {
                index.putIfAbsent(name, i);
            }
        }
        return index;
    }

    private static String cell(List<String> values, Map<String, Integer> index, String column) {
        Integer position = index.get(column);
        if (position == null || position >= values.size()) {
            return null;
        }
        String raw = values.get(position).trim();
        return raw.isEmpty() ? null : raw;
    }

    /** Null si el valor falta o no es numerico. Nunca cero. */
    private static Double number(String raw) {
        if (raw == null) {
            return null;
        }
        String normalized = raw.replace(',', '.');
        try {
            return Double.valueOf(normalized);
        } catch (NumberFormatException ex) {
            return null;
        }
    }

    private static Optional<LocalDate> parseDate(String raw) {
        if (raw == null) {
            return Optional.empty();
        }
        try {
            if (raw.length() >= 10 && raw.charAt(4) == '-') {
                return Optional.of(LocalDate.parse(raw.substring(0, 10)));
            }
            return Optional.of(LocalDate.parse(raw, DMY));
        } catch (RuntimeException ex) {
            return Optional.empty();
        }
    }
}
