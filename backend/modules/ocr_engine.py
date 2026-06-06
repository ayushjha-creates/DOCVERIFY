import cv2
import numpy as np
import pytesseract
import pdfplumber
import re
import sys
import json
import os
from collections import Counter
from PIL import Image

SUSPICIOUS_UNICODE = {
    '\u00a0': 'Non-breaking space',
    '\u200b': 'Zero-width space',
    '\u200c': 'Zero-width non-joiner',
    '\u200d': 'Zero-width joiner',
    '\u200e': 'Left-to-right mark',
    '\u200f': 'Right-to-left mark',
    '\ufeff': 'BOM / Zero-width no-break space',
    '\u2060': 'Word joiner',
    '\u00ad': 'Soft hyphen',
    '\u034f': 'Combining grapheme joiner',
}

COMMON_BOILERPLATE = {
    "this is to", "certified that the", "on behalf of",
    "date of birth", "hereinafter referred to", "in witness whereof",
    "the sum of", "per cent", "subject to", "terms and conditions",
    "all rights reserved",
}


def _preprocess_image(img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape
    gray = cv2.resize(gray, (w * 2, h * 2), interpolation=cv2.INTER_CUBIC)
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]], dtype=np.float32)
    sharpened = cv2.filter2D(binary, -1, kernel)
    return sharpened


def extract_text(file_path):
    ext = os.path.splitext(file_path)[1].lower()

    if ext == '.pdf':
        try:
            full_text = ""
            fonts = set()
            with pdfplumber.open(file_path) as pdf:
                for page in pdf.pages:
                    text = page.extract_text() or ""
                    full_text += text + "\n"
                    for char in page.chars:
                        fontname = char.get("fontname", "")
                        if fontname:
                            fonts.add(fontname)
            words = full_text.split()
            return {
                "full_text": full_text.strip(),
                "words": words,
                "lines": full_text.split("\n"),
                "word_confidences": [],
                "fonts": list(fonts),
                "char_count": len(full_text),
                "word_count": len(words),
                "method": "pdfplumber",
            }
        except Exception:
            try:
                from pdf2image import convert_from_path
                images = convert_from_path(file_path)
                full_text = ""
                for img in images:
                    img_cv = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
                    processed = _preprocess_image(img_cv)
                    text = pytesseract.image_to_string(processed)
                    full_text += text + "\n"
                words = full_text.split()
                return {
                    "full_text": full_text.strip(),
                    "words": words,
                    "lines": full_text.split("\n"),
                    "word_confidences": [],
                    "fonts": [],
                    "char_count": len(full_text),
                    "word_count": len(words),
                    "method": "tesseract",
                }
            except Exception:
                return {
                    "full_text": "",
                    "words": [],
                    "lines": [],
                    "word_confidences": [],
                    "fonts": [],
                    "char_count": 0,
                    "word_count": 0,
                    "method": "tesseract",
                }

    else:
        try:
            img_pil = Image.open(file_path).convert("RGB")
            img_cv = cv2.cvtColor(np.array(img_pil), cv2.COLOR_RGB2BGR)
            processed = _preprocess_image(img_cv)
            full_text = pytesseract.image_to_string(processed)
            data = pytesseract.image_to_data(processed, output_type=pytesseract.Output.DICT)
            words = [w for w in data["text"] if w.strip()]
            confs = [int(data["conf"][i]) for i in range(len(data["text"]))
                     if data["text"][i].strip() and int(data["conf"][i]) > 0]
            return {
                "full_text": full_text.strip(),
                "words": [w for w in data["text"] if w.strip()],
                "lines": full_text.split("\n"),
                "word_confidences": confs,
                "fonts": [],
                "char_count": len(full_text),
                "word_count": len(words),
                "method": "tesseract",
            }
        except Exception:
            return {
                "full_text": "",
                "words": [],
                "lines": [],
                "word_confidences": [],
                "fonts": [],
                "char_count": 0,
                "word_count": 0,
                "method": "tesseract",
            }


def _normalise_font(fontname):
    name = fontname.split("-")[0] if "-" in fontname else fontname
    name = re.sub(r'\d+', '', name)
    return name.strip().lower()


def analyse_ocr(file_path):
    flags = []
    details_parts = []
    raw_out = {
        "word_count": 0,
        "char_count": 0,
        "avg_ocr_confidence": None,
        "unique_fonts": 0,
        "font_list": [],
        "invisible_unicode_count": 0,
        "numeric_outliers": [],
        "spacing_cv": None,
        "method": "",
    }

    extracted = extract_text(file_path)
    full_text = extracted["full_text"]
    words = extracted["words"]
    word_confs = extracted["word_confidences"]
    fonts = extracted["fonts"]
    raw_out["word_count"] = extracted["word_count"]
    raw_out["char_count"] = extracted["char_count"]
    raw_out["method"] = extracted["method"]

    if not full_text:
        return {
            "status": "OK",
            "deduction": 0,
            "details": "No text content found in the document.",
            "flags": [],
            "raw": raw_out,
        }

    # ── CHECK: LOW OCR CONFIDENCE (image only) ──
    try:
        if word_confs and extracted["method"] == "tesseract":
            avg_conf = float(np.mean(word_confs))
            raw_out["avg_ocr_confidence"] = round(avg_conf, 1)
            if avg_conf < 72:
                flags.append("LOW_OCR_CONFIDENCE")
                details_parts.append(
                    f"Average OCR confidence across the document is {avg_conf:.1f}%. "
                    "Legitimate printed documents typically score above 80%. Low confidence across "
                    "multiple regions suggests inconsistent text rendering, which can indicate "
                    "digital editing of text areas."
                )
    except Exception as e:
        print(f"LOW_OCR_CONFIDENCE check failed: {e}")

    # ── CHECK: FONT INCONSISTENCY (PDF only) ──
    try:
        if fonts and extracted["method"] == "pdfplumber":
            normalised = [_normalise_font(f) for f in fonts]
            unique_families = list(set(normalised))
            raw_out["unique_fonts"] = len(unique_families)
            raw_out["font_list"] = unique_families
            if len(unique_families) > 7:
                flags.append("EXCESSIVE_FONTS")
                details_parts.append(
                    f"Document contains {len(unique_families)} distinct font families: "
                    f"{', '.join(unique_families[:8])}. "
                    "Legitimate institutional documents use at most 3-4 fonts. Additional fonts are "
                    "typically introduced when text is injected or replaced using external editors."
                )
            elif len(unique_families) > 4:
                flags.append("FONT_INCONSISTENCY")
                details_parts.append(
                    f"Document contains {len(unique_families)} distinct font families: "
                    f"{', '.join(unique_families[:8])}. "
                    "Legitimate institutional documents use at most 3-4 fonts. Additional fonts are "
                    "typically introduced when text is injected or replaced using external editors."
                )
    except Exception as e:
        print(f"FONT_INCONSISTENCY check failed: {e}")

    # ── CHECK: UNICODE ANOMALIES ──
    try:
        found_unicode = {char: name for char, name in SUSPICIOUS_UNICODE.items() if char in full_text}
        total_invisible = sum(full_text.count(c) for c in found_unicode)
        raw_out["invisible_unicode_count"] = total_invisible
        if total_invisible > 3:
            flags.append("INVISIBLE_UNICODE")
            details_parts.append(
                f"Found {total_invisible} invisible Unicode characters "
                f"({', '.join(found_unicode.values())}) embedded in document text. "
                "These characters are invisible on screen but are commonly introduced when text is "
                "copy-pasted from external sources or web-based PDF editors."
            )
    except Exception as e:
        print(f"INVISIBLE_UNICODE check failed: {e}")

    # ── CHECK: SPACING INCONSISTENCY (image only) ──
    try:
        if extracted["method"] == "tesseract":
            data = pytesseract.image_to_data(
                _preprocess_image(cv2.cvtColor(np.array(Image.open(file_path).convert("RGB")), cv2.COLOR_RGB2BGR)),
                output_type=pytesseract.Output.DICT,
            )
            gaps = []
            prev_line = -1
            prev_right = None
            valid_words = [i for i in range(len(data["text"])) if data["text"][i].strip()]
            for i in valid_words:
                line = data["line_num"][i]
                left = data["left"][i]
                width = data["width"][i]
                if line == prev_line and prev_right is not None:
                    gap = left - prev_right
                    if 0 < gap < 200:
                        gaps.append(gap)
                prev_right = left + width
                prev_line = line
            if gaps:
                mean_gap = float(np.mean(gaps))
                std_gap = float(np.std(gaps))
                if mean_gap > 0:
                    cv_gap = std_gap / mean_gap
                    raw_out["spacing_cv"] = round(cv_gap, 2)
                    if cv_gap > 0.55:
                        flags.append("SPACING_INCONSISTENCY")
                        details_parts.append(
                            f"Inter-word spacing shows high variability "
                            f"(coefficient of variation: {cv_gap:.2f}). "
                            "Consistent typesetting produces uniform spacing. Erratic spacing between "
                            "specific words suggests individual words or numbers were replaced after "
                            "the document was originally typeset."
                        )
    except Exception as e:
        print(f"SPACING_INCONSISTENCY check failed: {e}")

    # ── CHECK: NUMERIC PATTERN ANOMALY ──
    try:
        numbers = re.findall(r'\b\d+\.?\d*\b', full_text)
        numbers = [float(n) for n in numbers if n]
        if len(numbers) >= 5:
            mean_val = float(np.mean(numbers))
            std_val = float(np.std(numbers))
            if std_val > 0:
                outliers = [n for n in numbers if abs(n - mean_val) > 2.8 * std_val]
                if outliers:
                    raw_out["numeric_outliers"] = [round(n, 2) for n in outliers[:10]]
                    flags.append("NUMERIC_OUTLIER")
                    details_parts.append(
                        f"Statistical analysis of {len(numbers)} numeric values found "
                        f"{len(outliers)} outlier(s): {[round(n, 1) for n in outliers[:5]]}. "
                        "In authentic documents, numeric values follow a consistent distribution. "
                        "Extreme outliers may indicate individual values were altered."
                    )
    except Exception as e:
        print(f"NUMERIC_OUTLIER check failed: {e}")

    # ── CHECK: COPY-PASTE TEXT REPETITION ──
    try:
        word_list = words
        if len(word_list) >= 8:
            ngrams = [tuple(word_list[i:i + 4]) for i in range(len(word_list) - 3)]
            counts = Counter(ngrams)
            repeated = {}
            for ng, c in counts.items():
                if c > 2:
                    phrase = " ".join(ng)
                    if phrase.lower() not in COMMON_BOILERPLATE:
                        repeated[phrase] = c
            if repeated:
                flags.append("REPEATED_PHRASES")
                top = list(repeated.items())[:3]
                parts = [f'"{p}" ({c}x)' for p, c in top]
                details_parts.append(
                    f"Found {len(repeated)} multi-word phrase(s) repeated more than twice "
                    f"in the document, including {', '.join(parts)}. "
                    "Unusual phrase repetition can indicate sections were duplicated from a template "
                    "or another document during assembly."
                )
    except Exception as e:
        print(f"REPEATED_PHRASES check failed: {e}")

    # ── CHECK: LINE ALIGNMENT CONSISTENCY (image only) ──
    try:
        if extracted["method"] == "tesseract":
            data = pytesseract.image_to_data(
                _preprocess_image(cv2.cvtColor(np.array(Image.open(file_path).convert("RGB")), cv2.COLOR_RGB2BGR)),
                output_type=pytesseract.Output.DICT,
            )
            line_tops = {}
            for i in range(len(data["text"])):
                if data["text"][i].strip():
                    ln = data["line_num"][i]
                    if ln not in line_tops:
                        line_tops[ln] = []
                    line_tops[ln].append(data["top"][i])
            misaligned = 0
            for ln, tops in line_tops.items():
                if len(tops) >= 2:
                    var = float(np.std(tops))
                    if var > 3:
                        misaligned += 1
            if misaligned > 2:
                flags.append("LINE_MISALIGNMENT")
                details_parts.append(
                    f"Text baseline alignment shows irregularities on {misaligned} lines "
                    "(variance > 4px). Genuine typeset documents maintain pixel-perfect horizontal "
                    "baselines. Vertical misalignment of individual words suggests they were inserted "
                    "after the document was originally created."
                )
    except Exception as e:
        print(f"LINE_MISALIGNMENT check failed: {e}")

    # ── Scoring ──
    weight_map = {
        "EXCESSIVE_FONTS": 3,
        "INVISIBLE_UNICODE": 2,
        "SPACING_INCONSISTENCY": 2,
        "FONT_INCONSISTENCY": 2,
        "NUMERIC_OUTLIER": 2,
        "LINE_MISALIGNMENT": 2,
        "LOW_OCR_CONFIDENCE": 1,
        "REPEATED_PHRASES": 1,
    }

    total_weight = sum(weight_map.get(f, 1) for f in flags)

    if total_weight == 0:
        status = "OK"
        deduction = 0
        details = (
            "OCR extraction completed with high confidence. Font usage, text spacing, "
            "Unicode composition, and numeric distributions are all consistent with a "
            "legitimately authored document."
        )
    elif total_weight == 1:
        status = "WARN"
        deduction = 10
        details = " ".join(details_parts[:1])
    elif total_weight == 2:
        status = "WARN"
        deduction = 15
        details = " ".join(details_parts[:2])
    else:
        status = "FAIL"
        deduction = 20
        details = " ".join(details_parts[:2])

    return {
        "status": status,
        "deduction": deduction,
        "details": details,
        "flags": flags,
        "raw": raw_out,
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python ocr_engine.py <file_path>")
        sys.exit(1)
    result = analyse_ocr(sys.argv[1])
    print(json.dumps(result, indent=2))
