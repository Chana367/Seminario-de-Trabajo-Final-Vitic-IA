package com.vitialert.backend.client;

import com.vitialert.backend.repository.NodeRepository;
import com.vitialert.backend.repository.TelemetryReadingRepository;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.domain.PageRequest;
import org.springframework.http.MediaType;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.transaction.annotation.Transactional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/**
 * Si VitiAI o la API de inferencia estan caidos, la telemetria se sigue aceptando y
 * persistiendo y la valvula cae al fallback local. Las integraciones apuntan a puertos
 * cerrados a proposito: mockear los clientes probaria que el codigo maneja un Optional vacio
 * fabricado por el propio test, no que la excepcion real de conexion se captura donde debe.
 */
@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
@TestPropertySource(properties = {
        "spring.datasource.url=jdbc:h2:mem:vitialert-down;DB_CLOSE_DELAY=-1;DB_CLOSE_ON_EXIT=FALSE;MODE=PostgreSQL",
        "vitialert.satellite.enabled=true",
        "vitialert.satellite.base-url=http://127.0.0.1:59997",
        "vitialert.satellite.timeout-ms=300",
        "vitialert.ml.enabled=true",
        "vitialert.ml.base-url=http://127.0.0.1:59998",
        "vitialert.ml.timeout-ms=300"
})
@Transactional
class ExternalServicesDownTest {

    private static final String PAYLOAD = """
            {
              "nodo_id": "down-1",
              "temperatura_ambiente_c": 28.4,
              "humedad_relativa_pct": 45,
              "humedad_suelo_pct": 22,
              "humedad_suelo_raw": 2730,
              "velocidad_viento_kmh": 18.5,
              "caudal_l_min": 7.80,
              "volumen_total_l": 124.60,
              "valvula_abierta_actual": true,
              "decision_riego_local": true
            }
            """;

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private SatelliteClient satelliteClient;

    @Autowired
    private PredictionClient predictionClient;

    @Autowired
    private NodeRepository nodeRepository;

    @Autowired
    private TelemetryReadingRepository telemetryReadingRepository;

    @Test
    void vitiAiCaidoDevuelveVacioEnLugarDeFallar() {
        assertThat(satelliteClient.isEnabled()).isTrue();
        assertThat(satelliteClient.fetchFeatures(-32.89, -68.84)).isEmpty();
    }

    @Test
    void laTelemetriaSeGuardaYLaValvulaCaeAlFallbackLocalAunqueElModeloEsteCaido() throws Exception {
        assertThat(predictionClient.isEnabled()).isTrue();

        mockMvc.perform(post("/api/data")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(PAYLOAD))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.abrir_valvula").value(true))
                .andExpect(jsonPath("$.encender_luz").value(true));

        var node = nodeRepository.findByExternalId("down-1").orElseThrow();
        assertThat(telemetryReadingRepository.findLatest(node.getId(), PageRequest.of(0, 5))).hasSize(1);
    }
}
