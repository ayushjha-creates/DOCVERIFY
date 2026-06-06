import os
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch, mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    Image as RLImage, ListFlowable, ListItem, Flowable
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.graphics.shapes import Drawing, Circle, String
from reportlab.graphics.charts.piecharts import Pie
from datetime import datetime

class Gauge(Flowable):
    def __init__(self, score, width=200, height=40):
        Flowable.__init__(self)
        self.score = score
        self.width = width
        self.height = height

    def draw(self):
        self.canv.setStrokeColor(colors.HexColor("#1e293b"))
        self.canv.setLineWidth(2)
        self.canv.setFillColor(colors.HexColor("#1e293b"))
        self.canv.roundRect(0, 0, self.width, self.height, 8, fill=1, stroke=1)
        fill_width = (self.score / 100.0) * (self.width - 4)
        if self.score >= 80:
            bar_color = colors.HexColor("#22c55e")
        elif self.score >= 40:
            bar_color = colors.HexColor("#eab308")
        else:
            bar_color = colors.HexColor("#ef4444")
        self.canv.setFillColor(bar_color)
        self.canv.roundRect(2, 2, fill_width, self.height - 4, 6, fill=1, stroke=0)
        self.canv.setFillColor(colors.white)
        self.canv.setFont("Helvetica-Bold", 14)
        text = f"{self.score}%"
        text_width = self.canv.stringWidth(text, "Helvetica-Bold", 14)
        self.canv.drawString((self.width - text_width) / 2, 11, text)

def generate_pdf_report(results, output_path):
    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        rightMargin=50,
        leftMargin=50,
        topMargin=50,
        bottomMargin=50,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "CustomTitle", parent=styles["Title"],
        fontSize=24, textColor=colors.HexColor("#0f172a"),
        spaceAfter=6
    )
    subtitle_style = ParagraphStyle(
        "CustomSubtitle", parent=styles["Normal"],
        fontSize=12, textColor=colors.HexColor("#64748b"),
        alignment=TA_CENTER, spaceAfter=20
    )
    heading_style = ParagraphStyle(
        "CustomHeading", parent=styles["Heading2"],
        fontSize=14, textColor=colors.HexColor("#1e293b"),
        spaceBefore=16, spaceAfter=8
    )
    body_style = ParagraphStyle(
        "CustomBody", parent=styles["Normal"],
        fontSize=10, textColor=colors.HexColor("#334155"),
        spaceAfter=4, leading=14
    )

    elements = []

    elements.append(Paragraph("DOCVERIFY AI", title_style))
    elements.append(Paragraph("Document Authenticity Verification Report", subtitle_style))

    now = datetime.now().strftime("%B %d, %Y at %H:%M")
    elements.append(Paragraph(f"Generated: {now}", ParagraphStyle(
        "DateLine", parent=body_style, alignment=TA_CENTER,
        textColor=colors.HexColor("#94a3b8"), fontSize=9
    )))
    elements.append(Spacer(1, 20))

    scoring = results.get("scoring", {})
    score = scoring.get("score", 0)
    status = scoring.get("status", "unknown").upper()

    elements.append(Paragraph("Authenticity Score", heading_style))
    elements.append(Gauge(score, width=400, height=40))
    elements.append(Spacer(1, 6))

    status_color = colors.HexColor("#22c55e") if score >= 80 else (
        colors.HexColor("#eab308") if score >= 40 else colors.HexColor("#ef4444")
    )
    elements.append(Paragraph(
        f'Status: <font color="{status_color}"><b>{status}</b></font>',
        ParagraphStyle("StatusLine", parent=body_style, fontSize=12)
    ))
    elements.append(Spacer(1, 16))

    deduction_data = [["Detection Area", "Deduction"]]
    deductions = scoring.get("deductions", {})
    for key, label in [("metadata", "Metadata Issues"), ("ocr", "Text / OCR Issues"),
                       ("qr", "QR Code Issues"), ("tampering", "Tampering Evidence"),
                       ("signature", "Signature Issues")]:
        val = deductions.get(key, 0)
        deduction_data.append([label, f"-{val} pts"])
    deduction_data.append(["Total", f"-{scoring.get('total_deduction', 0)} pts"])

    ded_table = Table(deduction_data, colWidths=[280, 100])
    ded_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e293b")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 10),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 1), (-1, -1), 9),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#f1f5f9")),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    elements.append(ded_table)
    elements.append(Spacer(1, 20))

    reasons = scoring.get("reasons", [])
    if reasons:
        elements.append(Paragraph("Reasons for Score", heading_style))
        for reason in reasons:
            elements.append(Paragraph(f"• {reason}", body_style))

    elements.append(Spacer(1, 15))
    elements.append(Paragraph("Detailed Analysis", heading_style))

    module_labels = {
        "metadata": "Metadata Analysis",
        "ocr": "OCR & Text Analysis",
        "qr": "QR Code Verification",
        "tampering": "Image Tampering Detection",
        "signature": "Signature / Stamp Verification",
    }

    for module_key, module_name in module_labels.items():
        module_data = results.get(module_key, {})
        if module_data:
            elements.append(Paragraph(module_name, ParagraphStyle(
                "ModHeading", parent=heading_style,
                fontSize=12, spaceBefore=12, spaceAfter=4
            )))
            findings = module_data.get("findings", [])
            for finding in findings:
                icon = "✓" if finding.get("type") == "info" else "⚠" if finding.get("type") == "warning" else "✗"
                elements.append(Paragraph(
                    f'{icon} <b>{finding["title"]}</b><br/>'
                    f'<font size="8" color="#64748b">{finding.get("detail", "")}</font>',
                    body_style
                ))

    blockchain = results.get("blockchain", {})
    if blockchain:
        elements.append(Spacer(1, 20))
        elements.append(Paragraph("Blockchain Verification", heading_style))
        elements.append(Paragraph(
            f'Document Hash: <font face="Courier" size="8">{blockchain.get("document_hash", "")[:32]}...</font>',
            body_style
        ))
        elements.append(Paragraph(
            f'Blockchain Hash: <font face="Courier" size="8">{blockchain.get("blockchain_hash", "")[:32]}...</font>',
            body_style
        ))
        elements.append(Paragraph(
            f'Verify at: {blockchain.get("verification_url", "")}',
            body_style
        ))

    elements.append(Spacer(1, 30))
    footer_style = ParagraphStyle(
        "Footer", parent=body_style,
        fontSize=8, textColor=colors.HexColor("#94a3b8"),
        alignment=TA_CENTER
    )
    elements.append(Paragraph("DOCVERIFY AI — Powered by Advanced Forensic Analysis", footer_style))
    elements.append(Paragraph("This report is generated automatically. Results are indicative and should be verified.", footer_style))

    doc.build(elements)
    return output_path
