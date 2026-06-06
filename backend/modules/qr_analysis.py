import cv2
import numpy as np
from PIL import Image
import os
import sys
import ctypes
import re
import urllib.parse

def _load_pyzbar():
    homebrew_lib_path = "/opt/homebrew/lib/libzbar.dylib"
    try:
        import pyzbar.zbar_library
        original_load = pyzbar.zbar_library.load

        def patched_load():
            try:
                return original_load()
            except ImportError:
                lib = ctypes.cdll.LoadLibrary(homebrew_lib_path)
                return lib, []

        pyzbar.zbar_library.load = patched_load
        from pyzbar.pyzbar import decode as d
        return d
    except Exception:
        pass

    try:
        lib = ctypes.cdll.LoadLibrary(homebrew_lib_path)
        import pyzbar.zbar_library
        pyzbar.zbar_library.load = lambda: (lib, [])
        # Need to reload the wrapper module
        import importlib
        import pyzbar.wrapper
        importlib.reload(pyzbar.wrapper)
        from pyzbar.pyzbar import decode as d
        return d
    except Exception:
        return None

pyzbar_decode = _load_pyzbar()

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

def analyze_qr_codes(image_path):
    findings = []
    score = 0
    qr_codes = []
    suspicious = False

    try:
        img = cv2.imread(image_path)
        if img is None:
            img_pil = Image.open(image_path).convert("RGB")
            img = np.array(img_pil)
            img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        if pyzbar_decode is None:
            findings.append(_finding(
                "warning", "QR Library Not Available",
                "zbar library not found — QR scanning unavailable",
                points=0, severity="minor"
            ))
            decoded_objects = []
        else:
            decoded_objects = pyzbar_decode(gray)

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
