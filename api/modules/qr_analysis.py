import cv2
import numpy as np
from PIL import Image
import urllib.parse
import socket

try:
    from pyzbar.pyzbar import decode as pyzbar_decode
    PYZBAR_AVAILABLE = True
except ImportError:
    PYZBAR_AVAILABLE = False
    pyzbar_decode = None

SUSPICIOUS_TLDS = ['.xyz', '.top', '.click', '.tk', '.ml', '.ga', '.cf']


def detect_all_qrs(image_path):
    img_pil = Image.open(image_path).convert('RGB')
    img_cv = cv2.cvtColor(np.array(img_pil), cv2.COLOR_RGB2BGR)
    results = []

    if PYZBAR_AVAILABLE:
        found = pyzbar_decode(img_pil)
        results.extend(found)
        gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
        _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        found2 = pyzbar_decode(Image.fromarray(thresh))
    else:
        found = _decode_qr_cv2(img_cv)
        found2 = []
        if found:
            results.append(found)

    unique = []
    seen_data = set()
    for qr in results + (found2 if PYZBAR_AVAILABLE else []):
        data_str = qr.data.decode('utf-8', errors='ignore') if isinstance(qr.data, bytes) else str(qr.data)
        k = (data_str, qr.rect.left // 20, qr.rect.top // 20)
        if k not in seen_data:
            seen_data.add(k)
            unique.append(qr)
    return unique


def _decode_qr_cv2(img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    qr_detector = cv2.QRCodeDetector()
    data, bbox, _ = qr_detector.detectAndDecode(gray)
    if data:
        return type('QRObj', (), {'data': data.encode(), 'type': 'QRCODE', 'rect': type('Rect', (), {'left': 0, 'top': 0, 'width': 0, 'height': 0})})()
    return None


def analyze_single_qr(qr, index):
    data_str = qr.data.decode('utf-8', errors='ignore') if isinstance(qr.data, bytes) else str(qr.data)
    result = {
        "index": index,
        "data": data_str,
        "type": str(qr.type),
        "position": {
            "left": qr.rect.left, "top": qr.rect.top,
            "width": qr.rect.width, "height": qr.rect.height,
        },
        "status": "OK",
        "flags": [],
        "details": "",
    }

    data = result["data"]

    if not data or len(data.strip()) == 0:
        result["flags"].append("EMPTY_QR")
        result["status"] = "FAIL"
        result["details"] = f"QR #{index+1} could not be decoded or contains no data."
        return result

    if data.startswith("http://") or data.startswith("https://"):
        try:
            parsed = urllib.parse.urlparse(data)
            domain = parsed.netloc
            try:
                socket.gethostbyname(domain)
                domain_resolves = True
            except socket.gaierror:
                domain_resolves = False

            if not domain_resolves:
                result["flags"].append("DEAD_LINK")
                result["status"] = "FAIL"
                result["details"] = f"QR #{index+1} links to '{domain}' which does not resolve. Dead links on official documents indicate a forged or outdated QR."
            else:
                if any(domain.endswith(t) for t in SUSPICIOUS_TLDS):
                    result["flags"].append("SUSPICIOUS_DOMAIN")
                    result["status"] = "WARN"
                    result["details"] = f"QR #{index+1} links to '{domain}' which uses a TLD associated with free/spam domains."
                else:
                    result["status"] = "OK"
                    result["details"] = f"QR #{index+1} decoded successfully. URL '{data[:60]}' resolves to a valid domain."
        except Exception as e:
            result["flags"].append("URL_PARSE_ERROR")
            result["status"] = "WARN"
            result["details"] = f"QR #{index+1} URL could not be parsed: {e}"
    else:
        result["status"] = "OK"
        result["details"] = f"QR #{index+1} contains non-URL data: '{data[:80]}'. No domain verification needed."

    return result


def analyse_qr(file_path):
    all_qrs = detect_all_qrs(file_path)

    if len(all_qrs) == 0:
        return {
            "status": "OK",
            "deduction": 0,
            "qr_count": 0,
            "details": "No QR code detected in this document. This is normal for many document types.",
            "individual_results": [],
            "flags": [],
        }

    individual = []
    for i, qr in enumerate(all_qrs):
        individual.append(analyze_single_qr(qr, i))

    all_data = [r["data"] for r in individual]
    global_flags = []
    if len(set(all_data)) < len(all_data):
        global_flags.append("DUPLICATE_QR_DATA")

    statuses = [r["status"] for r in individual]

    if "FAIL" in statuses:
        overall_status = "FAIL"
        deduction = 30
    elif "WARN" in statuses or global_flags:
        overall_status = "WARN"
        deduction = 15
    else:
        overall_status = "OK"
        deduction = 0

    summary_parts = []
    for r in individual:
        summary_parts.append(f"QR {r['index']+1}: {r['status']} -- {r['details']}")
    summary = " | ".join(summary_parts)
    if global_flags:
        summary += " DUPLICATE QR DATA DETECTED."

    return {
        "status": overall_status,
        "deduction": deduction,
        "qr_count": len(all_qrs),
        "details": summary,
        "individual_results": individual,
        "flags": global_flags,
    }
