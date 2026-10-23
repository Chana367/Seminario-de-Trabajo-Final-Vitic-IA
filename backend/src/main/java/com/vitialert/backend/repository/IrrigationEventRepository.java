package com.vitialert.backend.repository;

import com.vitialert.backend.domain.IrrigationEvent;
import com.vitialert.backend.domain.IrrigationEventStatus;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.EntityGraph;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.time.Instant;
import java.util.List;

public interface IrrigationEventRepository extends JpaRepository<IrrigationEvent, Long> {

    /** Eventos del nodo en un estado dado. Usar con {@code PageRequest.of(0, 1)} para el abierto. */
    @Query("""
            select e from IrrigationEvent e
            where e.node.id = :nodeId and e.estado = :estado
            order by e.startedAt desc
            """)
    List<IrrigationEvent> findByStatus(@Param("nodeId") Long nodeId,
                                       @Param("estado") IrrigationEventStatus estado,
                                       Pageable pageable);

    /** El {@code @EntityGraph} evita LazyInitializationException al mapear a DTO fuera de la transaccion. */
    @EntityGraph(attributePaths = "node")
    @Query(value = """
            select e from IrrigationEvent e
            where e.node.id = :nodeId
              and e.startedAt >= :from
              and e.startedAt <= :to
            order by e.startedAt desc
            """,
            countQuery = """
                    select count(e) from IrrigationEvent e
                    where e.node.id = :nodeId
                      and e.startedAt >= :from
                      and e.startedAt <= :to
                    """)
    Page<IrrigationEvent> findRange(@Param("nodeId") Long nodeId,
                                    @Param("from") Instant from,
                                    @Param("to") Instant to,
                                    Pageable pageable);
}
