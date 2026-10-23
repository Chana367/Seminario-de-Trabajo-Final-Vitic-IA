package com.vitialert.backend.config;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.transaction.annotation.Transactional;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/**
 * Proteccion por clave compartida de los endpoints de escritura.
 *
 * <p><b>Por que esta clase existe.</b> El resto de la suite corre con
 * {@code vitialert.security.api-key} vacio, que es como se configura el laboratorio. Con la
 * clave vacia {@code ApiKeyFilter.shouldNotFilter} devuelve {@code true} y el filtro no se
 * ejecuta nunca: las demas pruebas pasan sin haberlo tocado jamas. Aca se fija una clave por
 * {@code @TestPropertySource} para ejercitarlo de verdad.</p>
 *
 * <p>Es el mismo agujero que dejo pasar el {@code LazyInitializationException}: una suite
 * puede estar entera en verde y no haber ejecutado nunca el codigo que importa.</p>
 */
@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
@TestPropertySource(properties = "vitialert.security.api-key=clave-de-prueba")
@Transactional
class ApiKeyFilterTest {

    private static final String CLAVE = "clave-de-prueba";

    private static final String PAYLOAD = """
            {
              "nodo_id": "%s",
              "temperatura_ambiente_c": 28.4,
              "humedad_relativa_pct": 45,
              "humedad_suelo_pct": 22,
              "humedad_suelo_raw": 2730,
              "velocidad_viento_kmh": 18.5,
              "caudal_l_min": 7.80,
              "volumen_total_l": 124.60,
              "valvula_abierta_actual": false,
              "decision_riego_local": false
            }
            """;

    @Autowired
    private MockMvc mockMvc;

    @Test
    void rechazaElPostSinCabeceraDeClave() throws Exception {
        mockMvc.perform(post("/api/data")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(PAYLOAD.formatted("auth-1")))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.status").value(401));
    }

    @Test
    void rechazaElPostConClaveIncorrecta() throws Exception {
        mockMvc.perform(post("/api/data")
                        .header("X-API-Key", "clave-que-no-es")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(PAYLOAD.formatted("auth-2")))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void rechazaUnaClaveQueSoloCoincideEnElPrefijo() throws Exception {
        // MessageDigest.isEqual compara el arreglo completo: un prefijo valido no alcanza.
        mockMvc.perform(post("/api/data")
                        .header("X-API-Key", CLAVE.substring(0, 5))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(PAYLOAD.formatted("auth-3")))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void aceptaElPostConLaClaveCorrectaYRespondeElContratoDelEsp32() throws Exception {
        mockMvc.perform(post("/api/data")
                        .header("X-API-Key", CLAVE)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(PAYLOAD.formatted("auth-4")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.abrir_valvula").exists())
                .andExpect(jsonPath("$.encender_luz").exists());
    }

    @Test
    void dejaPasarLasConsultasGetSinClave() throws Exception {
        // Decision explicita del prototipo: la clave protege la ESCRITURA, para que nadie
        // contamine el dataset. La lectura queda abierta. Este test esta para que el dia que
        // se decida cerrar tambien la lectura, quede claro que hay que cambiarlo.
        mockMvc.perform(get("/health"))
                .andExpect(status().isOk());

        mockMvc.perform(get("/api/nodes"))
                .andExpect(status().isOk());
    }
}
