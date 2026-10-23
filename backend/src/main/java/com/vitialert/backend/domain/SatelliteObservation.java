package com.vitialert.backend.domain;

import com.vitialert.backend.dto.SatelliteFeaturesDto;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;

import java.time.Instant;
import java.time.LocalDate;

/** Captura inmutable del contexto GOES/Sentinel devuelto por VitiAI. */
@Entity
@Table(name = "satellite_observation")
public class SatelliteObservation {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "node_id", nullable = false)
    private Node node;

    @Column(name = "retrieved_at", nullable = false)
    private Instant retrievedAt;
    @Column(name = "goes_observation_time")
    private Instant goesObservationTime;
    @Column(name = "sentinel_image_date")
    private LocalDate sentinelImageDate;
    @Column(name = "cloud_top_temperature_c")
    private Double cloudTopTemperatureC;
    @Column(name = "cloud_temperature_delta_c")
    private Double cloudTemperatureDeltaC;
    @Column(name = "cloud_fraction")
    private Double cloudFraction;
    @Column(name = "rainfall_rate_mm_h")
    private Double rainfallRateMmH;
    @Column(name = "ndvi_mean")
    private Double ndviMean;
    @Column(name = "ndmi_mean")
    private Double ndmiMean;
    @Column(name = "overall_quality", length = 30)
    private String overallQuality;

    protected SatelliteObservation() { }

    public static SatelliteObservation from(Node node, SatelliteFeaturesDto dto) {
        SatelliteObservation observation = new SatelliteObservation();
        observation.node = node;
        observation.retrievedAt = dto.timestamp() == null ? Instant.now() : dto.timestamp();
        if (dto.goes() != null) {
            observation.goesObservationTime = dto.goes().observationTime();
            observation.cloudTopTemperatureC = dto.goes().cloudTopTemperatureC();
            observation.cloudTemperatureDeltaC = dto.goes().cloudTemperatureDeltaC();
            observation.cloudFraction = dto.goes().cloudFraction();
            observation.rainfallRateMmH = dto.goes().rainfallRateMmH();
        }
        if (dto.sentinel() != null) {
            observation.sentinelImageDate = dto.sentinel().imageDate();
            observation.ndviMean = dto.sentinel().ndviMean();
            observation.ndmiMean = dto.sentinel().ndmiMean();
        }
        observation.overallQuality = dto.overallQuality();
        return observation;
    }

    public Long getId() { return id; }
    public Node getNode() { return node; }
    public Instant getRetrievedAt() { return retrievedAt; }
    public Instant getGoesObservationTime() { return goesObservationTime; }
    public LocalDate getSentinelImageDate() { return sentinelImageDate; }
    public Double getCloudTopTemperatureC() { return cloudTopTemperatureC; }
    public Double getCloudTemperatureDeltaC() { return cloudTemperatureDeltaC; }
    public Double getCloudFraction() { return cloudFraction; }
    public Double getRainfallRateMmH() { return rainfallRateMmH; }
    public Double getNdviMean() { return ndviMean; }
    public Double getNdmiMean() { return ndmiMean; }
    public String getOverallQuality() { return overallQuality; }
}
