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


def analyze_signatures(image_path, output_dir=None):
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

        original_for_draw = img.copy()
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)

        # Otsu binarisation — adaptive per-document
        _, binary = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

        # Morphological close + dilate to connect nearby strokes
        close_kernel = np.ones((5, 5), np.uint8)
        closed = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, close_kernel)
        dilated = cv2.dilate(closed, np.ones((3, 3), np.uint8), iterations=2)

        h, w = gray.shape
        cfg = CONFIG

        # ── Hough Circle detection for stamps ──
        stamp_candidates = _detect_stamp_hough(gray)

        # ── Contour detection ──
        contours, hierarchy = cv2.findContours(dilated, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
        hier = hierarchy[0] if hierarchy is not None else []

        # Identify page-border contours (outermost, covers >60% of image)
        border_candidates = set()
        if len(hier) > 0:
            for idx in range(len(contours)):
                if int(hier[idx][3]) != -1:
                    continue
                _, _, cw, ch = cv2.boundingRect(contours[idx])
                if cw * ch > h * w * 0.6:
                    border_candidates.add(idx)

        signature_candidates = []

        for idx, contour in enumerate(contours):
            if idx in border_candidates:
                continue

            area = cv2.contourArea(contour)
            if area < cfg["min_area"] or area > cfg["max_area"]:
                continue

            x, y, cw, ch = cv2.boundingRect(contour)
            if ch < cfg["min_height"] or cw < cfg["min_width"]:
                continue
            if ch > h * cfg["max_height_ratio"] or cw > w * cfg["max_width_ratio"]:
                continue

            aspect_ratio = cw / ch if ch > 0 else 0
            extent = area / (cw * ch) if cw * ch > 0 else 0

            # ── Shape features ──
            perimeter = cv2.arcLength(contour, True)
            circularity = (4 * np.pi * area) / (perimeter * perimeter) if perimeter > 0 else 0
            complexity = (perimeter * perimeter) / area if area > 0 else 0

            hull = cv2.convexHull(contour)
            hull_area = cv2.contourArea(hull)
            solidity = area / hull_area if hull_area > 0 else 0

            # Ink density
            mask = np.zeros(gray.shape, dtype=np.uint8)
            cv2.drawContours(mask, [contour], -1, 255, -1)
            ink_pixels = np.sum(binary[mask == 255] > 0)
            mask_pixels = np.sum(mask > 0)
            ink_density = ink_pixels / mask_pixels if mask_pixels > 0 else 0

            pct_y = y / h
            in_bottom = pct_y > cfg["bottom_ratio"]

            # ── Stamp detection via contour ──
            # Stamps are circular/oval: high circularity, aspect near 1.0, high solidity
            is_stamp_shape = (
                circularity > cfg["stamp_circularity_min"]
                and cfg["stamp_extent_min"] < extent < cfg["stamp_extent_max"]
                and cfg["stamp_aspect_min"] < aspect_ratio < cfg["stamp_aspect_max"]
                and solidity > cfg["stamp_solidity_min"]
            )
            if is_stamp_shape:
                # Quick OCR check — if region has text, it's a logo not a stamp
                if not _bbox_contains_text(gray, (x, y, cw, ch)):
                    stamp_candidates.append({
                        "area": area,
                        "position": (x, y, cw, ch),
                        "aspect_ratio": aspect_ratio,
                        "extent": extent,
                        "circularity": circularity,
                        "solidity": solidity,
                        "ink_density": ink_density,
                        "is_stamp": True,
                        "from_hough": False,
                    })
                continue

            # ── Skip non-signature shapes ──
            # Text is typically blocky / solid
            if solidity > cfg["sig_solidity_max"]:
                continue

            # Skip straight horizontal / vertical lines (low complexity)
            if complexity < 15:
                continue

            # Ink density — signatures have moderate density (strokes + white space).
            # Very sparse = noise; extremely dense (>0.75) = solid text block.
            if ink_density < cfg["sig_ink_density_min"] or ink_density > 0.75:
                continue

            # Aspect ratio — signatures are flat and wide
            if not (cfg["sig_aspect_min"] < aspect_ratio < cfg["sig_aspect_max"]):
                if in_bottom and area > 2000 and extent < 0.45:
                    pass
                else:
                    continue

            # Extent
            if not (cfg["sig_extent_min"] < extent < cfg["sig_extent_max"]):
                continue

            # ── Stroke width std ──
            mask = np.zeros(gray.shape, dtype=np.uint8)
            cv2.drawContours(mask, [contour], -1, 255, -1)
            stroke_pixels = np.where(mask[y:y+ch, x:x+cw] > 0)
            if len(stroke_pixels[0]) > 50:
                dist = cv2.distanceTransform(255 - binary[y:y+ch, x:x+cw], cv2.DIST_L2, 5)
                stroke_vals = dist[stroke_pixels]
                if len(stroke_vals) > 10:
                    stroke_std = float(np.std(stroke_vals))
                    if stroke_std < cfg["sig_stroke_std_min"]:
                        continue

            # Complexity — real signatures are organic / curvy
            if complexity < cfg["sig_complexity_min"]:
                continue

            # ── Position score ──
            pos_score = 0
            if in_bottom:
                pos_score += 1
            if 2.5 < aspect_ratio < 5.5:
                pos_score += 1
            if 0.12 < extent < 0.40:
                pos_score += 1
            if area > 3000:
                pos_score += 1
            if 0.15 < ink_density < 0.50:
                pos_score += 1
            if complexity > 22:
                pos_score += 1

            threshold = 3 if in_bottom else 4
            if pos_score < threshold:
                continue

            # ── OCR filter: skip if region contains recognisable text ──
            if _bbox_contains_text(gray, (x, y, cw, ch)):
                continue

            signature_candidates.append({
                "area": area,
                "position": (x, y, cw, ch),
                "aspect_ratio": aspect_ratio,
                "extent": extent,
                "circularity": circularity,
                "complexity": complexity,
                "solidity": solidity,
                "ink_density": ink_density,
                "pos_score": pos_score,
                "pct_y": pct_y,
                "is_stamp": False,
            })

        # ── Merge nearby candidates ──
        all_candidates = signature_candidates + stamp_candidates
        merged = []
        used = set()
        for i, a in enumerate(all_candidates):
            if i in used:
                continue
            group = [a]
            used.add(i)
            for j, b in enumerate(all_candidates):
                if j in used:
                    continue
                ax, ay, aw, ah = a["position"]
                bx, by, bw, bh = b["position"]
                a_cx, a_cy = ax + aw / 2, ay + ah / 2
                b_cx, b_cy = bx + bw / 2, by + bh / 2
                dist = ((a_cx - b_cx) ** 2 + (a_cy - b_cy) ** 2) ** 0.5
                if dist < (aw + ah + bw + bh) / 2:
                    group.append(b)
                    used.add(j)
            merged.append(group)

        # ── Build final blob list ──
        signature_blobs = []
        for group in merged:
            total = sum(m["area"] for m in group)
            xs = [m["position"][0] for m in group]
            ys = [m["position"][1] for m in group]
            x = min(xs)
            y = min(ys)
            bw = max(m["position"][0] + m["position"][2] for m in group) - x
            bh = max(m["position"][1] + m["position"][3] for m in group) - y
            is_stamp = any(m.get("is_stamp", False) for m in group)
            avg_extent = np.mean([m["extent"] for m in group])
            avg_aspect = np.mean([m["aspect_ratio"] for m in group])
            avg_circ = np.mean([m.get("circularity", 0) for m in group])
            avg_complexity = np.mean([m.get("complexity", 0) for m in group])
            pct_y = y / h
            signature_blobs.append({
                "area": total,
                "position": (x, y, bw, bh),
                "aspect_ratio": avg_aspect,
                "extent": avg_extent,
                "circularity": avg_circ,
                "complexity": avg_complexity,
                "is_stamp": is_stamp,
                "pct_y": pct_y,
            })

        signature_blobs.sort(key=lambda b: b["pct_y"])

        total_sig_count = len(signature_blobs)
        sig_list = [b for b in signature_blobs if not b["is_stamp"]]
        stamp_list = [b for b in signature_blobs if b["is_stamp"]]

        # Safety cap — too many blobs = noise
        if total_sig_count > cfg["noise_cap"]:
            total_sig_count = 0
            signature_blobs = []

        # ── Compute confidence & build details ──
        sig_details = []
        for blob in signature_blobs:
            conf = _compute_confidence(blob, h, is_stamp=blob.get("is_stamp", False))
            sig_details.append({
                "confidence": conf,
                "bbox": [int(v) for v in blob["position"]],
                "type": "stamp" if blob.get("is_stamp") else "signature",
                "area": int(blob["area"]),
            })

        signatures_detected = total_sig_count

        # ── Draw highlighted image ──
        overlay = original_for_draw.copy()
        for idx, blob in enumerate(signature_blobs):
            conf = sig_details[idx]["confidence"]
            if conf < cfg["min_report_confidence"]:
                continue  # skip low-confidence in visual
            x, y, bw, bh = blob["position"]
            color = (0, 255, 0) if blob.get("is_stamp") else (0, 0, 255)
            cv2.rectangle(overlay, (x, y), (x + bw, y + bh), color, 3)
            label = f"{'STAMP' if blob.get('is_stamp') else 'SIG'} {conf}%"
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

        if signatures_detected > 0:
            sig_count = len(sig_list)
            stamp_count = len(stamp_list)
            parts = []
            if sig_count > 0:
                parts.append(f"{sig_count} signature(s)")
            if stamp_count > 0:
                parts.append(f"{stamp_count} stamp(s)")
            desc = ", ".join(parts) if parts else f"{signatures_detected} mark(s)"

            # Only report high-confidence findings
            high_conf = [sd for sd in sig_details if sd["confidence"] >= cfg["min_report_confidence"]]

            if high_conf:
                highest = max(high_conf, key=lambda d: d["confidence"])
                primary_type = "signature" if highest["type"] == "signature" else "stamp"
                findings.append(_finding(
                    "info", f"{primary_type.capitalize()} Detected",
                    f"Found {desc} in document (top confidence: {highest['confidence']}%)",
                    points=0, severity="minor"
                ))

                pos = highest["bbox"]
                location = "bottom" if pos[1] > h * 0.5 else "top"
                side = "right" if pos[0] > w * 0.5 else "left" if pos[0] > w * 0.2 else "center"
                findings.append(_finding(
                    "info", "Primary Mark Location",
                    f"{primary_type.capitalize()} detected in {location} {side} with {highest['confidence']}% confidence",
                    points=0, severity="minor"
                ))

                for sd in high_conf[:3]:
                    x, y, bw, bh = sd["bbox"]
                    label = "Stamp" if sd["type"] == "stamp" else "Signature"
                    findings.append(_finding(
                        "info", f"{label} {high_conf.index(sd)+1}",
                        f"Position: ({x}, {y}), Size: {bw}x{bh}, Confidence: {sd['confidence']}%",
                        points=0, severity="minor"
                    ))


            else:
                findings.append(_finding(
                    "info", "Low Confidence Detections",
                    f"Found {signatures_detected} potential marks but confidence is low — manual review recommended",
                    points=0, severity="minor"
                ))
        else:
                findings.append(_finding(
                    "info", "No Signature/Stamp Found",
                    "No signatures or stamps detected in document",
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
        "findings": findings,
        "signatures_count": signatures_detected,
        "signature_details": sig_details,
        "highlight_path": highlight_path,
    }
