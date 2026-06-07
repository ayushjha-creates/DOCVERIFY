import numpy as np
from PIL import Image
import os
import re
import urllib.parse

try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    cv2 = None
    CV2_AVAILABLE = False

TRUSTED_DOMAINS = [
    "gov.in", "gov.sg", "gov.my", "edu", "ac.in",
    "document-verify.com", "verify.gov"
]

SUSPICIOUS_TLDS = [".xyz", ".tk", ".ml", ".ga", ".cf", ".gq", ".top", ".loan"]


def _finding(ftype, title, detail, points=0, severity="minor", field_location=""):
    return {
        "type": ftype,
        "title": title,
        "detail": detail,
        "points": points,
        "severity": severity,
        "field_location": field_location,
    }


def _decode_qr_cv2(gray):
    qr_detector = cv2.QRCodeDetector()
    data, bbox, _ = qr_detector.detectAndDecode(gray)
    if data:
        return _make_qr_obj(data, bbox)
    return None


def _decode_multi_qr(gray):
    try:
        ret, data_list, bbox_list = cv2.QRCodeDetector().detectAndDecodeMulti(gray)
    except AttributeError:
        return None
    if not ret or not data_list:
        return None
    results = []
    for data, bbox in zip(data_list, bbox_list):
        if data:
            results.append(_make_qr_obj(data, bbox))
    return results or None


def _make_qr_obj(data, bbox):
    if bbox is not None and len(bbox) > 0:
        pts = np.array(bbox).astype(int)
        if pts.ndim == 3:
            pts = pts[0]
        left = int(min(pts[:, 0]))
        top = int(min(pts[:, 1]))
        right = int(max(pts[:, 0]))
        bottom = int(max(pts[:, 1]))
    else:
        left = top = right = bottom = 0
    class MockObj:
        pass
    obj = MockObj()
    obj.data = data.encode() if isinstance(data, str) else data
    obj.type = "QRCODE"
    rect = MockObj()
    rect.left = left
    rect.top = top
    rect.width = right - left
    rect.height = bottom - top
    obj.rect = rect
    return obj


def _find_all_qr_cv2(gray):
    results = _decode_multi_qr(gray)
    if results is not None:
        return results
    all_objs = []
    remaining = gray.copy()
    for _ in range(10):
        obj = _decode_qr_cv2(remaining)
        if obj is None:
            break
        all_objs.append(obj)
        x, y, w, h = obj.rect.left, obj.rect.top, obj.rect.width, obj.rect.height
        x = max(x - 10, 0)
        y = max(y - 10, 0)
        w = min(w + 20, remaining.shape[1] - x)
        h = min(h + 20, remaining.shape[0] - y)
        cv2.rectangle(remaining, (x, y), (x + w, y + h), (0,), -1)
        if h < 10 or w < 10:
            break
    return all_objs


def analyze_qr_codes(image_path):
    findings = []
    score = 0
    qr_codes = []
    suspicious = False

    if not CV2_AVAILABLE:
        return {"status": "error", "score": 0, "findings": [{"type": "error", "title": "QR Unavailable", "detail": "OpenCV not available", "points": 0, "severity": "high"}], "qr_codes": []}

    try:
        img = cv2.imread(image_path)
        if img is None:
            img_pil = Image.open(image_path).convert("RGB")
            img = np.array(img_pil)
            img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        decoded_objects = _find_all_qr_cv2(gray)

        if not decoded_objects:
            findings.append(_finding(
                "info", "No QR Codes Found",
                "No QR codes detected in document",
                points=0, severity="minor"
            ))
        else:
            urls_found = []
            for obj in decoded_objects:
                data = obj.data.decode("utf-8")
                rect = obj.rect
                qr_info = {
                    "data": data,
                    "type": str(obj.type),
                    "position": {
                        "x": rect.left, "y": rect.top,
                        "w": rect.width, "h": rect.height
                    }
                }
                qr_codes.append(qr_info)

                if data.startswith("http://") or data.startswith("https://"):
                    urls_found.append(data)
                    parsed = urllib.parse.urlparse(data)
                    domain = parsed.netloc.lower()

                    trusted = any(domain.endswith(td) for td in TRUSTED_DOMAINS)
                    suspicious_tld = any(domain.endswith(tld) for tld in SUSPICIOUS_TLDS)
                    is_ip = bool(re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}', domain))

                    if not trusted:
                        if suspicious_tld:
                            findings.append(_finding(
                                "warning", "Suspicious QR Domain",
                                f"QR code links to suspicious TLD: {domain}",
                                points=15, severity="high"
                            ))
                            suspicious = True
                            score -= 15
                        elif is_ip:
                            findings.append(_finding(
                                "warning", "QR Links to IP Address",
                                f"QR code links directly to IP: {domain}",
                                points=10, severity="medium"
                            ))
                            suspicious = True
                            score -= 10
                        else:
                            findings.append(_finding(
                                "warning", "Unverified QR Domain",
                                f"QR code links to unverified domain: {domain}",
                                points=5, severity="medium"
                            ))
                            score -= 5
                    else:
                        findings.append(_finding(
                            "info", "Trusted QR Domain",
                            f"QR code links to trusted domain: {domain}",
                            points=0, severity="minor"
                        ))
                else:
                    non_url_data = data[:50] + "..." if len(data) > 50 else data
                    findings.append(_finding(
                        "info", "QR Code Found",
                        f"Content: {non_url_data}",
                        points=0, severity="minor"
                    ))

            if len(qr_codes) > 3:
                findings.append(_finding(
                    "warning", "Multiple QR Codes",
                    f"Found {len(qr_codes)} QR codes — unusually high count",
                    points=5, severity="medium"
                ))
                suspicious = True
                score -= 5

            data_strings = [q["data"] for q in qr_codes]
            if len(data_strings) != len(set(data_strings)):
                findings.append(_finding(
                    "warning", "Duplicate QR Codes",
                    "Duplicate QR codes detected in document",
                    points=10, severity="high"
                ))
                suspicious = True
                score -= 10

    except Exception as e:
        findings.append(_finding(
            "warning", "QR Analysis Error",
            f"Could not analyze QR codes: {str(e)}",
            points=5, severity="medium"
        ))
        suspicious = True
        score -= 5

    status = "suspicious" if suspicious else "clean"
    final_score = max(score, -40)

    return {
        "status": status,
        "score": final_score,
        "findings": findings,
        "qr_codes": qr_codes
    }
