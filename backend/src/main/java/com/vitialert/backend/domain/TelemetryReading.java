package com.vitialert.backend.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;

import java.math.BigDecimal;
import java.time.Instant;

/**
 * Lectura INMUTABLE generada por cada POST del ESP32.
 *
 * <p>Nunca se sobrescribe ni se actualiza: cada payload recibido produce una fila
 * nueva. Por eso la clase no expone setters y se construye con {@link Builder}.</p>
 *
 * <p>Los valores relacionados con agua ({@code caudalLMin}, {@code volumenTotalL})
 * usan {@link BigDecimal} porque el volumen es un contador acumulado sobre el que
 * se hacen restas para calcular el consumo de cada riego. Las variables ambientales
 * usan {@link Double}: su precision esta limitada por el sensor, no por el tipo.</p>
 */
@Entity
@Table(name = "telemetry_reading")
public class TelemetryReading {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "node_id", nullable = false)
    private Node node;

    /** Timestamp generado por el backend al recibir el POST. Siempre UTC. */
    @Column(name = "timestamp_received", nullable = false)
    private Instant timestampReceived;

    @Column(name = "temperatura_ambiente_c")
    private Double temperaturaAmbienteC;

    @Column(name = "humedad_relativa_pct")
    private Double humedadRelativaPct;

    @Column(name = "humedad_suelo_pct")
    private Double humedadSueloPct;

    @Column(name = "humedad_suelo_raw")
    private Integer humedadSueloRaw;

    @Column(name = "velocidad_viento_kmh")
    private Double velocidadVientoKmh;

    @Column(name = "caudal_l_min", precision = 10, scale = 3)
    private BigDecimal caudalLMin;

    @Column(name = "volumen_total_l", precision = 12, scale = 3)
    private BigDecimal volumenTotalL;

    @Column(name = "valvula_abierta_actual")
    private Boolean valvulaAbiertaActual;

    @Column(name = "decision_riego_local")
    private Boolean decisionRiegoLocal;

    @Enumerated(EnumType.STRING)
    @Column(name = "quality_flag", nullable = false, length = 20)
    private QualityFlag qualityFlag;

    @Column(name = "quality_notes", length = 500)
    private String qualityNotes;

    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt;

    protected TelemetryReading() {
        // requerido por JPA
    }

    private TelemetryReading(Builder builder) {
        this.node = builder.node;
        this.timestampReceived = builder.timestampReceived;
        this.temperaturaAmbienteC = builder.temperaturaAmbienteC;
        this.humedadRelativaPct = builder.humedadRelativaPct;
        this.humedadSueloPct = builder.humedadSueloPct;
        this.humedadSueloRaw = builder.humedadSueloRaw;
        this.velocidadVientoKmh = builder.velocidadVientoKmh;
        this.caudalLMin = builder.caudalLMin;
        this.volumenTotalL = builder.volumenTotalL;
        this.valvulaAbiertaActual = builder.valvulaAbiertaActual;
        this.decisionRiegoLocal = builder.decisionRiegoLocal;
        this.qualityFlag = builder.qualityFlag == null ? QualityFlag.VALID : builder.qualityFlag;
        this.qualityNotes = builder.qualityNotes;
        this.createdAt = Instant.now();
    }

    public static Builder builder() {
        return new Builder();
    }

    public Long getId() {
        return id;
    }

    public Node getNode() {
        return node;
    }

    public Instant getTimestampReceived() {
        return timestampReceived;
    }

    public Double getTemperaturaAmbienteC() {
        return temperaturaAmbienteC;
    }

    public Double getHumedadRelativaPct() {
        return humedadRelativaPct;
    }

    public Double getHumedadSueloPct() {
        return humedadSueloPct;
    }

    public Integer getHumedadSueloRaw() {
        return humedadSueloRaw;
    }

    public Double getVelocidadVientoKmh() {
        return velocidadVientoKmh;
    }

    public BigDecimal getCaudalLMin() {
        return caudalLMin;
    }

    public BigDecimal getVolumenTotalL() {
        return volumenTotalL;
    }

    public Boolean getValvulaAbiertaActual() {
        return valvulaAbiertaActual;
    }

    public Boolean getDecisionRiegoLocal() {
        return decisionRiegoLocal;
    }

    public QualityFlag getQualityFlag() {
        return qualityFlag;
    }

    public String getQualityNotes() {
        return qualityNotes;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }

    /** true unicamente si el firmware informo explicitamente la valvula abierta. */
    public boolean isValveOpen() {
        return Boolean.TRUE.equals(valvulaAbiertaActual);
    }

    /** true unicamente si el firmware informo explicitamente la decision local de regar. */
    public boolean isLocalIrrigationDecision() {
        return Boolean.TRUE.equals(decisionRiegoLocal);
    }

    public static final class Builder {

        private Node node;
        private Instant timestampReceived;
        private Double temperaturaAmbienteC;
        private Double humedadRelativaPct;
        private Double humedadSueloPct;
        private Integer humedadSueloRaw;
        private Double velocidadVientoKmh;
        private BigDecimal caudalLMin;
        private BigDecimal volumenTotalL;
        private Boolean valvulaAbiertaActual;
        private Boolean decisionRiegoLocal;
        private QualityFlag qualityFlag;
        private String qualityNotes;

        public Builder node(Node node) {
            this.node = node;
            return this;
        }

        public Builder timestampReceived(Instant timestampReceived) {
            this.timestampReceived = timestampReceived;
            return this;
        }

        public Builder temperaturaAmbienteC(Double value) {
            this.temperaturaAmbienteC = value;
            return this;
        }

        public Builder humedadRelativaPct(Double value) {
            this.humedadRelativaPct = value;
            return this;
        }

        public Builder humedadSueloPct(Double value) {
            this.humedadSueloPct = value;
            return this;
        }

        public Builder humedadSueloRaw(Integer value) {
            this.humedadSueloRaw = value;
            return this;
        }

        public Builder velocidadVientoKmh(Double value) {
            this.velocidadVientoKmh = value;
            return this;
        }

        public Builder caudalLMin(BigDecimal value) {
            this.caudalLMin = value;
            return this;
        }

        public Builder volumenTotalL(BigDecimal value) {
            this.volumenTotalL = value;
            return this;
        }

        public Builder valvulaAbiertaActual(Boolean value) {
            this.valvulaAbiertaActual = value;
            return this;
        }

        public Builder decisionRiegoLocal(Boolean value) {
            this.decisionRiegoLocal = value;
            return this;
        }

        public Builder quality(QualityFlag flag, String notes) {
            this.qualityFlag = flag;
            this.qualityNotes = notes;
            return this;
        }

        public TelemetryReading build() {
            if (node == null) {
                throw new IllegalStateException("node es obligatorio");
            }
            if (timestampReceived == null) {
                throw new IllegalStateException("timestampReceived es obligatorio");
            }
            return new TelemetryReading(this);
        }
    }
}
