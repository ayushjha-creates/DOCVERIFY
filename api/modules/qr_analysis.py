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
    results = []
    dbg = {"img_size": "?", "multi": 0, "iter": 0, "pyzbar": 0}

    def _load():
        img = Image.open(image_path).convert('RGB')
        cvimg = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
        g = cv2.cvtColor(cvimg, cv2.COLOR_BGR2GRAY)
        h, w = g.shape
        dbg["img_size"] = f"{w}x{h}"
        return g, img

    def _add(data, pts=None):
        if data and not any(r["data"] == data for r in results):
            results.append(_make_qr_obj_from_cv(data, pts))
            return True
        return False

    # Pass 1: Multi on full gray
    gray, _ = _load()
    try:
        ret, dlist, plist, *_ = cv2.QRCodeDetector().detectAndDecodeMulti(gray)
        if ret and dlist:
            for data, pts in zip(dlist, plist):
                if _add(data, pts):
                    dbg["multi"] += 1
    except (AttributeError, cv2.error):
        pass

    # Pass 2: Multi on thresholded
    gray, _ = _load()
    th = _threshold(gray)
    try:
        ret, dlist, plist, *_ = cv2.QRCodeDetector().detectAndDecodeMulti(th)
        if ret and dlist:
            for data, pts in zip(dlist, plist):
                if _add(data, pts):
                    dbg["multi"] += 1
    except (AttributeError, cv2.error):
        pass

    # Pass 3: Iterative mask-and-re-Multi
    gray, _ = _load()
    remaining = gray.copy()
    for _ in range(8):
        try:
            ret, dlist, plist, *_ = cv2.QRCodeDetector().detectAndDecodeMulti(remaining)
            if not ret or not dlist:
                break
            new_any = False
            for data, pts in zip(dlist, plist):
                if _add(data, pts):
                    new_any = True
                    dbg["multi"] += 1
            if not new_any:
                break
            mask = np.ones_like(remaining, dtype=np.uint8) * 255
            for pts in plist:
                if pts is not None and len(pts) > 0:
                    cv2.fillPoly(mask, [np.array(pts, dtype=np.int32).reshape(-1, 2)], 0)
            remaining = cv2.bitwise_and(remaining, mask)
        except (AttributeError, cv2.error):
            break

    # Pass 4: detectAndDecode on full image
    gray, _ = _load()
    data, bbox, _ = cv2.QRCodeDetector().detectAndDecode(gray)
    if _add(data, bbox):
        dbg["iter"] += 1

    # Pass 5+6: Overlapping tiled detection (handles QRs straddling the midline)
    gray, _ = _load()
    h, w = gray.shape
    # Use overlapping horizontal strips: left 70%, right 70%, center 70%
    tile_w = int(w * 0.72)
    for x_start in [0, max(0, w // 4), max(0, w // 2)]:
        x_end = min(x_start + tile_w, w)
        if x_end - x_start < 100:
            continue
        tile = gray[:, x_start:x_end]
        try:
            ret, dlist, plist, *_ = cv2.QRCodeDetector().detectAndDecodeMulti(tile)
            if ret and dlist:
                for data, pts in zip(dlist, plist):
                    if _add(data, pts):
                        dbg["multi"] += 1
        except (AttributeError, cv2.error):
            pass
        try:
            data, bbox, _ = cv2.QRCodeDetector().detectAndDecode(tile)
            if _add(data, bbox):
                dbg["iter"] += 1
        except (AttributeError, cv2.error):
            pass

    # Pass 7: pyzbar supplement
    gray_pil, img_pil = _load()
    if PYZBAR_AVAILABLE:
        try:
            for img_in in (img_pil, img_pil.convert('L'), Image.fromarray(gray_pil)):
                pyz_found = pyzbar_decode(img_in)
                for qr in pyz_found:
                    data_str = qr.data.decode('utf-8', errors='ignore') if isinstance(qr.data, bytes) else str(qr.data)
                    if data_str and not any(r["data"] == data_str for r in results):
                        results.append(_make_qr_obj_from_pyzbar(qr))
                        dbg["pyzbar"] += 1
        except Exception:
            pass

    seen_data = set()
    unique = []
    for r in results:
        if r["data"] not in seen_data:
            seen_data.add(r["data"])
            unique.append(r)

    print(f"[qr] detect: multi={dbg['multi']} iter={dbg['iter']} pyz={dbg['pyzbar']} total={len(results)} unique={len(unique)} img={dbg['img_size']}", flush=True)
    return unique, dbg


def _threshold(gray):
    try:
        _, th = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        return th
    except Exception:
        return gray


def _make_qr_obj_from_cv(data, bbox):
    if bbox is not None and len(bbox) > 0:
        pts = np.array(bbox[0] if isinstance(bbox, (list, tuple)) or bbox.ndim == 3 else bbox).astype(int)
        if pts.ndim == 3:
            pts = pts[0]
        left, top = int(min(pts[:, 0])), int(min(pts[:, 1]))
        right, bottom = int(max(pts[:, 0])), int(max(pts[:, 1]))
    else:
        left = top = right = bottom = 0
    return {
        "data": data if isinstance(data, str) else data.decode('utf-8', errors='ignore'),
        "position": {"left": left, "top": top, "width": right - left, "height": bottom - top},
    }


def _make_qr_obj_from_pyzbar(qr):
    data_str = qr.data.decode('utf-8', errors='ignore') if isinstance(qr.data, bytes) else str(qr.data)
    return {
        "data": data_str,
        "position": {"left": qr.rect.left, "top": qr.rect.top, "width": qr.rect.width, "height": qr.rect.height},
    }


def analyze_single_qr(qr, index):
    result = {
        "index": index,
        "data": qr["data"],
        "position": qr["position"],
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
    all_qrs, qr_dbg = detect_all_qrs(file_path)

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
        "_dbg": qr_dbg,
    }
