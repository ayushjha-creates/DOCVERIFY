import numpy as np
from PIL import Image
import os

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

# ═══════════════════════════════════════════════════════════════
#  CONFIGURATION — all thresholds adjustable here
# ═══════════════════════════════════════════════════════════════
CONFIG = {
    # ── Contour pre-filter ──
    "min_area": 1500,             # Minimum contour area (px²)
    "max_area": 25000,            # Maximum contour area (px²)
    "min_height": 18,             # Minimum bounding-box height (px)
    "min_width": 30,              # Minimum bounding-box width (px)
    "max_height_ratio": 0.40,     # Box height / page height cap
    "max_width_ratio": 0.55,      # Box width / page width cap

    # ── Signature-specific ──
    "sig_aspect_min": 2.0,        # Aspect ratio (w/h) lower bound
    "sig_aspect_max": 7.0,        # Aspect ratio upper bound
    "sig_extent_min": 0.08,       # Extent (area/bbox-area) lower bound
    "sig_extent_max": 0.55,       # Extent upper bound
    "sig_ink_density_min": 0.15,  # Minimum ink density (fraction of dark pixels)
    "sig_solidity_max": 0.70,     # Maximum solidity (text is more solid, sigs are organic)
    "sig_complexity_min": 20,     # Minimum perimeter²/area (signatures are curvy)
    "sig_stroke_std_min": 1.8,    # Minimum stroke width std — text has uniform strokes

    # ── Stamp-specific ──
    "stamp_circularity_min": 0.65, # Circularity lower bound (circle=1.0)
    "stamp_extent_min": 0.40,
    "stamp_extent_max": 0.85,
    "stamp_aspect_min": 0.75,     # Stamp aspect ratio near 1.0 (circular/oval)
    "stamp_aspect_max": 1.40,
    "stamp_solidity_min": 0.70,   # Stamps are relatively solid

    # ── Position ──
    "bottom_ratio": 0.45,         # Only consider contours in bottom 45% of page

    # ── OCR filter ──
    "ocr_max_words": 2,           # Max recognisable words in bbox to still accept
    "ocr_conf_threshold": 40,     # OCR confidence threshold

    # ── Output ──
    "min_report_confidence": 60,  # Don't report detections below this
    "noise_cap": 4,               # If more than this many blobs, treat as noise

    # ── Scoring ──
    "deduction_missing": 0,       # No deduction for missing signature
    "deduction_suspicious": 5,    # Small deduction if suspicious marks
}


def _compute_confidence(sig, h, is_stamp=False):
    """Compute confidence score 0-100 for a signature/stamp blob."""
    conf = 50
    x, y, w, bh = sig["position"]

    if is_stamp:
        # Stamp confidence: circularity and extent are the main signals
        conf += 20
        if sig["circularity"] > 0.70:
            conf += 15
        elif sig["circularity"] > 0.60:
            conf += 8
        if 0.35 < sig["extent"] < 0.80:
            conf += 10
        return min(conf, 100)

    # — Signature confidence —
    aspect = sig["aspect_ratio"]
    extent = sig["extent"]
    area = sig["area"]
    complexity = sig.get("complexity", 0)
    pct_y = y / h

    # Position bonus (bottom is more likely to be a signature)
    if pct_y > 0.60:
        conf += 15
    elif pct_y > 0.45:
        conf += 10
    elif pct_y > 0.30:
        conf += 5

    # Extent: real signatures have moderate extent (not too tight, not too sparse)
    if 0.12 < extent < 0.40:
        conf += 15
    elif extent < 0.55:
        conf += 5

    # Aspect ratio: sweet spot 2.5–5.0
    if 2.5 < aspect < 5.0:
        conf += 10
    elif 2.0 < aspect < 7.0:
        conf += 5

    # Area
    if area > 4000:
        conf += 10
    elif area > 2000:
        conf += 5

    # Complexity — high = curvy, organic
    if complexity > 25:
        conf += 10
    elif complexity > 20:
        conf += 5

    return min(conf, 100)


def _bbox_contains_text(img_gray, bbox):
    """Quick OCR check: if bounding box contains recognisable words, return True."""
    x, y, bw, bh = bbox
    x2 = min(x + bw, img_gray.shape[1])
    y2 = min(y + bh, img_gray.shape[0])
    if x2 <= x or y2 <= y:
        return False
    roi = img_gray[y:y2, x:x2]
    if roi.size < 400:
        return False
    try:
        # Upscale small ROIs so Tesseract has a better chance
        if roi.shape[0] < 30 or roi.shape[1] < 80:
            scale = max(60 / roi.shape[0], 200 / roi.shape[1], 1.0)
            roi = cv2.resize(roi, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        data = pytesseract.image_to_data(roi, output_type=pytesseract.Output.DICT)
        words = [w for w in data["text"] if w.strip()]
        if len(words) > CONFIG["ocr_max_words"]:
            # Check confidence — if high enough, it's real text
            confs = [int(data["conf"][i]) for i in range(len(data["text"]))
                     if data["text"][i].strip() and int(data["conf"][i]) > 0]
            avg_conf = np.mean(confs) if confs else 0
            return avg_conf > CONFIG["ocr_conf_threshold"]
    except Exception:
        pass
    return False


def detect_signature_region(image_path):
    try:
        img = cv2.imread(image_path)
        if img is None:
            pil = Image.open(image_path).convert('RGB')
            img = cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)

        h, w = img.shape[:2]

        # ── METHOD 1: INK CLUSTER IN BOTTOM THIRD ──
        bottom = img[int(h * 0.55):, :]
        gray = cv2.cvtColor(bottom, cv2.COLOR_BGR2GRAY)

        binary = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV,
            blockSize=25, C=10
        )

        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 5))
        closed = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)

        contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        candidates = []
        for cnt in contours:
            x, y, cw, ch = cv2.boundingRect(cnt)
            area = cv2.contourArea(cnt)
            if area < 400: continue
            if area > w * h * 0.12: continue
            if cw == 0 or ch == 0: continue
            aspect = cw / ch
            if aspect < 1.2 or aspect > 12: continue
            if cw < w * 0.08: continue
            hull_area = cv2.contourArea(cv2.convexHull(cnt))
            if hull_area == 0: continue
            solidity = area / hull_area
            if solidity < 0.04 or solidity > 0.65: continue
            candidates.append((area, x, y, cw, ch, cnt))

        if candidates:
            best = max(candidates, key=lambda c: c[0])
            _, x, y, cw, ch, _ = best
            y_full = y + int(h * 0.55)
            return True, [x, y_full, cw, ch]

        # ── METHOD 2: DARK STROKE CLUSTER ──
        gray_full = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        bottom_half = gray_full[h // 2:, :]
        edges = cv2.Canny(bottom_half, 30, 100)
        kernel2 = cv2.getStructuringElement(cv2.MORPH_RECT, (20, 8))
        dilated = cv2.dilate(edges, kernel2, iterations=2)

        contours2, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for cnt in sorted(contours2, key=cv2.contourArea, reverse=True)[:5]:
            x, y, cw, ch = cv2.boundingRect(cnt)
            area = cv2.contourArea(cnt)
            if area < 300: continue
            if cw < w * 0.06: continue
            if cw / max(ch, 1) < 1.5: continue
            pts = cnt.reshape(-1, 2)
            if len(pts) < 10: continue
            y_std = np.std(pts[:, 1])
            if y_std < 3: continue
            y_full = y + h // 2
            return True, [x, y_full, cw, ch]

        # ── METHOD 3: COLOUR SIGNATURE DETECTION ──
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        bottom_hsv = hsv[int(h * 0.5):, :]

        blue_mask = cv2.inRange(bottom_hsv, np.array([100, 50, 30]), np.array([140, 255, 200]))
        dark_mask = cv2.inRange(bottom_hsv, np.array([0, 0, 0]), np.array([180, 255, 80]))
        combined_mask = cv2.bitwise_or(blue_mask, dark_mask)

        kernel3 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (12, 6))
        combined_mask = cv2.morphologyEx(combined_mask, cv2.MORPH_CLOSE, kernel3)

        contours3, _ = cv2.findContours(combined_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for cnt in sorted(contours3, key=cv2.contourArea, reverse=True)[:3]:
            x, y, cw, ch = cv2.boundingRect(cnt)
            area = cv2.contourArea(cnt)
            if area < 300: continue
            if cw < w * 0.05: continue
            if cw / max(ch, 1) < 1.2: continue
            y_full = y + int(h * 0.5)
            return True, [x, y_full, cw, ch]

        return False, None
    except Exception:
        return False, None


def _detect_stamp_hough(img_gray):
    """Detect circular stamps via Hough Circle Transform (conservative)."""
    h, w = img_gray.shape
    circles = cv2.HoughCircles(
        img_gray, cv2.HOUGH_GRADIENT, dp=1.5, minDist=max(h, w) // 4,
        param1=60, param2=40, minRadius=15, maxRadius=min(h, w) // 4
    )
    stamps = []
    if circles is not None:
        circles = np.round(circles[0]).astype("int")
        for (cx, cy, r) in circles:
            x = int(max(cx - r, 0))
            y = int(max(cy - r, 0))
            bw = int(min(2 * r, w - x))
            bh = int(min(2 * r, h - y))
            # Skip if too large — likely page artifact
            if bw > w * 0.25 or bh > h * 0.25:
                continue
            # Skip Hough stamps that overlap text (likely a logo, not a stamp)
            if _bbox_contains_text(img_gray, (x, y, bw, bh)):
                continue
            stamps.append({
                "area": np.pi * r * r,
                "position": (x, y, bw, bh),
                "aspect_ratio": 1.0,
                "extent": np.pi / 4,
                "circularity": 0.85,
                "solidity": 0.90,
                "ink_density": 0.30,
                "is_stamp": True,
                "from_hough": True,
            })
    return stamps


def analyze_signatures(image_path, output_dir=None, doc_class="unknown"):
    if not CV2_AVAILABLE or not TESSERACT_AVAILABLE:
        missing = [m for m, f in [("OpenCV", CV2_AVAILABLE), ("Tesseract", TESSERACT_AVAILABLE)] if not f]
        return {
            "status": "error",
            "score": 0,
            "findings": [{"type": "error", "title": "Signature Analysis Unavailable", "detail": f"Missing: {', '.join(missing)}", "points": 0, "severity": "high"}],
            "signatures_count": 0,
            "signature_details": [],
            "highlight_path": None,
        }

    findings = []
    score = 0
    suspicious = False
    signatures_detected = 0
    sig_details = []
    highlight_path = None

    try:
        # ── Load image ──
        if isinstance(image_path, np.ndarray):
            img = image_path.copy()
        else:
            img = cv2.imread(image_path)
            if img is None:
                img_pil = Image.open(image_path).convert("RGB")
                img = np.array(img_pil)
                img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)

        h, w = img.shape[:2]
        original_for_draw = img.copy()

        # ── Detect signature region using new cascade approach ──
        region_found, bbox = detect_signature_region(image_path)

        if not region_found:
            if doc_class == "system":
                return {
                    "status": "OK",
                    "deduction": 0,
                    "region_found": False,
                    "details": "No handwritten signature detected. Normal for system-generated documents.",
                    "flags": [],
                    "score": 0,
                    "findings": [{"type": "info", "title": "No Signature/Stamp Found",
                                  "detail": "No handwritten signature detected. This is expected for system-generated documents such as boarding passes, tickets, and receipts.",
                                  "points": 0, "severity": "minor"}],
                    "signatures_count": 0, "signature_details": [], "highlight_path": None,
                }
            elif doc_class == "formal":
                return {
                    "status": "WARN",
                    "deduction": 5,
                    "region_found": False,
                    "details": "No handwritten signature region could be detected. Formal documents typically carry a signature or authorisation mark.",
                    "flags": ["NO_SIGNATURE_FOUND"],
                    "score": -5,
                    "findings": [{"type": "warning", "title": "No Signature Detected",
                                  "detail": "No handwritten signature region could be detected. Formal documents typically carry a signature or authorisation mark. This may indicate a digital forgery or a low-quality scan that prevented detection.",
                                  "points": 5, "severity": "medium"}],
                    "signatures_count": 0, "signature_details": [], "highlight_path": None,
                }
            else:
                return {
                    "status": "OK",
                    "deduction": 0,
                    "region_found": False,
                    "details": "No signature region detected. Document type could not be determined.",
                    "flags": [],
                    "score": 0,
                    "findings": [{"type": "info", "title": "No Signature/Stamp Found",
                                  "detail": "No signature region detected. Document type could not be determined.",
                                  "points": 0, "severity": "minor"}],
                    "signatures_count": 0, "signature_details": [], "highlight_path": None,
                }

        # ── Region found — build blob details ──
        x, y, bw, bh = bbox
        signature_blobs = [{
            "area": bw * bh,
            "position": (x, y, bw, bh),
            "aspect_ratio": bw / max(bh, 1),
            "extent": 0.3,
            "circularity": 0.3,
            "complexity": 25,
            "is_stamp": False,
            "pct_y": y / h,
        }]

        total_sig_count = 1
        sig_details = [{
            "confidence": 70,
            "bbox": [x, y, bw, bh],
            "type": "signature",
            "area": bw * bh,
        }]

        signatures_detected = 1

        # ── Draw highlighted image ──
        overlay = original_for_draw.copy()
        color = (0, 0, 255)
        cv2.rectangle(overlay, (x, y), (x + bw, y + bh), color, 3)
        label = f"SIG 70%"
        cv2.putText(overlay, label, (x, max(y - 8, 15)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2)

        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
            highlight_path = os.path.join(output_dir, "signature_overlay.png")
        else:
            highlight_path = image_path.replace(".png", "_signature_overlay.png")
        overlay_rgb = cv2.cvtColor(overlay, cv2.COLOR_BGR2RGB)
        Image.fromarray(overlay_rgb).save(highlight_path)

        # ── Findings ──
        def _finding(ftype, title, detail, points=0, severity="minor", field_location=""):
            return {
                "type": ftype,
                "title": title,
                "detail": detail,
                "points": points,
                "severity": severity,
                "field_location": field_location,
            }

        findings.append(_finding(
            "info", "Signature Detected",
            f"Found signature region in document (bbox: {x},{y} {bw}x{bh})",
            points=0, severity="minor"
        ))
        location = "bottom" if y > h * 0.5 else "top"
        side = "right" if x > w * 0.5 else "left" if x > w * 0.2 else "center"
        findings.append(_finding(
            "info", "Signature Location",
            f"Signature detected in {location} {side}",
            points=0, severity="minor"
        ))

    except Exception as e:
        findings.append(_finding(
            "warning", "Signature Analysis Error",
            f"Could not analyze signatures: {str(e)}",
            points=0, severity="minor"
        ))

    # ── Final status ──
    if signatures_detected == 0:
        status = "no_signature"
    elif suspicious:
        status = "suspicious"
    else:
        status = "signature_detected"
    total_score = max(score, -20)

    return {
        "status": status,
        "score": total_score,
        "deduction": abs(total_score),
        "findings": findings,
        "signatures_count": signatures_detected,
        "signature_details": sig_details,
        "highlight_path": highlight_path,
    }
