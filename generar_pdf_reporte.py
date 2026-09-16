import os
import sys
from datetime import datetime

try:
    from reportlab.lib.pagesizes import letter, A4
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether, HRFlowable
    )
    from reportlab.pdfgen import canvas
except ImportError:
    print("ReportLab no está instalado todavía")
    sys.exit(1)

class NumberedCanvas(canvas.Canvas):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, page_count):
        self.saveState()
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#64748b"))
        
        # Header (pages > 1)
        if self._pageNumber > 1:
            self.drawString(36, 810, "PROLAGO CARORA 2026 — Informe Ejecutivo de Actualizaciones del Sistema")
            self.setStrokeColor(colors.HexColor("#cbd5e1"))
            self.setLineWidth(0.5)
            self.line(36, 804, 559, 804)

        # Footer
        text_footer = "PROLAGO C.A. • RIF: J-50493821-0 • Carora, Estado Lara — Documento Oficial de Entrega"
        self.drawString(36, 25, text_footer)
        page_text = f"Página {self._pageNumber} de {page_count}"
        self.drawRightString(559, 25, page_text)
        self.setStrokeColor(colors.HexColor("#cbd5e1"))
        self.setLineWidth(0.5)
        self.line(36, 35, 559, 35)
        self.restoreState()

def generar_pdf(destino_path):
    doc = SimpleDocTemplate(
        destino_path,
        pagesize=A4,
        leftMargin=36,
        rightMargin=36,
        topMargin=42,
        bottomMargin=46
    )

    styles = getSampleStyleSheet()
    
    # Custom styles
    color_wine = colors.HexColor("#8B1E24")
    color_dark = colors.HexColor("#0f172a")
    color_slate = colors.HexColor("#334155")
    color_gold = colors.HexColor("#d97706")
    color_emerald = colors.HexColor("#059669")

    style_title = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=20,
        leading=24,
        textColor=color_wine,
        spaceAfter=4
    )

    style_subtitle = ParagraphStyle(
        'DocSubTitle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=10,
        leading=13,
        textColor=color_slate,
        spaceAfter=12
    )

    style_h1 = ParagraphStyle(
        'SecH1',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=12,
        leading=15,
        textColor=color_wine,
        spaceBefore=10,
        spaceAfter=4,
        keepWithNext=True
    )

    style_body = ParagraphStyle(
        'Body',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8.5,
        leading=12,
        textColor=color_slate
    )

    style_body_bold = ParagraphStyle(
        'BodyBold',
        parent=style_body,
        fontName='Helvetica-Bold'
    )

    style_item_title = ParagraphStyle(
        'ItemTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9.5,
        leading=13,
        textColor=color_dark
    )

    style_table_cell = ParagraphStyle(
        'TableCell',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8,
        leading=10.5,
        textColor=color_slate
    )

    style_table_header = ParagraphStyle(
        'TableHeader',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8,
        leading=10.5,
        textColor=colors.white
    )

    story = []

    # BANNER HEADER
    banner_data = [
        [
            Paragraph("<b>PROLAGO C.A.</b><br/><font size='7.5' color='#cbd5e1'>Medicina Veterinaria y Alimentos Concentrados • Carora, Lara</font>", style_table_header),
            Paragraph("<b>INFORME OFICIAL DE ACTUALIZACIONES</b><br/><font size='7.5' color='#fef08a'>Versión 2.5 Comercial &bull; Listo para Entrega</font>", ParagraphStyle('RHeader', parent=style_table_header, alignment=2))
        ]
    ]
    t_banner = Table(banner_data, colWidths=[300, 223])
    t_banner.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), color_wine),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('TOPPADDING', (0,0), (-1,-1), 8),
        ('BOTTOMPADDING', (0,0), (-1,-1), 8),
        ('LEFTPADDING', (0,0), (-1,-1), 10),
        ('RIGHTPADDING', (0,0), (-1,-1), 10),
    ]))
    story.append(t_banner)
    story.append(Spacer(1, 10))

    # ENCABEZADO METADATA
    fecha_hoy = datetime.now().strftime("%d/%m/%Y")
    meta_data = [
        [Paragraph(f"<b>Fecha de Emisión:</b> {fecha_hoy}", style_body), Paragraph("<b>Estado:</b> <font color='#059669'><b>100% OPERATIVO / VALIDADO</b></font>", style_body)],
        [Paragraph("<b>Sistema:</b> Prolago Carora 2026 (Web & Local)", style_body), Paragraph("<b>Inversión de Servicio:</b> <font color='#8B1E24'><b>$300 USD (Pago Único)</b></font>", style_body)],
        [Paragraph("<b>Catálogo Precargado:</b> 982 Artículos listos", style_body), Paragraph("<b>Existencias Iniciales:</b> <font color='#2563eb'><b>0.0 (Inventario Limpio para Conteo)</b></font>", style_body)]
    ]
    t_meta = Table(meta_data, colWidths=[260, 263])
    t_meta.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#f8fafc")),
        ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor("#e2e8f0")),
        ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor("#f1f5f9")),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ('LEFTPADDING', (0,0), (-1,-1), 8),
        ('RIGHTPADDING', (0,0), (-1,-1), 8),
    ]))
    story.append(t_meta)
    story.append(Spacer(1, 12))

    # INTRODUCCIÓN
    story.append(Paragraph("<b>Resumen Ejecutivo de las Nuevas Actualizaciones:</b>", style_h1))
    p_intro = Paragraph(
        "El presente informe técnico y comercial consolida todas las mejoras, optimizaciones y nuevos módulos implementados en el software <b>Prolago Carora 2026</b>. Estas actualizaciones responden directamente a las exigencias operativas del negocio: control estricto del dinero físico, agilidad de cobro en mostrador, monitoreo predictivo del inventario crítico y presentación ejecutiva orientada a la venta del software.",
        style_body
    )
    story.append(p_intro)
    story.append(Spacer(1, 8))

    # MODULOS DETALLADOS
    actualizaciones = [
        (
            "1. Módulo Autónomo de Cajas y Arqueo de Turnos (/cajas y en POS)",
            [
                "<b>Módulo Independiente:</b> Se separó totalmente la gestión de cajas para garantizar una auditoría financiera clara y sin interferencias.",
                "<b>Widget en Vivo en POS:</b> Los cajeros visualizan en todo momento en la barra lateral el estado de la caja (Abierta #Turno o Cerrada), junto con botones rápidos para abrir o cerrar sin abandonar el mostrador.",
                "<b>Apertura con Fondo Base:</b> Registro de fondo de caja inicial tanto en dólares ($) como en bolívares (Bs.). Bloqueo de seguridad que impide facturar si no hay una caja activa.",
                "<b>Arqueo Ciego al Cierre:</b> El cajero declara el dinero contado físicamente por método de pago. El sistema calcula en segundos si existe <b>sobrante o faltante</b>.",
                "<b>Ticket Térmico de Cierre:</b> Impresión de balance para contabilidad en impresoras térmicas (58mm / 80mm) con histórico inmutable de todos los turnos del año."
            ]
        ),
        (
            "2. Centro de Reportes Gerenciales 6 en 1 con Exportación a Excel (/reportes)",
            [
                "<b>6 Reportes Especializados:</b> Ventas, Compras, Inventario, Stock por Acabarse, Cajas y Cuentas por Cobrar (Cobranza).",
                "<b>Filtros Temporales Inteligentes:</b> Selector de fechas por calendario y botones rápidos de 1 clic: <i>Hoy, Esta Semana, Este Mes, Este Año</i>.",
                "<b>Exportación a CSV / Excel:</b> Cada reporte cuenta con su botón verde de exportación directa para abrir y analizar datos en Microsoft Excel.",
                "<b>Top 10 y Rendimiento de Cajeros:</b> Identificación instantánea de los productos más vendidos y el total facturado por cada usuario del sistema."
            ]
        ),
        (
            "3. Alerta de Stock Crítico Individualizada por Artículo",
            [
                "<b>Límite de Alerta Personalizado:</b> Cada artículo dispone de su propio parámetro libre <i>'Stock para Alerta'</i> (ej: avisar en 2 sacos, 10 unidades, 50 piezas).",
                "<b>Reporte 'Stock por Acabarse':</b> Filtra automáticamente los artículos que tocaron o perforaron su umbral mínimo, calculando el déficit y la <b>inversión en $ y Bs requerida para reponer mercancía</b>.",
                "<b>Insignia Visual en Vivo:</b> Contador dinámico en la pestaña de reportes que alerta visualmente con badge rojo cuántos artículos están en riesgo."
            ]
        ),
        (
            "4. Navegación Fluida con Tecla Enter (Sustituto de Tabulador)",
            [
                "<b>Avance Rápido con Enter:</b> En cualquier formulario o modal de cobro, presionar <font color='#8B1E24'><b>Enter</b></font> avanza al siguiente campo seleccionando el texto para agilizar la digitación.",
                "<b>Retroceso con Shift + Enter:</b> Permite regresar al campo anterior con la misma fluidez que Shift + Tab.",
                "<b>Acción en el Último Campo:</b> Al dar Enter en el último campo de un formulario o modal de cobro, se enfoca directamente el botón principal (<i>Guardar, Cobrar, Confirmar</i>) para cerrar la venta sin usar el ratón.",
                "<b>Comportamiento Inteligente:</b> Respeta saltos de línea en áreas de texto (textarea) y la lectura rápida de código de barras en el POS."
            ]
        ),
        (
            "5. Landing Page y Dossier Comercial de Venta con Gráficas (/propuesta)",
            [
                "<b>Página Web Ejecutiva:</b> Diseñada con estética corporativa de alto impacto visual para enviar al cliente final o inversionista.",
                "<b>4 Gráficas Interactivas (Chart.js):</b> Comparativa Operativa (Antes vs Con Prolago), Flujo Multimoneda ($ y Bs), Valoración Patrimonial de Inventario y <b>Calculadora Interactiva de Retorno de Inversión (ROI)</b>.",
                "<b>Oferta Cerrada por $300 USD:</b> Presentación formal del costo único de $300 USD detallando los 6 entregables incluidos sin mensualidades forzadas.",
                "<b>Generación de PDF con 1 Clic:</b> Botón integrado para descargar o imprimir la propuesta en formato ejecutivo A4."
            ]
        ),
        (
            "6. Catálogo Comercial Preparado para Entrega Oficial (Stock en Cero)",
            [
                "<b>Existencias en 0.0:</b> Se reinició el stock de los <b>982 artículos</b> a exactamente cero para que el cliente realice su conteo físico o carga de compras real.",
                "<b>Datos Comerciales Intactos:</b> Se preservaron códigos, nombres, categorías, marcas, proveedores, costos, PVP calculado y stock de alerta individual.",
                "<b>Sincronización Total:</b> Aplicado en la base de datos principal (prolago.db) y en los paquetes locales (.exe para Windows)."
            ]
        ),
        (
            "7. Funcionalidades Previas Consolidadas",
            [
                "<b>Administrador de Usuarios y Permisos:</b> Roles (Admin y Cajeros) con control modular de accesos a cada pantalla del sistema.",
                "<b>Factura Crédito A4 Media Hoja:</b> Comprobante formal con condiciones de plazo, fecha de vencimiento y casilla de firma.",
                "<b>Modificación Protegida de Facturas:</b> Solo el administrador puede modificar o anular comprobantes emitidos mediante clave maestra.",
                "<b>Módulo de Despachos:</b> Carga automática del nombre y dirección del cliente al buscar la factura.",
                "<b>Operación Offline y Copias de Seguridad:</b> Funciona en red local sin internet y permite respaldar la base de datos con un clic."
            ]
        )
    ]

    for titulo, puntos in actualizaciones:
        item_flowables = []
        item_flowables.append(Paragraph(f"<b>{titulo}</b>", style_h1))
        for p in puntos:
            item_flowables.append(Paragraph(f"&bull; {p}", style_body))
        item_flowables.append(Spacer(1, 6))
        story.append(KeepTogether(item_flowables))

    # TABLA RESUMEN DE MÓDULOS Y ESTADO
    story.append(Spacer(1, 6))
    story.append(Paragraph("<b>Matriz de Estado y Disponibilidad de Módulos:</b>", style_h1))
    
    tabla_data = [
        [
            Paragraph("<b>Módulo del Sistema</b>", style_table_header),
            Paragraph("<b>Ruta / Acceso</b>", style_table_header),
            Paragraph("<b>Capacidades Principales</b>", style_table_header),
            Paragraph("<b>Estado</b>", style_table_header)
        ],
        [
            Paragraph("<b>Punto de Venta (POS)</b>", style_table_cell),
            Paragraph("<code>/</code>", style_table_cell),
            Paragraph("Multimoneda ($ y Bs), código de barras, navegación con Enter, ticket 58/80mm", style_table_cell),
            Paragraph("<font color='#059669'><b>100% Operativo</b></font>", style_table_cell)
        ],
        [
            Paragraph("<b>Control de Cajas</b>", style_table_cell),
            Paragraph("<code>/cajas</code>", style_table_cell),
            Paragraph("Apertura, fondo base, arqueo ciego, sobrante/faltante, ticket de cierre", style_table_cell),
            Paragraph("<font color='#059669'><b>100% Operativo</b></font>", style_table_cell)
        ],
        [
            Paragraph("<b>Reportes Gerenciales</b>", style_table_cell),
            Paragraph("<code>/reportes</code>", style_table_cell),
            Paragraph("6 reportes consolidados (Ventas, Compras, Stock Alerta, Cajas, Crédito), Excel", style_table_cell),
            Paragraph("<font color='#059669'><b>100% Operativo</b></font>", style_table_cell)
        ],
        [
            Paragraph("<b>Stock por Acabarse</b>", style_table_cell),
            Paragraph("<code>/reportes#alerta</code>", style_table_cell),
            Paragraph("Alerta individual por artículo, cálculo de déficit e inversión en $ y Bs", style_table_cell),
            Paragraph("<font color='#059669'><b>100% Operativo</b></font>", style_table_cell)
        ],
        [
            Paragraph("<b>Propuesta Comercial</b>", style_table_cell),
            Paragraph("<code>/propuesta</code>", style_table_cell),
            Paragraph("Landing page con gráficas Chart.js, calculadora ROI, dossier y PDF $300 USD", style_table_cell),
            Paragraph("<font color='#059669'><b>100% Operativo</b></font>", style_table_cell)
        ],
        [
            Paragraph("<b>Inventario (982 arts)</b>", style_table_cell),
            Paragraph("<code>/inventario</code>", style_table_cell),
            Paragraph("Stock reiniciado a 0.0, costos, fórmulas PVP y alertas individuales listas", style_table_cell),
            Paragraph("<font color='#059669'><b>100% Operativo</b></font>", style_table_cell)
        ],
        [
            Paragraph("<b>Mantenimiento & BD</b>", style_table_cell),
            Paragraph("<code>/mantenimiento</code>", style_table_cell),
            Paragraph("Respaldos descargables, restauración de datos, IP de red local", style_table_cell),
            Paragraph("<font color='#059669'><b>100% Operativo</b></font>", style_table_cell)
        ]
    ]

    t_resumen = Table(tabla_data, colWidths=[115, 75, 250, 83])
    t_resumen.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), color_wine),
        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#cbd5e1")),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor("#f8fafc")]),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ('LEFTPADDING', (0,0), (-1,-1), 5),
        ('RIGHTPADDING', (0,0), (-1,-1), 5),
    ]))
    story.append(KeepTogether([t_resumen]))
    
    story.append(Spacer(1, 14))

    # CERTIFICACIÓN FINAL
    cert_data = [
        [
            Paragraph("<b>CERTIFICACIÓN DE ENTREGA TÉCNICA:</b><br/>El sistema <b>Prolago Carora 2026</b> se encuentra completamente funcional, probado y optimizado para su despliegue comercial inmediato en entornos web (Nube) y local (Windows sin internet). La inversión establecida para la implantación es de <b>$300 USD</b> pago único.", style_body)
        ]
    ]
    t_cert = Table(cert_data, colWidths=[523])
    t_cert.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#fef2f2")),
        ('BOX', (0,0), (-1,-1), 1, colors.HexColor("#f87171")),
        ('TOPPADDING', (0,0), (-1,-1), 8),
        ('BOTTOMPADDING', (0,0), (-1,-1), 8),
        ('LEFTPADDING', (0,0), (-1,-1), 10),
        ('RIGHTPADDING', (0,0), (-1,-1), 10),
    ]))
    story.append(KeepTogether([t_cert]))

    doc.build(story, canvasmaker=NumberedCanvas)
    print(f"PDF generado con éxito en: {destino_path}")

if __name__ == "__main__":
    out_dir = r"C:\Users\e\.gemini\antigravity\scratch\prolago-web"
    pdf_path = os.path.join(out_dir, "Informe_Actualizaciones_Prolago_2026.pdf")
    generar_pdf(pdf_path)
