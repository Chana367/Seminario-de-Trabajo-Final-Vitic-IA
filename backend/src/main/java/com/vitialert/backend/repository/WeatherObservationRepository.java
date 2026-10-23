package com.vitialert.backend.repository;

import com.vitialert.backend.domain.WeatherObservation;
import org.springframework.data.jpa.repository.JpaRepository;

import java.time.LocalDate;
import java.util.List;
import java.util.Optional;

public interface WeatherObservationRepository extends JpaRepository<WeatherObservation, Long> {

    Optional<WeatherObservation> findByObservationDateAndSource(LocalDate observationDate, String source);

    List<WeatherObservation> findByObservationDateBetweenOrderByObservationDateAscSourceAsc(LocalDate from, LocalDate to);
}
