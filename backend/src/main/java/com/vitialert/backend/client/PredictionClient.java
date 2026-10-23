package com.vitialert.backend.client;

import com.vitialert.backend.config.VitiAlertProperties;
import com.vitialert.backend.dto.FeatureVector;
import com.vitialert.backend.dto.PredictionRequest;
import com.vitialert.backend.dto.PredictionResponse;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.MediaType;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

import java.util.Optional;

/**
 * Unico punto de contacto con el modelo de Ciencia de Datos.
 *
 * <p>Reparto de responsabilidades del proyecto:</p>
 * <ul>
 *   <li><b>Python</b>: entrenar, evaluar, serializar (.pkl) e inferir.</li>
 *   <li><b>Java</b>: recibir, validar, persistir, integrar, construir features, consultar la
 *       inferencia, decidir y responder al ESP32.</li>
 * </ul>
 *
 * <p><b>Java nunca carga un .pkl.</b> Un pickle ataria la version del modelo a la del backend
 * y obligaria a un puente que habria que revalidar. Por HTTP, el modelo se reentrena y
 * redespliega sin tocar Java.</p>
 *
 * <p>Apagado por defecto: mientras lo este no se hace ninguna llamada de red y la valvula
 * sigue gobernada por {@code decision_riego_local}.</p>
 */
@Component
public class PredictionClient {

    private static final Logger log = LoggerFactory.getLogger(PredictionClient.class);

    private final RestClient restClient;
    private final VitiAlertProperties.Ml properties;

    public PredictionClient(VitiAlertProperties properties) {
        this.properties = properties.ml();
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
     * Consulta la inferencia. Las features viajan con los mismos nombres que las columnas del
     * CSV de entrenamiento, y los faltantes como {@code null} explicito.
     *
     * @return vacio si el modelo esta apagado o el servicio no responde a tiempo; el llamador
     * aplica entonces el fallback local
     */
    public Optional<PredictionResponse> predict(FeatureVector features) {
        if (!properties.enabled()) {
            return Optional.empty();
        }
        try {
            PredictionResponse response = restClient.post()
                    .uri(properties.predictPath())
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(new PredictionRequest(features.nodeId(), features.timestamp(), features.predictorMap()))
                    .retrieve()
                    .body(PredictionResponse.class);
            return Optional.ofNullable(response);
        } catch (RuntimeException ex) {
            log.warn("Servicio de inferencia no disponible (nodo={}): {}", features.nodeId(), ex.getMessage());
            return Optional.empty();
        }
    }
}
