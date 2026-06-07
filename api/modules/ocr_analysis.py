import os
import re
from collections import defaultdict
from PIL import Image
import numpy as np

try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    cv2 = None
    CV2_AVAILABLE = False

try:
    import pytesseract
    TESSERACT_AVAILABLE = True
except ImportError:
    pytesseract = None
    TESSERACT_AVAILABLE = False

_MAX_OCR_PX = 1200  # resize longest side to this before OCR

# ── Configure bundled tesseract binary ──
_TESS_CFG = None
if TESSERACT_AVAILABLE:
    _ocr_dir = os.path.dirname(os.path.abspath(__file__))
    _api_dir = os.path.dirname(_ocr_dir)
    _tess_bin = os.path.join(_api_dir, "bin", "tesseract")
    if os.path.exists(_tess_bin):
        _tessdata = os.path.join(_api_dir, "bin", "tessdata")
        _lib_dir = os.path.join(_api_dir, "bin", "lib")
        _TESS_CFG = {
            "cmd": _tess_bin,
            "tessdata": _tessdata if os.path.isdir(_tessdata) else None,
            "libdir": _lib_dir if os.path.isdir(_lib_dir) else None,
        }
        pytesseract.pytesseract.tesseract_cmd = _tess_bin
        if _TESS_CFG["tessdata"]:
            os.environ.setdefault("TESSDATA_PREFIX", _TESS_CFG["tessdata"])

SUSPICIOUS_KEYWORDS = [
    "edited", "modified", "altered", "tampered", "doctored",
    "copy", "paste", "replaced", "forged", "fake", "hacked",
]

def _resize_for_ocr(img):
    h, w = img.shape[:2]
    longest = max(h, w)
    if longest > _MAX_OCR_PX:
        scale = _MAX_OCR_PX / longest
        new_w, new_h = int(w * scale), int(h * scale)
        return cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)
    return img


def _load_image(image_path):
    img = cv2.imread(image_path)
    if img is None:
        img_pil = Image.open(image_path).convert("RGB")
        img = np.array(img_pil)
        img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
    return img

def _finding(ftype, title, detail, points, severity, field_location=""):
    return {
        "type": ftype,
        "title": title,
        "detail": detail,
        "points": points,
        "severity": severity,
        "field_location": field_location,
    }


def analyze_ocr(image_path):
    findings = []
    score = 0
    suspicious = False

    if not CV2_AVAILABLE or not TESSERACT_AVAILABLE:
        missing = [m for m, f in [("OpenCV", CV2_AVAILABLE), ("Tesseract", TESSERACT_AVAILABLE)] if not f]
        return {
            "status": "error",
            "score": 0,
            "findings": [{"type": "error", "title": "OCR Unavailable", "detail": f"Missing: {', '.join(missing)}", "points": 0, "severity": "high"}],
            "text": "",
        }

    try:
        img = _load_image(image_path)
        img = _resize_for_ocr(img)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        _, thresh = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY)

        # Set LD_LIBRARY_PATH for tesseract subprocess only
        _old_ld = os.environ.get("LD_LIBRARY_PATH", "")
        if _TESS_CFG and _TESS_CFG["libdir"]:
            os.environ["LD_LIBRARY_PATH"] = f"{_TESS_CFG['libdir']}:{_old_ld}"
        try:
            ocr_data = pytesseract.image_to_data(
                thresh, output_type=pytesseract.Output.DICT
            )
            text = " ".join([w for w in ocr_data["text"] if w.strip()])
        finally:
            if _TESS_CFG and _TESS_CFG["libdir"]:
                if _old_ld:
                    os.environ["LD_LIBRARY_PATH"] = _old_ld
                else:
                    os.environ.pop("LD_LIBRARY_PATH", None)
        words = [w for w in ocr_data["text"] if w.strip()]

        if not words:
            findings.append(_finding(
                "warning", "No Text Detected",
                "No text could be extracted — document may be scanned image or blank",
                points=15, severity="high"
            ))
            suspicious = True
            score -= 15
            status = "suspicious" if suspicious else "clean"
            total_score = max(score, -40)
            return {
                "status": status,
                "score": total_score,
                "findings": findings,
                "text": "",
            }

        h, w = gray.shape

        # ── 1. Confidence check ──
        confs = [int(ocr_data["conf"][i]) for i in range(len(ocr_data["text"]))
                 if ocr_data["text"][i].strip() and int(ocr_data["conf"][i]) > 0]
        if confs:
            avg_conf = np.mean(confs)
            low_conf_count = sum(1 for c in confs if c < 30)
            if low_conf_count > len(confs) * 0.3 and len(confs) > 5:
                findings.append(_finding(
                    "warning", "Low OCR Confidence",
                    f"{low_conf_count}/{len(confs)} characters have very low OCR confidence (<30%) — document may be low quality or tampered",
                    points=5, severity="medium"
                ))
                suspicious = True
                score -= 5
        else:
            avg_conf = 0

        # ── 2. Group words into lines by y-coordinate ──
        line_groups = defaultdict(list)
        for i in range(len(ocr_data["text"])):
            txt = ocr_data["text"][i].strip()
            if not txt:
                continue
            y = ocr_data["top"][i]
            h_i = ocr_data["height"][i]
            bucket = round(y / max(h_i + 4, 1))
            line_groups[bucket].append(i)

        # ── 3. Font mixing WITHIN lines ──
        mixed_font_found = False
        for bucket, indices in line_groups.items():
            if len(indices) < 3:
                continue
            sizes = [ocr_data["height"][i] for i in indices]
            mean_sz = np.mean(sizes)
            for i in indices:
                sz = ocr_data["height"][i]
                if sz > mean_sz * 2.2 or sz < mean_sz * 0.4:
                    word = ocr_data["text"][i]
                    x = ocr_data["left"][i]
                    findings.append(_finding(
                        "warning", "Mixed Font Sizes in Line",
                        f"Font size anomaly near '...{word}...' (col {x}) — possible text insertion",
                        points=10, severity="high",
                        field_location=word
                    ))
                    mixed_font_found = True
                    break
            if mixed_font_found:
                break

        if mixed_font_found:
            suspicious = True
            score -= 10

        # ── 3b. Font character-width ratio check — DISABLED ──
        width_change_found = False

        # ── 4. Font mixing within short isolated labels (e.g., "Name: John") ──
        if not mixed_font_found:
            for bucket, indices in line_groups.items():
                if len(indices) < 2 or len(indices) > 6:
                    continue
                sizes = [ocr_data["height"][i] for i in indices]
                if len(sizes) >= 2:
                    cv_sz = np.std(sizes) / (np.mean(sizes) + 1e-6)
                    if cv_sz > 0.5:
                        words_in_line = [ocr_data["text"][i] for i in indices]
                        line_text = " ".join(words_in_line)
                        findings.append(_finding(
                            "warning", "Inconsistent Font in Field",
                            f"Font size variation detected in '{line_text[:60]}' — possible text replacement",
                            points=5, severity="medium",
                            field_location=line_text[:40]
                        ))
                        suspicious = True
                        score -= 5
                        break

        # ── 5. Alignment inconsistency ──
        sorted_buckets = sorted(line_groups.items())
        if len(sorted_buckets) >= 3:
            align_shifts = []
            for bucket, indices in sorted_buckets:
                lefts = [ocr_data["left"][i] for i in indices]
                if lefts:
                    align_shifts.append(min(lefts))
            if len(align_shifts) >= 3:
                align_std = np.std(align_shifts)
                align_mean = np.mean(align_shifts)
                max_gap = max(abs(align_shifts[i] - align_shifts[i-1]) for i in range(1, len(align_shifts)))
                if max_gap > 200 and align_std > align_mean * 0.5:
                    findings.append(_finding(
                        "warning", "Alignment Inconsistency",
                        "Text blocks show unusual alignment shifts — possible edited content",
                        points=5, severity="medium"
                    ))
                    suspicious = True
                    score -= 5

        # ── 6. Suspicious keywords ──
        text_lower = text.lower()
        found_keywords = [kw for kw in SUSPICIOUS_KEYWORDS if kw in text_lower]
        if found_keywords:
            findings.append(_finding(
                "warning", "Suspicious Keyword Found",
                f"Text contains: {', '.join(found_keywords)}",
                points=10, severity="high",
                field_location=found_keywords[0]
            ))
            suspicious = True
            score -= 10

        # ── 7. Control characters / repetition ──
        text_clean = text.strip()
        suspicious_patterns = [
            (r'[\u0000-\u0008\u000b\u000c\u000e-\u001f]', "Control characters"),
            (r'(.)\1{25,}', "Repeated characters"),
        ]
        for pattern, desc in suspicious_patterns:
            if re.search(pattern, text_clean):
                findings.append(_finding(
                    "warning", f"Suspicious Text: {desc}",
                    "Found unusual patterns in extracted text",
                    points=8, severity="high"
                ))
                suspicious = True
                score -= 8

        # ── 8. AI-generated text detection ──
        try:
            h, w = gray.shape
            total_pixels = h * w
            text_pixel_ratio = np.sum(gray < 200) / total_pixels if total_pixels > 0 else 0

            # Near-zero text variability suggests rendered/perfect text
            if len(words) > 20:
                word_lens = [len(w) for w in words]
                word_len_std = np.std(word_lens) if len(word_lens) > 1 else 0
                if word_len_std < 1.5 and len(words) > 50:
                    findings.append(_finding(
                        "warning", "AI: Unnatural Text Uniformity",
                        f"Word length standard deviation is {word_len_std:.2f} (<1.5). "
                        "AI-generated text often produces unnaturally uniform word lengths "
                        "compared to the variability of human writing.",
                        points=10, severity="high"
                    ))
                    suspicious = True
                    score -= 10

                avg_word_len = np.mean(word_lens)

                # Very consistent word lengths across the document
                if avg_word_len > 4.5 and word_len_std < 2.0:
                    findings.append(_finding(
                        "warning", "AI: Overly Consistent Text Structure",
                        f"Average word length ({avg_word_len:.1f}) is high with low variance ({word_len_std:.1f}) — "
                        "suggests AI-generated academic/formal text rather than natural human writing",
                        points=5, severity="medium"
                    ))
                    suspicious = True
                    score -= 5

            # Check for AI-specific phrasing patterns in extracted text
            ai_phrases = [
                "as an ai", "i don't have personal", "i cannot", "i'm an ai",
                "as a language model", "i'm not able to", "i don't have access to",
                "i am an ai", "i'm an artificial intelligence",
                "as an artificial intelligence", "i do not have personal",
            ]
            text_lower = text.lower()
            for phrase in ai_phrases:
                if phrase in text_lower:
                    findings.append(_finding(
                        "warning", "AI: AI-Generated Text Pattern",
                        f"Text contains '{phrase}' — characteristic of AI-generated content",
                        points=15, severity="high",
                        field_location=phrase
                    ))
                    suspicious = True
                    score -= 15
                    break

            # Check for lorem ipsum / placeholder content
            # Very uniform character distribution suggests generated content
            if len(text) > 200:
                text_clean2 = re.sub(r'\s+', '', text.lower())
                total_chars = len(text_clean2)
                if total_chars > 0:
                    unique_ratio = len(set(text_clean2)) / total_chars
                    if unique_ratio < 0.15:
                        findings.append(_finding(
                            "warning", "AI: Low Character Diversity",
                            f"Character diversity is {unique_ratio:.1%} (<15%) — "
                            "unnaturally uniform character distribution suggests AI-generated or placeholder content",
                            points=10, severity="high"
                        ))
                        suspicious = True
                        score -= 10
        except Exception:
            pass

        # ── 9. Summary finding ──
        if not suspicious:
            findings.append(_finding(
                "info", "Text Analysis: Clean",
                f"{len(words)} words extracted — no signs of tampering",
                points=0, severity="minor"
            ))

    except Exception as e:
        findings.append(_finding(
            "warning", "OCR Processing Error",
            f"Could not process OCR: {str(e)}",
            points=5, severity="medium"
        ))
        suspicious = True
        score -= 5

    status = "suspicious" if suspicious else "clean"
    total_score = max(score, -40)

    return {
        "status": status,
        "score": total_score,
        "findings": findings,
        "text": text if 'text' in dir() and isinstance(text, str) else "",
    }
