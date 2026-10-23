package com.vitialert.backend.service;

import com.vitialert.backend.config.VitiAlertProperties;
import com.vitialert.backend.domain.IrrigationEvent;
import com.vitialert.backend.domain.IrrigationEventStatus;
import com.vitialert.backend.domain.Node;
import com.vitialert.backend.domain.TelemetryReading;
import com.vitialert.backend.repository.IrrigationEventRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.Optional;

/**
 * Reconstruye los periodos reales de riego a partir de las transiciones de la electrovalvula.
 *
 * <pre>
 * valvula false -&gt; true  =&gt; inicio del evento
 * valvula true  -&gt; false =&gt; fin del evento
 * </pre>
 *
 * <p>Solo se consulta el evento abierto del nodo, que es a lo sumo uno (garantizado por un
 * indice unico parcial en la base): la ingesta de un POST nunca recorre el historico.</p>
 *
 * <p>Las repeticiones del mismo estado son ruido: el ESP32 informa el estado de la valvula en
 * CADA POST, no solo cuando cambia.</p>
 *
 * <p><b>Watchdog.</b> Esa misma garantia de "un solo evento abierto por nodo" es un riesgo: si
 * el nodo se apaga con la valvula abierta, o si se pierde el POST que informaba el cierre, el
 * evento queda en {@code OPEN} para siempre y <em>se traga todos los riegos posteriores del
 * nodo</em>, porque la condicion de apertura exige que no haya ninguno abierto. El resultado
 * seria un unico evento de semanas de duracion y el historial de riego perdido. Por eso, antes
 * de decidir cualquier transicion, un evento que lleva abierto mas de
 * {@code vitialert.irrigation.max-open-hours} se da de baja como
 * {@link IrrigationEventStatus#ABANDONED}.</p>
 *
 * <p>La verificacion es perezosa: corre en la ingesta, que es exactamente cuando hace falta
 * (el nodo volvio y quiere abrir un evento nuevo). No se agrega una tarea programada porque no
 * aportaria nada: un evento colgado solo estorba cuando llega la lectura siguiente.</p>
 */
@Service
public class IrrigationService {

    private static final Logger log = LoggerFactory.getLogger(IrrigationService.class);

    private final IrrigationEventRepository irrigationEventRepository;
    private final Duration maxOpen;

    public IrrigationService(IrrigationEventRepository irrigationEventRepository,
                             VitiAlertProperties properties) {
        this.irrigationEventRepository = irrigationEventRepository;
        this.maxOpen = Duration.ofHours(properties.irrigation().maxOpenHours());
    }

    /** Aplica la lectura recien persistida sobre la maquina de estados del riego. */
    @Transactional
    public Optional<IrrigationEvent> processReading(Node node, TelemetryReading reading) {
        if (reading.getValvulaAbiertaActual() == null) {
            // Sin estado de valvula no se puede inferir la transicion. La lectura ya quedo
            // marcada MISSING y el evento en curso se mantiene tal cual.
            return Optional.empty();
        }

        Instant now = reading.getTimestampReceived();
        Optional<IrrigationEvent> open = findCurrent(node.getId())
                .flatMap(event -> abandonIfStale(node, event, now));
        boolean valveOpen = reading.isValveOpen();

        if (valveOpen && open.isEmpty()) {
            IrrigationEvent saved = irrigationEventRepository.save(
                    new IrrigationEvent(node, now, reading.getVolumenTotalL()));
            log.info("Riego iniciado nodo={} eventoId={} volumenInicial={} L",
                    node.getExternalId(), saved.getId(), reading.getVolumenTotalL());
            return Optional.of(saved);
        }

        if (!valveOpen && open.isPresent()) {
            IrrigationEvent event = open.get();
            event.close(now, reading.getVolumenTotalL());
            IrrigationEvent saved = irrigationEventRepository.save(event);
            if (saved.getEstado() == IrrigationEventStatus.CLOSED_WITH_WARNING) {
                log.warn("Riego finalizado con advertencia nodo={} eventoId={} detalle={}",
                        node.getExternalId(), saved.getId(), saved.getObservaciones());
            } else {
                log.info("Riego finalizado nodo={} eventoId={} duracion={} s volumenAplicado={} L",
                        node.getExternalId(), saved.getId(), saved.getDuracionSegundos(),
                        saved.getVolumenAplicadoL());
            }
            return Optional.of(saved);
        }

        return Optional.empty();
    }

    /**
     * Devuelve el evento si sigue vigente, o vacio si lo dio de baja por antiguedad.
     *
     * <p>Devolver vacio es lo que permite que la lectura actual abra un evento nuevo: el nodo
     * esta informando la valvula abierta ahora, asi que el riego que empieza es este, no aquel.</p>
     */
    private Optional<IrrigationEvent> abandonIfStale(Node node, IrrigationEvent event, Instant now) {
        Duration openFor = Duration.between(event.getStartedAt(), now);
        if (openFor.compareTo(maxOpen) <= 0) {
            return Optional.of(event);
        }

        event.abandon("Watchdog: la valvula figuraba abierta desde " + event.getStartedAt()
                + " (" + openFor.toHours() + " h, maximo " + maxOpen.toHours() + " h) y nunca se "
                + "observo el cierre. Duracion, volumen aplicado y caudal promedio quedan sin "
                + "calcular porque se desconoce el instante de cierre.");
        irrigationEventRepository.save(event);
        log.warn("Riego dado de baja por watchdog nodo={} eventoId={} abiertoHace={} h",
                node.getExternalId(), event.getId(), openFor.toHours());
        return Optional.empty();
    }

    @Transactional(readOnly = true)
    public Optional<IrrigationEvent> findCurrent(Long nodeId) {
        List<IrrigationEvent> open = irrigationEventRepository.findByStatus(
                nodeId, IrrigationEventStatus.OPEN, PageRequest.of(0, 1));
        return open.isEmpty() ? Optional.empty() : Optional.of(open.get(0));
    }

    @Transactional(readOnly = true)
    public Page<IrrigationEvent> findRange(Long nodeId, Instant from, Instant to, Pageable pageable) {
        return irrigationEventRepository.findRange(nodeId, from, to, pageable);
    }
}
