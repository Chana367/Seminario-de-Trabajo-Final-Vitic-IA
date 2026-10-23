package com.vitialert.backend.repository;

import com.vitialert.backend.domain.Node;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.Optional;

public interface NodeRepository extends JpaRepository<Node, Long> {

    Optional<Node> findByExternalId(String externalId);

    List<Node> findAllByOrderByExternalIdAsc();
}
