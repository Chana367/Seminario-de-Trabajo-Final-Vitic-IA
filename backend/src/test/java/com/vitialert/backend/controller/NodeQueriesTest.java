package com.vitialert.backend.controller;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/**
 * Endpoints de consulta ejercitados con la sesion de Hibernate CERRADA.
 *
 * <p><b>Esta clase NO lleva {@code @Transactional} a proposito.</b> El resto de los tests si la
 * lleva, y eso mantiene la sesion abierta durante todo el test: con esa red de contencion, un
 * acceso perezoso fuera de transaccion nunca falla y el problema queda invisible.</p>
 *
 * <p>Aca se reproduce el escenario real: {@code open-in-view: false}, la relacion
 * {@code node} es LAZY, el servicio devuelve entidades y el controller las mapea a DTO
 * DESPUES de que la transaccion cerro. Sin {@code @EntityGraph(attributePaths = "node")} en
 * las consultas, estos tres endpoints lanzan LazyInitializationException.</p>
 *
 * <p>El fallo lo detecto Francisco Paredes en el commit 6eda399 sobre la version anterior del
 * backend; el refactor lo reintrodujo y esta clase existe para que no vuelva a pasar.</p>
 */
@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
class NodeQueriesTest {

    private static final String NODE = "lazy-1";

    private static final String PAYLOAD = """
            {
              "nodo_id": "%s",
              "temperatura_ambiente_c": 24.0,
              "humedad_relativa_pct": 55,
              "humedad_suelo_pct": 31,
              "humedad_suelo_raw": 2600,
              "velocidad_viento_kmh": 8.0,
              "caudal_l_min": %s,
              "volumen_total_l": %s,
              "valvula_abierta_actual": %s,
              "decision_riego_local": %s
            }
            """;

    @Autowired
    private MockMvc mockMvc;

    /** Alta del nodo y un ciclo completo de riego, por el camino real del ESP32. */
    @BeforeEach
    void seed() throws Exception {
        send(PAYLOAD.formatted(NODE, "7.50", "100.00", "true", "true"));
        send(PAYLOAD.formatted(NODE, "0.00", "137.50", "false", "false"));
    }

    private void send(String body) throws Exception {
        mockMvc.perform(post("/api/data")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(body))
                .andExpect(status().isOk());
    }

    @Test
    void laUltimaLecturaSeSerializaConLaSesionCerrada() throws Exception {
        mockMvc.perform(get("/api/nodes/{id}/telemetry/latest", NODE))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.node_id").value(NODE))
                .andExpect(jsonPath("$.humedad_suelo_pct").value(31.0));
    }

    @Test
    void elHistoricoPaginadoSeSerializaConLaSesionCerrada() throws Exception {
        mockMvc.perform(get("/api/nodes/{id}/telemetry", NODE))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.content[0].node_id").value(NODE))
                .andExpect(jsonPath("$.total_elements").isNumber());
    }

    @Test
    void losEventosDeRiegoSeSerializanConLaSesionCerrada() throws Exception {
        mockMvc.perform(get("/api/nodes/{id}/irrigation-events", NODE))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.content[0].node_id").value(NODE))
                .andExpect(jsonPath("$.content[0].volumen_aplicado_l").isNumber())
                .andExpect(jsonPath("$.content[0].estado").value("CLOSED"));
    }
}
