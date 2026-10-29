"""Resumen de cuatro páginas para compartir el cierre experimental."""
from pathlib import Path
import json

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, PageBreak

ROOT = Path(__file__).resolve().parents[1]
WIDTH, HEIGHT = A4
NAVY = colors.HexColor("#203b49")
TEAL = colors.HexColor("#1b6076")
GRAY = colors.HexColor("#52616a")


def n(v, decimals=0):
    return f"{v:,.{decimals}f}".translate(str.maketrans({",": ".", ".": ","}))


def main():
    fonts = Path("C:/Windows/Fonts")
    if (fonts / "segoeui.ttf").exists():
        pdfmetrics.registerFont(TTFont("Body", str(fonts / "segoeui.ttf")))
        pdfmetrics.registerFont(TTFont("Body-Bold", str(fonts / "segoeuib.ttf")))
        pdfmetrics.registerFontFamily("Body", normal="Body", bold="Body-Bold", italic="Body", boldItalic="Body-Bold")
        regular, bold = "Body", "Body-Bold"
    else:
        regular, bold = "Helvetica", "Helvetica-Bold"
    styles = {
        "body": ParagraphStyle("body", fontName=regular, fontSize=10, leading=14, textColor=NAVY, spaceAfter=8),
        "small": ParagraphStyle("small", fontName=regular, fontSize=8.7, leading=12, textColor=GRAY, spaceAfter=6),
        "title": ParagraphStyle("title", fontName=bold, fontSize=24, leading=29, textColor=NAVY, spaceAfter=12),
        "h1": ParagraphStyle("h1", fontName=bold, fontSize=18, leading=23, textColor=NAVY, spaceAfter=13),
        "h2": ParagraphStyle("h2", fontName=bold, fontSize=11.5, leading=16, textColor=TEAL, spaceBefore=6, spaceAfter=7),
        "cell": ParagraphStyle("cell", fontName=regular, fontSize=9.1, leading=12, textColor=NAVY),
        "head": ParagraphStyle("head", fontName=bold, fontSize=9.1, leading=12, textColor=colors.white),
    }
    s = json.loads((ROOT / "RESUMEN_RESULTADOS.json").read_text(encoding="utf-8"))
    m = s["fixed_holdout"]
    story = []

    def p(text, style="body"):
        story.append(Paragraph(text, styles[style]))

    def table(rows, widths):
        cells = [[Paragraph(str(v), styles["head"] if i == 0 else styles["cell"]) for v in row] for i, row in enumerate(rows)]
        t = Table(cells, colWidths=widths, hAlign="LEFT")
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), TEAL), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                               ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                               ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                               ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#f0f4f4"), colors.white]),
                               ("LINEBELOW", (0, -1), (-1, -1), .4, colors.HexColor("#c6d0d4"))]))
        story.extend([t, Spacer(1, 10)])

    def image(name, width=493):
        path = ROOT / "graficos" / name
        from PIL import Image as PILImage
        with PILImage.open(path) as pic:
            w, h = pic.size
        story.extend([Image(str(path), width=width, height=width * h / w), Spacer(1, 7)])

    p("EQUIPO VITIALERT  |  CIERRE EXPERIMENTAL", "small")
    p("Resultados de la campaña", "title")
    p("Corte: <b>28 de octubre de 2026, 16:00 (Argentina)</b>. Nodo 1. Última lectura incluida: 15:59:58.")
    p("Mejora relativa observada; precisión operativa pendiente", "h2")
    p("El sistema permitió adquirir, respaldar e integrar datos y entrenar un pronóstico de humedad a 24 horas. El modelo superó a persistencia en el bloque temporal, pero el error absoluto sigue siendo alto. La hipótesis recibe <b>apoyo parcial, sin confirmación robusta</b>.")
    table([["Prueba sobre las mismas 55 horas", "MAE", "RMSE", "R²"],
           ["Modelo conservado del 22/10", n(m["old_model"]["mae_pp"], 2), n(m["old_model"]["rmse_pp"], 2), n(m["old_model"]["r2"], 3)],
           ["Gradient Boosting con integración disponible", n(m["model"]["mae_pp"], 2), n(m["model"]["rmse_pp"], 2), n(m["model"]["r2"], 3)],
           ["Persistencia", n(m["persistence"]["mae_pp"], 2), n(m["persistence"]["rmse_pp"], 2), n(m["persistence"]["r2"], 3)]], [277, 67, 75, 74])
    p("<b>20,35% menos MAE</b> frente a persistencia; habilidad RMSE <b>0,0882</b>. Las unidades de error son puntos de la escala relativa del sensor. Estas cifras no son porcentaje de acierto ni agua ahorrada.")
    image("03_comparacion_mismo_periodo.png", 465)
    p("La prueba reconstruye un ajuste con corte de entrenamiento al 24/10 y 74 pares. No fue una campaña prospectiva. El artefacto final usa los 153 pares conocidos al cierre y necesita datos posteriores para una evaluación independiente.", "small")
    story.append(PageBreak())

    p("Captura e instrumentación", "h1")
    table([["Evidencia de octubre", "Corte 22/10", "Corte 28/10"],
           ["Lecturas conservadas", "7.150", "21.106"], ["Horas de suelo con cobertura", "118", "233"],
           ["Pares medidos a 24 horas", "70", "153"], ["Fechas con alguna lectura", "9", "15"]], [293, 100, 100])
    p("DHT22: se conservaron sus lecturas válidas", "h2")
    p("El DHT estuvo completo en <b>1.690 de 1.690 lecturas del 28/10</b>. En toda la serie hay 42 horas con cobertura suficiente, pero solo <b>tres pares a 24 horas</b> tienen DHT en el origen. El entrenamiento congelado incluye uno; añadir DHT no cambió la métrica del bloque.")
    image("01_captura_y_dht.png", 465)
    p("Caudal: ahora hay circulación registrada", "h2")
    p("Después del corte anterior, 333 ciclos cerrados reportaron volumen positivo sin advertencia del backend. Mediana: <b>1,54 L y 17 segundos</b>. La suma de incrementos reportada fue 576,83 L, sin calibración independiente.")
    p("<b>El agua recircula.</b> La suma del contador no equivale a consumo neto, dosis absorbida por el suelo ni ahorro. Hay descensos del contador, alertas y ciclos atípicos conservados para revisión. El caudal no se incorporó como dosis del suelo en el modelo.", "small")
    story.append(PageBreak())

    p("Validación temporal y errores", "h1")
    p("Se reconstruyó retrospectivamente un ajuste con corte de entrenamiento al <b>24/10 a las 16:00</b>, usando 74 pares con respuestas anteriores a ese momento. La prueba incluye 55 de 72 orígenes posibles, con respuestas del 25 al 28/10. El ajuste se mantuvo fijo dentro del bloque.")
    image("02_prueba_temporal.png", 493)
    table([["Fecha de respuesta", "Casos", "MAE modelo", "MAE persistencia"],
           ["25/10", "6", "65,76", "67,27"], ["26/10", "18", "42,81", "47,44"],
           ["27/10", "16", "5,67", "37,84"], ["28/10", "15", "61,96", "58,71"]], [170, 75, 124, 124])
    p("La mejora no es uniforme", "h2")
    p("El 28/10 el ajuste congelado fue peor que persistencia. Al omitir el 27/10 solo como diagnóstico, la habilidad RMSE cae de 0,0882 a 0,0061. No se eliminó ese día del resultado publicado. Cuatro fechas no bastan para asegurar estabilidad.")
    p("El entrenamiento tenía respuestas entre <b>15,27 y 47,48</b>; la prueba llegó a <b>92,24</b>. El montaje recibió intervenciones manuales sin agenda cuantificada como entrada del pronóstico. Esto es compatible con un cambio de régimen, sin demostrar la causa exacta de cada error.")
    p("Como complemento, la estrategia de origen móvil obtuvo MAE 18,19 frente a 29,91 de persistencia, en 105 pronósticos de ocho fechas. Esa estrategia se reajusta con nuevas respuestas; no es la evaluación del artefacto final ni del bloque fijo.", "small")
    story.append(PageBreak())

    p("Conclusión y alcance de la hipótesis", "h1")
    p('El borrador v4 propone que la integración temporalmente consistente de IoT, meteorología y satélite permita estimar la humedad a 24 horas con menor error que persistencia. Se conserva esa hipótesis; no se cambia para acomodar el resultado.')
    table([["Afirmación", "Conclusión del cierre"],
           ["Menor error medio que persistencia en el bloque", "Sí: mejora descriptiva de 20,35% en MAE."],
           ["Predicción precisa para decidir riego", "No demostrada: MAE alto y R² negativo."],
           ["Ganancia estable por integrar fuentes adicionales", "No demostrada; diferencia pequeña e inestable."],
           ["Ahorro de agua o dosis aplicada al suelo", "No medidos; el circuito recircula agua."],
           ["Viabilidad de adquisición y evaluación reproducible", "Demostrada en la maqueta, con respaldo y controles."]], [233, 260])
    p("Por qué la integración no alcanzó", "h2")
    p("Se recuperaron 86 filas meteorológicas de 50 fechas y 12 capturas satelitales. Se restringió cada entrada a información disponible antes de su origen. Los índices Sentinel presentes repiten 0,2354 y -0,0115; en el entrenamiento congelado no hay variación numérica para aprender un efecto de vegetación. GOES no tiene valores utilizables en ese entrenamiento. El DHT aporta un solo par.")
    p("Con suelo/horario el MAE fijo fue <b>39,836</b>; con integración, <b>39,731</b>: solo 0,105 puntos de diferencia. En origen móvil, integrar fue ligeramente peor que suelo. No se puede atribuir causalmente la mejora frente a persistencia al DHT, al caudal o al satélite.")
    p("Conclusión para la defensa", "h2")
    p("<b>La hipótesis recibe apoyo parcial.</b> El resultado numérico frente a la referencia fue favorable en esta maqueta, con precisión y diversidad insuficientes para considerarlo una confirmación robusta o una recomendación de riego validada. Se logró una plataforma funcional y un procedimiento que permite comprobar sus límites.")
    p("Prioridades de continuidad", "h2")
    p("Medir y calibrar la dosis aplicada al sustrato; registrar horarios y cantidades de intervenciones; repetir ciclos húmedo-seco; sostener el DHT; conservar versiones de clima e identificar escenas satelitales; evaluar un candidato congelado con datos posteriores.")
    p("Fuentes: respaldo PostgreSQL y respuestas GET de esta entrega; resultados del 22/10; registro de intervenciones; borrador v4, pp. 8 y 29. Método: <link href='https://otexts.com/fpp3/toolbox.html#time-series-cross-validation' color='#1b6076'>Forecasting: Principles and Practice</link>. Estimador: <link href='https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.HistGradientBoostingRegressor.html' color='#1b6076'>documentación oficial de scikit-learn</link>. El detalle reproducible y los hashes acompañan el informe.", "small")

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#ced7da"))
        canvas.line(46, 37, WIDTH - 46, 37)
        canvas.setFillColor(GRAY)
        canvas.setFont(regular, 8)
        canvas.drawString(46, 24, "VitiAlert | Corte 28/10/2026, 16:00 Argentina | Maqueta experimental")
        canvas.drawRightString(WIDTH - 46, 24, str(doc.page))
        canvas.restoreState()

    target = ROOT / "RESUMEN_PARA_EL_EQUIPO.pdf"
    doc = SimpleDocTemplate(str(target), pagesize=A4, topMargin=43, bottomMargin=48,
                            leftMargin=46, rightMargin=46, title="VitiAlert - cierre de campaña 28 de octubre de 2026", author="Equipo VitiAlert")
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    print(target)


if __name__ == "__main__":
    main()
