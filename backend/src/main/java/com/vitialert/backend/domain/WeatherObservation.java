package com.vitialert.backend.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.PrePersist;
import jakarta.persistence.PreUpdate;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;

import java.time.Instant;
import java.time.LocalDate;

/**
 * Observacion meteorologica diaria proveniente del Data Miner Python
 * (API de Open-Meteo: ERA5-Seamless historico y pronostico para dias recientes).
 *
 * <p>Se almacena en una tabla separada de {@link TelemetryReading} porque es una
 * fuente distinta, con otra frecuencia y otro origen de verdad.</p>
 */
@Entity
@Table(name = "weather_observation",
        uniqueConstraints = @UniqueConstraint(name = "ux_weather_date_source",
                columnNames = {"observation_date", "source"}))
public class WeatherObservation {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "observation_date", nullable = false)
    private LocalDate observationDate;

    /** Origen del dato, por ejemplo OPEN_METEO_ERA5 u OPEN_METEO_FORECAST. */
    @Column(name = "source", nullable = false, length = 60)
    private String source;

    @Column(name = "temp_max_c")
    private Double tempMaxC;

    @Column(name = "temp_mean_c")
    private Double tempMeanC;

    @Column(name = "humidity_mean_pct")
    private Double humidityMeanPct;

    @Column(name = "humidity_min_pct")
    private Double humidityMinPct;

    @Column(name = "wind_mean_kmh")
    private Double windMeanKmh;

    @Column(name = "wind_max_kmh")
    private Double windMaxKmh;

    @Column(name = "precipitation_mm")
    private Double precipitationMm;

    @Column(name = "solar_radiation_mj_m2")
    private Double solarRadiationMjM2;

    @Column(name = "et0_mm")
    private Double et0Mm;

    @Column(name = "vpd_max_kpa")
    private Double vpdMaxKpa;

    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt;

    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt;

    protected WeatherObservation() {
        // requerido por JPA
    }

    public WeatherObservation(LocalDate observationDate, String source) {
        this.observationDate = observationDate;
        this.source = source;
    }

    @PrePersist
    void onCreate() {
        Instant now = Instant.now();
        this.createdAt = now;
        this.updatedAt = now;
    }

    @PreUpdate
    void onUpdate() {
        this.updatedAt = Instant.now();
    }

    public Long getId() {
        return id;
    }

    public LocalDate getObservationDate() {
        return observationDate;
    }

    public String getSource() {
        return source;
    }

    public Double getTempMaxC() {
        return tempMaxC;
    }

    public void setTempMaxC(Double tempMaxC) {
        this.tempMaxC = tempMaxC;
    }

    public Double getTempMeanC() {
        return tempMeanC;
    }

    public void setTempMeanC(Double tempMeanC) {
        this.tempMeanC = tempMeanC;
    }

    public Double getHumidityMeanPct() {
        return humidityMeanPct;
    }

    public void setHumidityMeanPct(Double humidityMeanPct) {
        this.humidityMeanPct = humidityMeanPct;
    }

    public Double getHumidityMinPct() {
        return humidityMinPct;
    }

    public void setHumidityMinPct(Double humidityMinPct) {
        this.humidityMinPct = humidityMinPct;
    }

    public Double getWindMeanKmh() {
        return windMeanKmh;
    }

    public void setWindMeanKmh(Double windMeanKmh) {
        this.windMeanKmh = windMeanKmh;
    }

    public Double getWindMaxKmh() {
        return windMaxKmh;
    }

    public void setWindMaxKmh(Double windMaxKmh) {
        this.windMaxKmh = windMaxKmh;
    }

    public Double getPrecipitationMm() {
        return precipitationMm;
    }

    public void setPrecipitationMm(Double precipitationMm) {
        this.precipitationMm = precipitationMm;
    }

    public Double getSolarRadiationMjM2() {
        return solarRadiationMjM2;
    }

    public void setSolarRadiationMjM2(Double solarRadiationMjM2) {
        this.solarRadiationMjM2 = solarRadiationMjM2;
    }

    public Double getEt0Mm() {
        return et0Mm;
    }

    public void setEt0Mm(Double et0Mm) {
        this.et0Mm = et0Mm;
    }

    public Double getVpdMaxKpa() {
        return vpdMaxKpa;
    }

    public void setVpdMaxKpa(Double vpdMaxKpa) {
        this.vpdMaxKpa = vpdMaxKpa;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }

    public Instant getUpdatedAt() {
        return updatedAt;
    }
}
