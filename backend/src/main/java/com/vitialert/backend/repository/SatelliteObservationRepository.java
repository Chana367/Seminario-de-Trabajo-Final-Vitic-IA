package com.vitialert.backend.repository;

import com.vitialert.backend.domain.SatelliteObservation;
import org.springframework.data.jpa.repository.JpaRepository;

import java.time.Instant;
import java.util.List;

public interface SatelliteObservationRepository extends JpaRepository<SatelliteObservation, Long> {

    List<SatelliteObservation> findByNodeIdAndRetrievedAtBetweenOrderByRetrievedAtAsc(
            Long nodeId, Instant from, Instant to);

    /** Clave natural de una captura: un nodo no tiene dos observaciones del mismo instante. */
    boolean existsByNodeIdAndRetrievedAt(Long nodeId, Instant retrievedAt);
}
