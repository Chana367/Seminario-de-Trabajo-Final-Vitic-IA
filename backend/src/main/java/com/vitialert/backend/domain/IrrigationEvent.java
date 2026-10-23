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
import java.math.RoundingMode;
import java.time.Duration;
import java.time.Instant;

/**
 * Periodo real de riego reconstruido a partir de las transiciones de la electrovalvula.
 *
 * <pre>
 * valvula false -&gt; true  =&gt; inicio del evento
 * valvula true  -&gt; false =&gt; fin del evento
 * </pre>
 *
 * <p>El volumen aplicado se calcula como {@code volumenFinal - volumenInicial}. Si el
 * contador acumulado del ESP32 se reinicia durante el riego la resta da negativo; en ese
 * caso se asume que el contador arranco de cero y el evento queda marcado como
 * {@link IrrigationEventStatus#CLOSED_WITH_WARNING} para no contaminar el dataset.</p>
 */
@Entity
@Table(name = "irrigation_event")
public class IrrigationEvent {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "node_id", nullable = false)
    private Node node;

    @Column(name = "started_at", nullable = false)
    private Instant startedAt;

    @Column(name = "ended_at")
    private Instant endedAt;

    @Column(name = "duracion_segundos")
    private Long duracionSegundos;

    @Column(name = "volumen_inicial_l", precision = 12, scale = 3)
    private BigDecimal volumenInicialL;

    @Column(name = "volumen_final_l", precision = 12, scale = 3)
    private BigDecimal volumenFinalL;

    @Column(name = "volumen_aplicado_l", precision = 12, scale = 3)
    private BigDecimal volumenAplicadoL;

    @Column(name = "caudal_promedio_l_min", precision = 10, scale = 3)
    private BigDecimal caudalPromedioLMin;

    @Enumerated(EnumType.STRING)
    @Column(name = "estado", nullable = false, length = 25)
    private IrrigationEventStatus estado;

    @Column(name = "observaciones", length = 500)
    private String observaciones;

    protected IrrigationEvent() {
        // requerido por JPA
    }

    public IrrigationEvent(Node node, Instant startedAt, BigDecimal volumenInicialL) {
        this.node = node;
        this.startedAt = startedAt;
        this.volumenInicialL = volumenInicialL;
        this.estado = IrrigationEventStatus.OPEN;
    }

    /**
     * Cierra el evento calculando duracion, volumen aplicado y caudal promedio.
     *
     * @param endedAt      instante en el que se detecto el cierre de la valvula
     * @param volumenFinal contador acumulado informado por el nodo en ese instante
     */
    public void close(Instant endedAt, BigDecimal volumenFinal) {
        this.endedAt = endedAt;
        this.volumenFinalL = volumenFinal;
        this.duracionSegundos = Math.max(0L, Duration.between(startedAt, endedAt).getSeconds());

        if (volumenInicialL == null || volumenFinal == null) {
            this.estado = IrrigationEventStatus.CLOSED_WITH_WARNING;
            this.observaciones = "Volumen acumulado ausente: no se puede calcular el volumen aplicado.";
            return;
        }

        BigDecimal aplicado = volumenFinal.subtract(volumenInicialL);
        if (aplicado.signum() < 0) {
            // El contador del ESP32 se reinicio durante el riego (reboot del nodo).
            this.volumenAplicadoL = volumenFinal;
            this.estado = IrrigationEventStatus.CLOSED_WITH_WARNING;
            this.observaciones = "Contador de volumen reiniciado durante el riego (inicial="
                    + volumenInicialL.toPlainString() + " L, final=" + volumenFinal.toPlainString()
                    + " L). Se asume reinicio desde cero.";
        } else {
            this.volumenAplicadoL = aplicado;
            this.estado = IrrigationEventStatus.CLOSED;
        }

        if (duracionSegundos != null && duracionSegundos > 0 && volumenAplicadoL != null) {
            BigDecimal minutos = BigDecimal.valueOf(duracionSegundos)
                    .divide(BigDecimal.valueOf(60), 6, RoundingMode.HALF_UP);
            if (minutos.signum() > 0) {
                this.caudalPromedioLMin = volumenAplicadoL.divide(minutos, 3, RoundingMode.HALF_UP);
            }
        }
    }

    /**
     * Da de baja un evento cuyo cierre nunca se observo.
     *
     * <p>A diferencia de {@link #close(Instant, BigDecimal)}, aca NO se calcula duracion,
     * volumen aplicado ni caudal promedio: no se sabe cuando cerro la valvula, y el invariante
     * del proyecto es que un dato desconocido queda en null y jamas se reemplaza por un valor
     * inventado. Inferir el cierre a partir de la ultima lectura seria fabricar el instante
     * mas importante del evento.</p>
     *
     * <p>El efecto lateral buscado es liberar el indice unico parcial
     * {@code ux_irrigation_open_per_node}: mientras este evento siga en {@code OPEN}, ningun
     * riego posterior del nodo puede abrir uno nuevo y todos quedarian absorbidos por este.</p>
     *
     * @param motivo explicacion que queda registrada en el evento para la trazabilidad
     */
    public void abandon(String motivo) {
        this.estado = IrrigationEventStatus.ABANDONED;
        this.observaciones = motivo;
    }

    public Long getId() {
        return id;
    }

    public Node getNode() {
        return node;
    }

    public Instant getStartedAt() {
        return startedAt;
    }

    public Instant getEndedAt() {
        return endedAt;
    }

    public Long getDuracionSegundos() {
        return duracionSegundos;
    }

    public BigDecimal getVolumenInicialL() {
        return volumenInicialL;
    }

    public BigDecimal getVolumenFinalL() {
        return volumenFinalL;
    }

    public BigDecimal getVolumenAplicadoL() {
        return volumenAplicadoL;
    }

    public BigDecimal getCaudalPromedioLMin() {
        return caudalPromedioLMin;
    }

    public IrrigationEventStatus getEstado() {
        return estado;
    }

    public String getObservaciones() {
        return observaciones;
    }

    public boolean isOpen() {
        return estado == IrrigationEventStatus.OPEN;
    }
}
