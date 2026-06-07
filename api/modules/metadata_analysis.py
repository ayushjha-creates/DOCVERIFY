import fitz
import datetime
import os
from PIL import Image
from PIL.ExifTags import TAGS


def _finding(ftype, title, detail, points=0, severity="minor", field_location=""):
    return {
        "type": ftype,
        "title": title,
        "detail": detail,
        "points": points,
        "severity": severity,
        "field_location": field_location,
    }


SUSPICIOUS_SOFTWARE = [
    "Adobe Photoshop", "GIMP", "Corel PaintShop", "Affinity Photo",
    "Sketch", "Canva", "Microsoft Paint", "Paint.NET", "Krita",
    "Pixelmator", "Photopea", "PhotoScape", "PicMonkey", "Fotor",
]

SUSPICIOUS_PRODUCERS = [
    "SmallPDF", "ILovePDF", "PDF Candy", "PDF24", "PDFescape",
    "Sejda", "PDFSimpli", "Soda PDF", "Nitro PDF", "Foxit PhantomPDF",
    "PDF Converter", "PDFelement", "pdfcrowd", "pdfmake",
    "DocHub", "PDFfiller", "JotForm", "PDFBear", "LightPDF",
    "PDF2Go", "online2pdf", "pandoc",
]

AI_PRODUCERS = [
    "ChatGPT", "Claude", "Gemini", "Copilot", "Llama", "Mistral",
    "Perplexity", "Jasper", "Copy.ai", "Writer.com", "Wordtune",
    "Sudowrite", "Rytr", "Writesonic", "TextCortex", "Notion AI",
    "Grammarly", "QuillBot", "StealthWriter", "Undetectable AI",
]

AI_GENERATED_SOFTWARE = [
    "DALL-E", "Midjourney", "Stable Diffusion", "Firefly", "Runway",
    "Leonardo AI", "DreamStudio", "Adobe Firefly", "DeepAI",
    "Craiyon", "Ideogram", "Clipdrop", "Kandinsky",
]


def _parse_pdf_date(date_str):
    if not date_str or "D:" not in date_str:
        return None
    clean = date_str.replace("D:", "")
    if len(clean) < 14:
        return None
    try:
        return datetime.datetime.strptime(clean[:14], "%Y%m%d%H%M%S")
    except ValueError:
        return None


def analyze_metadata(file_path):
    findings = []
    metadata = {}
    suspicious = False
    score = 0
    now = datetime.datetime.now()

    ext = os.path.splitext(file_path)[1].lower()

    if ext == '.pdf':
        doc = fitz.open(file_path)
        meta = doc.metadata
        metadata = {
            "title": meta.get("title", ""),
            "author": meta.get("author", ""),
            "subject": meta.get("subject", ""),
            "keywords": meta.get("keywords", ""),
            "creator": meta.get("creator", ""),
            "producer": meta.get("producer", "").strip(),
            "creationDate": meta.get("creationDate", ""),
            "modDate": meta.get("modDate", ""),
            "format": meta.get("format", ""),
        }
        doc.close()

        pdf_created = _parse_pdf_date(metadata.get("creationDate", ""))
        pdf_modified = _parse_pdf_date(metadata.get("modDate", ""))
        producer = metadata.get("producer", "")

        # ── 1. SUSPICIOUS_PRODUCER ──
        for sus in SUSPICIOUS_PRODUCERS + SUSPICIOUS_SOFTWARE:
            if sus.lower() in producer.lower():
                findings.append(_finding(
                    "warning", "Suspicious Producer Detected",
                    f"PDF produced by '{producer}' — online PDF tools are commonly used to reconstruct tampered documents",
                    points=15, severity="high", field_location="producer"
                ))
                suspicious = True
                score -= 15
                break

        # ── 2. FUTURE_TIMESTAMP ──
        for label, dt in [("creation", pdf_created), ("modification", pdf_modified)]:
            if dt and dt > now + datetime.timedelta(hours=1):
                findings.append(_finding(
                    "warning", "Future Timestamp Detected",
                    f"PDF {label} date ({dt.date()}) is in the future — document metadata has been altered",
                    points=20, severity="high", field_location=f"pdf_{label}_date"
                ))
                suspicious = True
                score -= 20
                break

        # ── 3. PDF_CREATED_TODAY ──
        if pdf_created and producer:
            if pdf_created.date() == now.date():
                for sus in SUSPICIOUS_PRODUCERS:
                    if sus.lower() in producer.lower():
                        findings.append(_finding(
                            "warning", "PDF Created Today with Online Tool",
                            f"PDF internal creation date is today ({pdf_created.date()}) and was produced using '{producer}'. "
                            "A legitimate historical document would carry its original creation date. "
                            "Same-day creation with an online PDF tool strongly suggests the document was "
                            "reconstructed or exported immediately before submission.",
                            points=10, severity="high", field_location="creationDate"
                        ))
                        suspicious = True
                        score -= 10
                        break

        # ── 4. PDF_DATE_MISMATCH ──
        if pdf_created and pdf_modified:
            gap_days = abs((pdf_modified - pdf_created).days)
            if gap_days > 3:
                findings.append(_finding(
                    "warning", "Date Mismatch Between PDF Fields",
                    f"PDF creation ({pdf_created.date()}) and modification ({pdf_modified.date()}) dates "
                    f"differ by {gap_days} days — these are set by the authoring software and should match",
                    points=10, severity="medium", field_location="creationDate/modDate"
                ))
                suspicious = True
                score -= 10

        # ── 5. MODIFIED_AFTER_CREATION ──
        if pdf_created and pdf_modified:
            if pdf_modified < pdf_created:
                findings.append(_finding(
                    "warning", "Modified Before Creation",
                    f"PDF modification date ({pdf_modified.date()}) is before creation date "
                    f"({pdf_created.date()}) — logically impossible, metadata has been tampered with",
                    points=15, severity="high", field_location="creationDate/modDate"
                ))
                suspicious = True
                score -= 15

        # ── 6. ODD_HOUR_MODIFICATION ──
        if pdf_modified:
            hour = pdf_modified.hour
            if hour < 5 or hour > 22:
                findings.append(_finding(
                    "warning", "Unusual Modification Hour",
                    f"PDF was last modified at {pdf_modified.strftime('%H:%M')} — unlikely for legitimate document creation",
                    points=5, severity="medium", field_location="modDate"
                ))
                suspicious = True
                score -= 5

        # ── 7. WEEKEND_MODIFICATION ──
        if pdf_modified:
            weekday = pdf_modified.weekday()
            if weekday >= 5:
                findings.append(_finding(
                    "warning", "Weekend Modification",
                    f"PDF was last modified on a {pdf_modified.strftime('%A')} — unusual for official documents",
                    points=5, severity="low", field_location="modDate"
                ))
                suspicious = True
                score -= 5

        # ── 8. AI-Generated Document Detection ──
        creator = metadata.get("creator", "")
        producer_lower = producer.lower() if producer else ""
        creator_lower = creator.lower() if creator else ""

        for ai_name in AI_PRODUCERS:
            if ai_name.lower() in producer_lower or ai_name.lower() in creator_lower:
                findings.append(_finding(
                    "warning", "AI: AI Tool Detected in Metadata",
                    f"Document produced by '{producer}' — indicates AI-generated or AI-assisted content",
                    points=15, severity="high", field_location="producer"
                ))
                suspicious = True
                score -= 15
                break

        for ai_sw in AI_GENERATED_SOFTWARE:
            if ai_sw.lower() in producer_lower or ai_sw.lower() in creator_lower:
                findings.append(_finding(
                    "warning", "AI: AI Image Generator Detected",
                    f"Document produced by '{producer}' — AI-generated imagery detected",
                    points=20, severity="high", field_location="producer"
                ))
                suspicious = True
                score -= 20
                break

        # Missing producer with creator set — AI tools often strip producer metadata
        if creator and not producer:
            findings.append(_finding(
                "warning", "AI: Missing Producer Metadata",
                f"Document has creator '{creator}' but no producer — AI-generated documents "
                "often omit or strip producer metadata",
                points=5, severity="medium", field_location="producer"
            ))
            suspicious = True
            score -= 5

        # ── Summary info ──
        summary_parts = []
        if metadata.get("creator"):
            summary_parts.append(f"Creator: {metadata['creator']}")
        if producer:
            summary_parts.append(f"Producer: {producer}")
        if not summary_parts:
            summary_parts.append("No creator/producer metadata")
        findings.append(_finding(
            "info", "PDF Metadata Extracted",
            " | ".join(summary_parts),
            points=0, severity="minor"
        ))

    elif ext in ['.png', '.jpg', '.jpeg', '.tiff', '.bmp']:
        try:
            img = Image.open(file_path)
            exif_data = img._getexif()
            if exif_data:
                for tag_id, value in exif_data.items():
                    tag_name = TAGS.get(tag_id, tag_id)
                    metadata[tag_name] = str(value)

                # ── Suspicious software (EXIF Software tag) ──
                sw = metadata.get("Software", "")
                for sus in SUSPICIOUS_SOFTWARE:
                    if sus.lower() in sw.lower():
                        findings.append(_finding(
                            "warning", "Suspicious Software Detected",
                            f"Image edited with: {sus}",
                            points=15, severity="high", field_location="Software"
                        ))
                        suspicious = True
                        score -= 15
                        break

                # ── Future timestamp (EXIF DateTime) ──
                dt_str = metadata.get("DateTime", "")
                if dt_str:
                    try:
                        exif_dt = datetime.datetime.strptime(dt_str, "%Y:%m:%d %H:%M:%S")
                        if exif_dt > now + datetime.timedelta(hours=1):
                            findings.append(_finding(
                                "warning", "Future Timestamp Detected",
                                f"Image date ({exif_dt.date()}) is in the future — metadata has been altered",
                                points=20, severity="high", field_location="DateTime"
                            ))
                            suspicious = True
                            score -= 20
                    except ValueError:
                        pass

                if "Software" in metadata:
                    findings.append(_finding(
                        "info", "Software Used",
                        f"Image created with: {metadata['Software']}",
                        points=0, severity="minor"
                    ))

                if "DateTime" in metadata:
                    findings.append(_finding(
                        "info", "Image Date",
                        f"Date: {metadata['DateTime']}",
                        points=0, severity="minor"
                    ))
            else:
                if ext in ['.jpg', '.jpeg', '.tiff']:
                    findings.append(_finding(
                        "info", "No EXIF Data",
                        "Image has no EXIF metadata — this is normal for many document types",
                        points=0, severity="minor"
                    ))
        except Exception as e:
            findings.append(_finding(
                "warning", "Metadata Read Error",
                f"Could not read metadata: {str(e)}",
                points=0, severity="minor"
            ))

    status = "suspicious" if suspicious else "clean"
    total_score = min(score, 0)

    return {
        "status": status,
        "score": total_score,
        "findings": findings,
        "metadata": metadata,
    }
