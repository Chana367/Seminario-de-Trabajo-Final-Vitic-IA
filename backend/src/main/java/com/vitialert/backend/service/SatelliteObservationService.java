package com.vitialert.backend.service;

import com.vitialert.backend.client.SatelliteClient;
import com.vitialert.backend.domain.Node;
import com.vitialert.backend.domain.SatelliteObservation;
import com.vitialert.backend.dto.SatelliteFeaturesDto;
import com.vitialert.backend.repository.NodeRepository;
import com.vitialert.backend.repository.SatelliteObservationRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.stereotype.Service;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Persiste capturas satelitales sin bloquear nunca la ingesta IoT.
 *
 * <p><b>Sin {@code @Transactional} a proposito.</b> El metodo hace una llamada HTTP por nodo
 * contra VitiAI, que corre en el plan gratuito de Render y puede tardar hasta un minuto y medio
 * en despertar. Envolver todo en una transaccion mantendria tomada una conexion del pool
 * durante N x timeout segundos mientras se espera la red; la base gratuita admite pocas
 * conexiones simultaneas y la ingesta del ESP32 comparte ese pool. Cada {@code save} abre su
 * propia transaccion corta, que es todo lo que hace falta: las capturas son independientes
 * entre si y guardar la del nodo 1 no depende de que la del nodo 2 funcione.</p>
 *
 * <p><b>Idempotencia.</b> Una captura queda identificada por (nodo, instante de captura). Si
 * VitiAI devuelve la misma imagen dos veces (reintento del workflow diario, o dos llamadas
 * seguidas dentro del mismo ciclo GOES) la fila ya existe y se omite, igual que hace el import
 * meteorologico con su clave (fecha, fuente). Sin esto, cada reintento agregaria una fila
 * identica y la tabla creceria sin aportar informacion nueva.</p>
 */
@Service
public class SatelliteObservationService {

    private static final Logger log = LoggerFactory.getLogger(SatelliteObservationService.class);

    private final NodeRepository nodeRepository;
    private final SatelliteObservationRepository repository;
    private final SatelliteClient client;

    public SatelliteObservationService(NodeRepository nodeRepository,
                                       SatelliteObservationRepository repository,
                                       SatelliteClient client) {
        this.nodeRepository = nodeRepository;
        this.repository = repository;
        this.client = client;
    }

    public Map<String, Object> refreshAll() {
        List<Node> nodes = nodeRepository.findAllByOrderByExternalIdAsc();

        int eligible = 0;
        int stored = 0;
        int duplicates = 0;
        int unavailable = 0;

        for (Node node : nodes) {
            if (node.getLatitud() == null || node.getLongitud() == null) {
                continue;
            }
            eligible++;

            var features = client.fetchFeatures(node.getLatitud(), node.getLongitud());
            if (features.isEmpty()) {
                unavailable++;
                continue;
            }

            if (store(node, features.get())) {
                stored++;
            } else {
                duplicates++;
            }
        }

        if (eligible > 0 && stored == 0) {
            // El workflow diario recibe 200 igual: la falla satelital jamas debe tumbar la
            // sincronizacion. Pero tiene que quedar registrada, porque si no se ve, el dataset
            // se queda sin columnas satelitales durante semanas y nadie se entera.
            log.warn("Refresco satelital sin capturas nuevas: nodos={} sinRespuesta={} duplicadas={} "
                            + "satelliteEnabled={}. Revisar si VitiAI esta despierto y si el timeout alcanza.",
                    eligible, unavailable, duplicates, client.isEnabled());
        }

        Map<String, Object> result = new LinkedHashMap<>();
        result.put("eligible_nodes", eligible);
        result.put("stored_observations", stored);
        result.put("skipped_duplicates", duplicates);
        result.put("unavailable_nodes", unavailable);
        result.put("satellite_enabled", client.isEnabled());
        return result;
    }

    /**
     * Guarda la captura salvo que ya exista.
     *
     * @return {@code true} si se guardo, {@code false} si ya estaba
     *
     * <p>La consulta previa resuelve el caso normal y la restriccion unica de la base es la
     * garantia real: si dos refrescos corren a la vez, uno de los dos choca contra el indice y
     * se descarta en vez de duplicar.</p>
     */
    private boolean store(Node node, SatelliteFeaturesDto features) {
        SatelliteObservation observation = SatelliteObservation.from(node, features);
        if (repository.existsByNodeIdAndRetrievedAt(node.getId(), observation.getRetrievedAt())) {
            return false;
        }
        try {
            repository.save(observation);
            return true;
        } catch (DataIntegrityViolationException ex) {
            return false;
        }
    }
}
