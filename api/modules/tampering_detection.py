import cv2
import numpy as np
from PIL import Image, ImageChops
from io import BytesIO
import os
import math


def _finding(ftype, title, detail, points, severity, field_location=""):
    return {
        "type": ftype,
        "title": title,
        "detail": detail,
        "points": points,
        "severity": severity,
        "field_location": field_location,
    }


def detect_ela(image_path, quality=90, output_dir=None):
    findings = []
    score = 0
    ela_image_path = None

    try:
        img = Image.open(image_path).convert("RGB")
        buffer = BytesIO()
        img.save(buffer, format="JPEG", quality=quality)
        buffer.seek(0)
        recompressed = Image.open(buffer).convert("RGB")
        ela = ImageChops.difference(img, recompressed)
        extrema = ela.getextrema()
        max_diff = max([max(e) for e in extrema]) if extrema else 0
        ela_np = np.array(ela)
        ela_gray = np.mean(ela_np, axis=2)
        threshold = 15
        tampered_pixels = np.sum(ela_gray > threshold)
        total_pixels = ela_gray.shape[0] * ela_gray.shape[1]
        tamper_percentage = (tampered_pixels / total_pixels) * 100

        ela_scaled = np.clip(ela_gray * 5, 0, 255).astype(np.uint8)
        ela_colored = cv2.applyColorMap(ela_scaled, cv2.COLORMAP_JET)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
            overlay_path = os.path.join(output_dir, "ela_overlay.png")
        else:
            overlay_path = image_path.replace(".png", "_ela_overlay.png")
        ela_rgb = cv2.cvtColor(ela_colored, cv2.COLOR_BGR2RGB)
        Image.fromarray(ela_rgb).save(overlay_path)

        ela_image_path = overlay_path

        if tamper_percentage > 1.0:
            findings.append(_finding(
                "error", "ELA: Tampering Detected",
                f"Error Level Analysis shows {tamper_percentage:.1f}% altered pixels — likely tampered",
                points=20, severity="high"
            ))
            score -= 20
        elif tamper_percentage > 0.3:
            findings.append(_finding(
                "warning", "ELA: Suspicious Areas",
                f"Error Level Analysis shows {tamper_percentage:.1f}% altered pixels — may be edited",
                points=5, severity="medium"
            ))
            score -= 5
        else:
            findings.append(_finding(
                "info", "ELA: Clean",
                f"Error Level Analysis shows only {tamper_percentage:.1f}% altered pixels — consistent",
                points=0, severity="minor"
            ))

    except Exception as e:
        findings.append(_finding(
            "warning", "ELA Processing Error",
            f"Could not perform ELA: {str(e)}",
            points=0, severity="minor"
        ))

    return findings, score, ela_image_path


def detect_noise_inconsistency(image_path):
    findings = []
    score = 0
    suspicious = False

    try:
        img = cv2.imread(image_path)
        if img is None:
            img_pil = Image.open(image_path).convert("RGB")
            img = np.array(img_pil)
            img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        h, w = gray.shape
        grid_size = 50
        noise_levels = []
        for y in range(0, h - grid_size, grid_size):
            for x in range(0, w - grid_size, grid_size):
                patch = gray[y:y+grid_size, x:x+grid_size]
                noise = np.std(patch)
                noise_levels.append(noise)

        if noise_levels:
            noise_array = np.array(noise_levels)
            mean_noise = np.mean(noise_array)
            std_noise = np.std(noise_array)
            inconsistent = noise_array[noise_array > mean_noise + 2.5 * std_noise]
            if len(inconsistent) > len(noise_levels) * 0.07:
                findings.append(_finding(
                    "warning", "Noise Inconsistency Detected",
                    f"{len(inconsistent)} regions with abnormal noise levels — possible splicing",
                    points=15, severity="high"
                ))
                suspicious = True
                score -= 15

        if not findings:
            findings.append(_finding(
                "info", "Noise Pattern: Normal",
                "Noise distribution is consistent across the document",
                points=0, severity="minor"
            ))

    except Exception as e:
        findings.append(_finding(
            "warning", "Noise Analysis Error",
            f"Could not analyze noise: {str(e)}",
            points=0, severity="minor"
        ))

    return findings, score, suspicious


def detect_copy_paste(image_path):
    findings = []
    score = 0
    suspicious = False
    highlight_img = None

    try:
        img = cv2.imread(image_path)
        if img is None:
            img_pil = Image.open(image_path).convert("RGB")
            img = np.array(img_pil)
            img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        sift = cv2.SIFT_create()
        kp, des = sift.detectAndCompute(gray, None)

        if des is not None and len(kp) > 10:
            FLANN_INDEX_KDTREE = 1
            index_params = dict(algorithm=FLANN_INDEX_KDTREE, trees=5)
            search_params = dict(checks=50)
            flann = cv2.FlannBasedMatcher(index_params, search_params)
            matches = flann.knnMatch(des, des, k=2)
            similar_regions = []
            for i, pair in enumerate(matches):
                if len(pair) >= 2:
                    m, n = pair
                    if m.distance < 0.75 * n.distance and m.queryIdx != m.trainIdx:
                        similar_regions.append((m.queryIdx, m.trainIdx, m.distance))

            if len(similar_regions) > len(kp) * 0.3:
                findings.append(_finding(
                    "warning", "Potential Copy-Paste Detected",
                    f"Found {len(similar_regions)} highly similar feature pairs — possible cloning",
                    points=10, severity="high"
                ))
                suspicious = True
                score -= 10
            elif len(similar_regions) > 5:
                findings.append(_finding(
                    "info", "Minor Similar Regions",
                    f"Found {len(similar_regions)} similar feature pairs — likely natural repetition",
                    points=0, severity="minor"
                ))
            else:
                findings.append(_finding(
                    "info", "Copy-Paste Check: Clean",
                    "No significant cloned regions detected",
                    points=0, severity="minor"
                ))
        else:
            findings.append(_finding(
                "info", "Copy-Paste Check: Limited Features",
                "Insufficient features for SIFT analysis",
                points=0, severity="minor"
            ))

    except Exception as e:
        findings.append(_finding(
            "warning", "Copy-Paste Detection Error",
            f"Could not perform copy-paste analysis: {str(e)}",
            points=0, severity="minor"
        ))

    return findings, score, suspicious


def detect_blur_edges(image_path):
    findings = []
    score = 0
    suspicious = False

    try:
        img = cv2.imread(image_path)
        if img is None:
            img_pil = Image.open(image_path).convert("RGB")
            img = np.array(img_pil)
            img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()

        h, w = gray.shape
        grid_size = 100
        blur_grid = []
        for y in range(0, h - grid_size, grid_size):
            row = []
            for x in range(0, w - grid_size, grid_size):
                patch = gray[y:y+grid_size, x:x+grid_size]
                var = cv2.Laplacian(patch, cv2.CV_64F).var()
                row.append(var)
            blur_grid.append(row)

        blur_array = np.array(blur_grid)
        if blur_array.size > 0:
            mean_blur = np.mean(blur_array)
            std_blur = np.std(blur_array)
            anomalies = blur_array[blur_array < mean_blur - 1.5 * std_blur]
            if laplacian_var > 1400:
                findings.append(_finding(
                    "warning", "Unnatural Sharpness",
                    f"Laplacian variance is {laplacian_var:.1f} (>1400). "
                    "Extremely high sharpness values suggest AI-generated or "
                    "synthetic image content rather than a natural scan.",
                    points=10, severity="high"
                ))
                suspicious = True
                score -= 10
            elif len(anomalies) > blur_array.size * 0.15:
                findings.append(_finding(
                    "warning", "Inconsistent Blur Detected",
                    f"{len(anomalies)} regions with abnormal blur — possible edge tampering",
                    points=10, severity="high"
                ))
                suspicious = True
                score -= 10
            elif laplacian_var < 50:
                findings.append(_finding(
                    "warning", "Overall Blur Detection",
                    "Document appears unusually blurry — may be low quality or tampered",
                    points=5, severity="medium"
                ))
                suspicious = True
                score -= 5
            else:
                findings.append(_finding(
                    "info", "Blur/Edge Analysis: Clean",
                    "Edge consistency appears normal across document",
                    points=0, severity="minor"
                ))

    except Exception as e:
        findings.append(_finding(
            "warning", "Blur Analysis Error",
            f"Could not perform blur analysis: {str(e)}",
            points=0, severity="minor"
        ))

    return findings, score, suspicious


# ── AI-Generated Document Detection ──


def detect_ai_smooth_background(gray):
    findings = []
    score = 0
    try:
        h, w = gray.shape
        patches = []
        step = 40
        for y in range(0, h - step, step):
            for x in range(0, w - step, step):
                patch = gray[y:y + step, x:x + step]
                patches.append(np.std(patch))
        if patches:
            mean_std = float(np.mean(patches))
            if mean_std < 6.0:
                findings.append(_finding(
                    "warning", "AI: Unnaturally Smooth Background",
                    f"Background texture variance is {mean_std:.2f} (threshold: <6.0). "
                    "AI-generated images often have perfectly uniform backgrounds "
                    "lacking the sensor noise found in camera/scanner captures.",
                    points=15, severity="high"
                ))
                score -= 15
            elif mean_std < 10.0:
                findings.append(_finding(
                    "warning", "AI: Suspiciously Smooth Background",
                    f"Background texture variance is {mean_std:.2f} — lower than typical scanned documents",
                    points=5, severity="medium"
                ))
                score -= 5
    except Exception as e:
        findings.append(_finding(
            "warning", "AI Background Check Error",
            f"Could not analyze background texture: {str(e)}",
            points=0, severity="minor"
        ))
    return findings, score


def detect_ai_perfect_borders(gray):
    findings = []
    score = 0
    try:
        h, w = gray.shape
        edges = cv2.Canny(gray, 50, 150)
        top_strip = edges[0:max(1, h // 40), :]
        bottom_strip = edges[max(0, h - h // 40):h, :]
        left_strip = edges[:, 0:max(1, w // 40)]
        right_strip = edges[:, max(0, w - w // 40):w]
        strips = [("top", top_strip), ("bottom", bottom_strip),
                  ("left", left_strip), ("right", right_strip)]
        perfect_count = 0
        for name, strip in strips:
            if strip.size == 0:
                continue
            edge_ratio = float(np.sum(strip > 0)) / strip.size
            if edge_ratio < 0.005:
                perfect_count += 1
        if perfect_count >= 3:
            findings.append(_finding(
                "warning", "AI: Pixel-Perfect Borders",
                f"{perfect_count}/4 document borders have near-zero edge activity. "
                "AI-generated documents often produce mathematically perfect borders "
                "that lack the slight imperfections of scanned/captured documents.",
                points=10, severity="high"
            ))
            score -= 10
        elif perfect_count >= 2:
            findings.append(_finding(
                "warning", "AI: Suspiciously Clean Borders",
                f"{perfect_count}/4 borders appear unnaturally clean",
                points=5, severity="medium"
            ))
            score -= 5
    except Exception as e:
        findings.append(_finding(
            "warning", "AI Border Check Error",
            f"Could not analyze borders: {str(e)}",
            points=0, severity="minor"
        ))
    return findings, score


def detect_ai_rendered_text(gray):
    findings = []
    score = 0
    try:
        grad_x = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
        grad_y = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
        magnitude = np.sqrt(grad_x ** 2 + grad_y ** 2)
        angle = np.arctan2(grad_y, grad_x + 1e-8)
        high_grad = magnitude > 30
        if np.sum(high_grad) < 100:
            return findings, score
        major_angles = angle[high_grad]
        hist, _ = np.histogram(major_angles, bins=36, range=(-np.pi, np.pi))
        hist_sum = float(np.sum(hist))
        if hist_sum > 0:
            top2 = sorted(hist, reverse=True)[:2]
            coherence = (top2[0] + top2[1]) / hist_sum
            if coherence > 0.80:
                findings.append(_finding(
                    "warning", "AI: Rendered Text Texture",
                    f"Gradient direction coherence is {coherence:.2f} (>0.80). "
                    "AI-generated text often has unnaturally uniform stroke directions "
                    "compared to the varied texture of scanned text.",
                    points=15, severity="high"
                ))
                score -= 15
            elif coherence > 0.70:
                findings.append(_finding(
                    "warning", "AI: Suspicious Text Texture",
                    f"Gradient direction coherence is {coherence:.2f}",
                    points=5, severity="medium"
                ))
                score -= 5
    except Exception as e:
        findings.append(_finding(
            "warning", "AI Text Texture Error",
            f"Could not analyze text texture: {str(e)}",
            points=0, severity="minor"
        ))
    return findings, score


def detect_ai_unnatural_colour(img_bgr):
    findings = []
    score = 0
    try:
        hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
        saturation = hsv[:, :, 1].astype(np.float32) / 255.0
        sat_mean = float(np.mean(saturation))
        if sat_mean < 0.03:
            findings.append(_finding(
                "warning", "AI: Unnatural Colour Distribution",
                f"Mean saturation is {sat_mean:.4f} (<0.03). "
                "AI-generated documents often have compressed, unnatural colour "
                "distributions that lack the slight colour variation of real documents.",
                points=10, severity="high"
            ))
            score -= 10
        elif sat_mean < 0.06:
            findings.append(_finding(
                "warning", "AI: Suspicious Colour Distribution",
                f"Mean saturation is {sat_mean:.4f}",
                points=5, severity="medium"
            ))
            score -= 5
    except Exception as e:
        findings.append(_finding(
            "warning", "AI Colour Check Error",
            f"Could not analyze colour: {str(e)}",
            points=0, severity="minor"
        ))
    return findings, score


def detect_inconsistent_resolution(img_bgr):
    findings = []
    score = 0
    try:
        h, w = img_bgr.shape[:2]
        gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
        fft = np.fft.fft2(gray)
        fft_shift = np.fft.fftshift(fft)
        magnitude = np.log(np.abs(fft_shift) + 1)
        cy, cx = magnitude.shape[0] // 2, magnitude.shape[1] // 2
        radius = min(cy, cx)
        rings = 4
        ring_energies = []
        for i in range(rings):
            inner = int(radius * i / rings)
            outer = int(radius * (i + 1) / rings)
            mask = np.zeros_like(magnitude, dtype=np.uint8)
            cv2.circle(mask, (cx, cy), outer, 1, -1)
            if inner > 0:
                inner_mask = np.zeros_like(magnitude, dtype=np.uint8)
                cv2.circle(inner_mask, (cx, cy), inner, 1, -1)
                mask = cv2.subtract(mask, inner_mask)
            energy = float(np.sum(magnitude[mask > 0]))
            ring_energies.append(energy)
        if ring_energies and max(ring_energies) > 0:
            ring_ratio = max(ring_energies) / (min(ring_energies) + 1e-8)
            if ring_ratio > 50:
                findings.append(_finding(
                    "warning", "AI: Inconsistent Resolution",
                    f"Frequency band energy ratio is {ring_ratio:.1f} — suggests "
                    "mixed-resolution content typical of AI generation or compositing.",
                    points=10, severity="high"
                ))
                score -= 10
            elif ring_ratio > 20:
                findings.append(_finding(
                    "warning", "AI: Slightly Inconsistent Resolution",
                    f"Frequency band energy ratio is {ring_ratio:.1f}",
                    points=5, severity="medium"
                ))
                score -= 5
    except Exception as e:
        findings.append(_finding(
            "warning", "AI Resolution Check Error",
            f"Could not analyze resolution: {str(e)}",
            points=0, severity="minor"
        ))
    return findings, score


def analyze_tampering(image_path, output_dir=None):
    all_findings = []
    total_score = 0
    final_suspicious = False
    marked_image_path = None

    findings_ela, score_ela, ela_path = detect_ela(image_path, output_dir=output_dir)
    findings_noise, score_noise, noise_susp = detect_noise_inconsistency(image_path)
    findings_cp, score_cp, cp_susp = detect_copy_paste(image_path)
    findings_blur, score_blur, blur_susp = detect_blur_edges(image_path)

    # ── AI detection checks ──
    try:
        if isinstance(image_path, np.ndarray):
            img_bgr = image_path.copy()
        else:
            img_bgr = cv2.imread(image_path)
            if img_bgr is None:
                img_pil = Image.open(image_path).convert("RGB")
                img_bgr = np.array(img_pil)
                img_bgr = cv2.cvtColor(img_bgr, cv2.COLOR_RGB2BGR)
        gray_ai = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)

        findings_ai_bg, score_ai_bg = detect_ai_smooth_background(gray_ai)
        findings_ai_borders, score_ai_borders = detect_ai_perfect_borders(gray_ai)
        findings_ai_text, score_ai_text = detect_ai_rendered_text(gray_ai)
        findings_ai_colour, score_ai_colour = detect_ai_unnatural_colour(img_bgr)
        findings_ai_res, score_ai_res = detect_inconsistent_resolution(img_bgr)
    except Exception as e:
        findings_ai_bg, score_ai_bg = [], 0
        findings_ai_borders, score_ai_borders = [], 0
        findings_ai_text, score_ai_text = [], 0
        findings_ai_colour, score_ai_colour = [], 0
        findings_ai_res, score_ai_res = [], 0

    all_findings.extend(findings_ela)
    all_findings.extend(findings_noise)
    all_findings.extend(findings_cp)
    all_findings.extend(findings_blur)
    all_findings.extend(findings_ai_bg)
    all_findings.extend(findings_ai_borders)
    all_findings.extend(findings_ai_text)
    all_findings.extend(findings_ai_colour)
    all_findings.extend(findings_ai_res)

    ai_suspicious = bool(score_ai_bg < 0 or score_ai_borders < 0 or
                         score_ai_text < 0 or score_ai_colour < 0 or score_ai_res < 0)

    total_score = score_ela + score_noise + score_cp + score_blur
    total_score += score_ai_bg + score_ai_borders + score_ai_text + score_ai_colour + score_ai_res
    final_suspicious = noise_susp or cp_susp or blur_susp or (score_ela < -10) or ai_suspicious

    if ela_path:
        marked_image_path = ela_path

    if not all_findings:
        all_findings.append(_finding(
            "info", "Tampering Check: Clean",
            "All tampering detection checks passed",
            points=0, severity="minor"
        ))

    status = "tampered" if final_suspicious else "clean"
    total_score = max(total_score, -60)

    return {
        "status": status,
        "score": total_score,
        "findings": all_findings,
        "marked_image_path": marked_image_path
    }
