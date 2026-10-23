package com.vitialert.backend.client;

import com.vitialert.backend.config.VitiAlertProperties;
import com.vitialert.backend.dto.SatelliteFeaturesDto;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

import java.util.Optional;

/**
 * Integracion con VitiAI (viti-alert-ds-api), el servicio Python que produce las features
 * satelitales a partir de GOES y Sentinel.
 *
 * <p>El backend Java NO implementa ninguna logica satelital: solo consulta.</p>
 *
 * <p><b>El servicio se consulta por COORDENADAS, no por nodo:</b>
 * {@code GET /api/v1/satellite/features?lat=&lon=&buffer_km=}. El llamador resuelve la
 * latitud y la longitud desde la entidad {@code Node}. Es justamente para esto que el nodo
 * guarda sus coordenadas, y no para usarlas como features del modelo.</p>
 *
 * <p><b>Regla de disponibilidad:</b> si VitiAI esta apagado, lento o devuelve error, este
 * metodo devuelve {@link Optional#empty()} y registra una advertencia. Nunca lanza. El dato
 * de campo es irrecuperable y la feature satelital no: ante la duda, la telemetria se guarda
 * igual y la valvula sigue gobernada por el fallback local.</p>
 */
@Component
public class SatelliteClient {

    private static final Logger log = LoggerFactory.getLogger(SatelliteClient.class);

    private final RestClient restClient;
    private final VitiAlertProperties.Satellite properties;

    public SatelliteClient(VitiAlertProperties properties) {
        this.properties = properties.satellite();
        SimpleClientHttpRequestFactory factory = new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(this.properties.timeoutMs());
        factory.setReadTimeout(this.properties.timeoutMs());
        this.restClient = RestClient.builder()
                .baseUrl(this.properties.baseUrl())
                .requestFactory(factory)
                .build();
    }

    public boolean isEnabled() {
        return properties.enabled();
    }

    /**
     * Features satelitales para un punto geografico.
     *
     * @return vacio si la integracion esta apagada o VitiAI no responde
     */
    public Optional<SatelliteFeaturesDto> fetchFeatures(double latitude, double longitude) {
        if (!properties.enabled()) {
            return Optional.empty();
        }
        try {
            SatelliteFeaturesDto response = restClient.get()
                    .uri(builder -> builder.path(properties.featuresPath())
                            .queryParam("lat", latitude)
                            .queryParam("lon", longitude)
                            .queryParam("buffer_km", properties.bufferKm())
                            .build())
                    .retrieve()
                    .body(SatelliteFeaturesDto.class);
            return Optional.ofNullable(response);
        } catch (RuntimeException ex) {
            log.warn("VitiAI satelital no disponible (lat={}, lon={}): {}", latitude, longitude, ex.getMessage());
            return Optional.empty();
        }
    }
}
