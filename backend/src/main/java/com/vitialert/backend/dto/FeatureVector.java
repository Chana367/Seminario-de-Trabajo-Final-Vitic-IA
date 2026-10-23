package com.vitialert.backend.dto;

import com.fasterxml.jackson.annotation.JsonProperty;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Una fila del dataset. Es la UNICA estructura de features del sistema: la misma que se
 * exporta a CSV, la misma que devuelve {@code GET /api/nodes/{id}/features} y la misma que
 * se envia al servicio Python de inferencia.
 *
 * <p>Tener una sola estructura elimina por construccion el <i>training/serving skew</i>: el
 * modelo se entrena y se consulta con features calculadas exactamente igual.</p>
 *
 * <p><b>Todos los campos son nullables a proposito.</b> Un valor ausente viaja como
 * {@code null} y se exporta como celda vacia. Nunca como cero: un cero en
 * {@code soil_moisture_lag_24h} significaria "hace 24 horas el suelo estaba completamente
 * seco", que es un dato valido del dominio y arruinaria el entrenamiento.</p>
 */
public record FeatureVector(

        @JsonProperty("timestamp") Instant timestamp,
        @JsonProperty("node_id") String nodeId,

        @JsonProperty("soil_moisture_pct") Double soilMoisturePct,

        @JsonProperty("soil_moisture_lag_1h") Double soilMoistureLag1h,
        @JsonProperty("soil_moisture_lag_3h") Double soilMoistureLag3h,
        @JsonProperty("soil_moisture_lag_6h") Double soilMoistureLag6h,
        @JsonProperty("soil_moisture_lag_24h") Double soilMoistureLag24h,

        /** Puntos porcentuales por hora entre t-3h y t. */
        @JsonProperty("soil_moisture_slope_3h") Double soilMoistureSlope3h,
        /** Puntos porcentuales por hora entre t-12h y t. */
        @JsonProperty("soil_moisture_slope_12h") Double soilMoistureSlope12h,

        @JsonProperty("soil_moisture_mean_24h") Double soilMoistureMean24h,

        @JsonProperty("temperature_c") Double temperatureC,
        @JsonProperty("relative_humidity_pct") Double relativeHumidityPct,
        @JsonProperty("wind_speed_kmh") Double windSpeedKmh,
        @JsonProperty("flow_l_min") BigDecimal flowLMin,

        @JsonProperty("irrigation_volume_1h") BigDecimal irrigationVolume1h,
        @JsonProperty("irrigation_volume_24h") BigDecimal irrigationVolume24h,

        /** Variables diarias del Data Miner, replicadas en todas las filas del dia. */
        @JsonProperty("precipitation_mm") Double precipitationMm,
        @JsonProperty("et0_mm") Double et0Mm,
        @JsonProperty("vpd_kpa") Double vpdKpa,
        @JsonProperty("solar_radiation") Double solarRadiation,

        @JsonProperty("cloud_top_temperature_c") Double cloudTopTemperatureC,
        @JsonProperty("cloud_temperature_delta_c") Double cloudTemperatureDeltaC,
        @JsonProperty("cloud_fraction") Double cloudFraction,
        @JsonProperty("rainfall_rate_mm_h") Double rainfallRateMmH,
        @JsonProperty("ndvi_mean") Double ndviMean,
        @JsonProperty("ndmi_mean") Double ndmiMean,

        /** Lecturas que componen el bucket horario. Permite descartar horas con poca cobertura. */
        @JsonProperty("sample_count") Integer sampleCount,

        /** Target: humedad de suelo en t+24h, buscada por timestamp exacto sobre la serie horaria. */
        @JsonProperty("soil_moisture_t_plus_24h") Double soilMoistureTPlus24h
) {

    /** Cabecera del CSV. El orden se corresponde uno a uno con {@link #csvValues()}. */
    public static List<String> csvHeader() {
        return List.of(
                "timestamp", "node_id", "soil_moisture_pct",
                "soil_moisture_lag_1h", "soil_moisture_lag_3h",
                "soil_moisture_lag_6h", "soil_moisture_lag_24h",
                "soil_moisture_slope_3h", "soil_moisture_slope_12h",
                "soil_moisture_mean_24h",
                "temperature_c", "relative_humidity_pct", "wind_speed_kmh", "flow_l_min",
                "irrigation_volume_1h", "irrigation_volume_24h",
                "precipitation_mm", "et0_mm", "vpd_kpa", "solar_radiation",
                "cloud_top_temperature_c", "cloud_temperature_delta_c", "cloud_fraction",
                "rainfall_rate_mm_h", "ndvi_mean", "ndmi_mean",
                "sample_count", "soil_moisture_t_plus_24h");
    }

    /** Valores en el mismo orden que {@link #csvHeader()}. Un null se exporta como celda vacia. */
    public List<Object> csvValues() {
        List<Object> values = new ArrayList<>(csvHeader().size());
        values.add(timestamp);
        values.add(nodeId);
        values.add(soilMoisturePct);
        values.add(soilMoistureLag1h);
        values.add(soilMoistureLag3h);
        values.add(soilMoistureLag6h);
        values.add(soilMoistureLag24h);
        values.add(soilMoistureSlope3h);
        values.add(soilMoistureSlope12h);
        values.add(soilMoistureMean24h);
        values.add(temperatureC);
        values.add(relativeHumidityPct);
        values.add(windSpeedKmh);
        values.add(flowLMin);
        values.add(irrigationVolume1h);
        values.add(irrigationVolume24h);
        values.add(precipitationMm);
        values.add(et0Mm);
        values.add(vpdKpa);
        values.add(solarRadiation);
        values.add(cloudTopTemperatureC);
        values.add(cloudTemperatureDeltaC);
        values.add(cloudFraction);
        values.add(rainfallRateMmH);
        values.add(ndviMean);
        values.add(ndmiMean);
        values.add(sampleCount);
        values.add(soilMoistureTPlus24h);
        return values;
    }

    /**
     * Features que se envian al modelo, con los mismos nombres que las columnas del CSV.
     * Se excluyen el identificador, el timestamp, el conteo de muestras y el target.
     */
    public Map<String, Double> predictorMap() {
        List<String> header = csvHeader();
        List<Object> values = csvValues();
        Map<String, Double> map = new LinkedHashMap<>();
        for (int i = 0; i < header.size(); i++) {
            String name = header.get(i);
            if (name.equals("timestamp") || name.equals("node_id")
                    || name.equals("sample_count") || name.equals("soil_moisture_t_plus_24h")) {
                continue;
            }
            Object value = values.get(i);
            map.put(name, value == null ? null : ((Number) value).doubleValue());
        }
        return map;
    }
}
