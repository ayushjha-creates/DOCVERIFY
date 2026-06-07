import os
import sys
import json
import uuid
import base64
import io
import traceback
import shutil
import datetime
import logging
import subprocess

_api_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _api_dir)

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

logging.basicConfig(level=logging.INFO, stream=sys.stdout)
logger = logging.getLogger("docverify")

app = FastAPI(title="DOCVERIFY AI API", version="1.0.0", root_path="/api")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _img_to_b64(path: str) -> str:
    try:
        from PIL import Image
        img = Image.open(path)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode()
    except Exception:
        return ""


def _test_import(mod_name):
    try:
        result = subprocess.run(
            [sys.executable, "-c", f"import {mod_name}; print('ok')"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            return "loaded"
        else:
            return f"crashed: {result.stderr.strip()[:200]}"
    except subprocess.TimeoutExpired:
        return "timeout"
    except Exception as e:
        return f"error: {e}"


@app.get("/health")
def health_check():
    return {"status": "healthy", "app": "DOCVERIFY AI"}


@app.get("/debug")
def debug_check():
    results = {"status": "ok", "libraries": {}, "modules": {}, "env": {}}

    for lib in ["numpy", "PIL", "cv2", "fitz", "pytesseract", "reportlab", "pdfplumber", "pdf2image"]:
        results["libraries"][lib] = _test_import(lib)

    results["env"]["cwd"] = os.getcwd()
    results["env"]["python"] = sys.version
    results["env"]["api_dir"] = _api_dir
    results["env"]["api_dir_files"] = os.listdir(_api_dir)
    bin_path = os.path.join(_api_dir, "bin")
    results["env"]["bin_exists"] = os.path.exists(bin_path)
    if results["env"]["bin_exists"]:
        results["env"]["bin_size_mb"] = round(sum(os.path.getsize(os.path.join(dp, f)) for dp, dn, fn in os.walk(bin_path) for f in fn) / 1024 / 1024, 1)

    return results


@app.post("/analyze")
async def analyze_document(file: UploadFile = File(...)):
    session_id = str(uuid.uuid4())
    workdir = f"/tmp/{session_id}"
    os.makedirs(workdir, exist_ok=True)
    logger.info(f"Session {session_id}: analyzing '{file.filename}'")

    file_ext = os.path.splitext(file.filename)[1].lower()
    safe_ext = file_ext if file_ext in ['.pdf', '.png', '.jpg', '.jpeg', '.tiff', '.bmp'] else '.pdf'
    file_path = os.path.join(workdir, f"original{safe_ext}")

    try:
        content = await file.read()
        with open(file_path, "wb") as f:
            f.write(content)
    except Exception as e:
        shutil.rmtree(workdir, ignore_errors=True)
        raise HTTPException(status_code=400, detail=f"Failed to save file: {str(e)}")

    try:
        results = {"analyzed_pages": 0}
        findings = {"metadata": [], "ocr": [], "qr": [], "tampering": [], "signature": []}
        deductions = {}
        reasons = []

        # Preprocess
        pp = _test_import("modules.preprocessing")
        if pp != "loaded":
            shutil.rmtree(workdir, ignore_errors=True)
            raise HTTPException(status_code=400, detail=f"Preprocessing unavailable ({pp})")

        import importlib
        pre_mod = importlib.import_module("modules.preprocessing")
        pp_result = pre_mod.preprocess_document(file_path, output_dir=workdir)
        if not pp_result or not isinstance(pp_result, tuple) or not pp_result[0]:
            shutil.rmtree(workdir, ignore_errors=True)
            raise HTTPException(status_code=400, detail="Could not extract pages from document")

        images, cleaned_images = pp_result
        num_pages = len(images)
        image_pool = cleaned_images if cleaned_images else images
        results["analyzed_pages"] = num_pages
        logger.info(f"Session {session_id}: {num_pages} pages")

        # Metadata
        try:
            meta_mod = importlib.import_module("modules.metadata_analysis")
            meta_result = meta_mod.analyze_metadata(file_path)
        except Exception as e:
            meta_result = {"status": "error", "score": 0, "findings": [{"type": "error", "title": "Metadata unavailable", "detail": str(e), "points": 0, "severity": "high"}]}
        results["metadata"] = meta_result
        findings["metadata"] = meta_result.get("findings", [])

        all_ocr, all_qr, all_tampering, all_signature = [], [], [], []
        sig_details_all, sig_highlight_b64, ela_marked_b64 = [], [], []

        for page_idx, page_img in enumerate(image_pool):
            page_num = page_idx + 1

            # OCR
            try:
                ocr_mod = importlib.import_module("modules.ocr_analysis")
                ocr_r = ocr_mod.analyze_ocr(page_img)
            except Exception as e:
                ocr_r = {"status": "error", "score": 0, "findings": [{"type": "error", "title": "OCR unavailable", "detail": str(e), "points": 0, "severity": "high", "page": page_num}]}
            if ocr_r:
                for ff in ocr_r.get("findings", []):
                    ff["page"] = page_num
                all_ocr.append(ocr_r)

            # QR
            try:
                qr_mod = importlib.import_module("modules.qr_analysis")
                qr_r = qr_mod.analyze_qr_codes(page_img)
            except Exception as e:
                qr_r = {"status": "error", "score": 0, "findings": [{"type": "error", "title": "QR unavailable", "detail": str(e), "points": 0, "severity": "high", "page": page_num}]}
            if qr_r:
                for ff in qr_r.get("findings", []):
                    ff["page"] = page_num
                all_qr.append(qr_r)

            # Tampering
            try:
                tamper_mod = importlib.import_module("modules.tampering_detection")
                tr = tamper_mod.analyze_tampering(page_img, output_dir=workdir)
            except Exception as e:
                tr = {"status": "error", "score": 0, "findings": [{"type": "error", "title": "Tampering unavailable", "detail": str(e), "points": 0, "severity": "high", "page": page_num}]}
            if tr:
                for ff in tr.get("findings", []):
                    ff["page"] = page_num
                mp = tr.get("marked_image_path")
                if mp and os.path.exists(mp):
                    b64 = _img_to_b64(mp)
                    if b64:
                        ela_marked_b64.append({"page": page_num, "data": b64})
                all_tampering.append(tr)

            # Signatures
            try:
                sig_mod = importlib.import_module("modules.signature_analysis")
                sr = sig_mod.analyze_signatures(page_img, output_dir=workdir)
            except Exception as e:
                sr = {"status": "error", "score": 0, "findings": [{"type": "error", "title": "Signature unavailable", "detail": str(e), "points": 0, "severity": "high", "page": page_num}], "signatures_count": 0, "signature_details": []}
            if sr:
                for ff in sr.get("findings", []):
                    ff["page"] = page_num
                sh = sr.get("highlight_path")
                if sh and os.path.exists(sh):
                    b64 = _img_to_b64(sh)
                    if b64:
                        sig_highlight_b64.append({"page": page_num, "data": b64})
                sig_details_all.extend({**sd, "page": page_num} for sd in sr.get("signature_details", []))
                all_signature.append(sr)

        def worst_of(module_results, key="score"):
            scores = [r.get(key, 0) for r in module_results if r]
            return min(scores) if scores else 0

        def all_findings(module_results):
            merged = []
            for r in module_results:
                merged.extend(r.get("findings", []))
            return merged

        results["ocr"] = {
            "status": "error" if any(r.get("status") == "error" for r in all_ocr) else
                      "suspicious" if any(r.get("status") == "suspicious" for r in all_ocr) else "clean",
            "score": worst_of(all_ocr), "findings": all_findings(all_ocr),
        }
        results["qr"] = {
            "status": "error" if any(r.get("status") == "error" for r in all_qr) else
                      "suspicious" if any(r.get("status") == "suspicious" for r in all_qr) else "clean",
            "score": worst_of(all_qr), "findings": all_findings(all_qr),
        }
        results["tampering"] = {
            "status": "error" if any(r.get("status") == "error" for r in all_tampering) else
                      "tampered" if any(r.get("status") == "tampered" for r in all_tampering) else
                      "suspicious" if any(r.get("status") == "suspicious" for r in all_tampering) else "clean",
            "score": worst_of(all_tampering), "findings": all_findings(all_tampering),
        }
        results["signature"] = {
            "status": "error" if any(r.get("status") == "error" for r in all_signature) else
                      "no_signature" if all(r.get("status") == "no_signature" for r in all_signature) else
                      "suspicious" if any(r.get("status") == "suspicious" for r in all_signature) else "signature_detected",
            "score": worst_of(all_signature), "findings": all_findings(all_signature),
            "signatures_count": sum(r.get("signatures_count", 0) for r in all_signature),
            "signature_details": sig_details_all,
        }

        # Scoring
        try:
            score_mod = importlib.import_module("modules.scoring")
            score_result = score_mod.calculate_score(results)
        except Exception as e:
            score_result = {"score": 0, "status": "error", "reasons": [f"Scoring error: {e}"], "deductions": {}}
        results["scoring"] = score_result

        # Blockchain
        try:
            bc_mod = importlib.import_module("modules.blockchain")
            bc_result = bc_mod.create_blockchain_verification(file_path, results)
        except Exception as e:
            bc_result = {"blockchain_hash": "", "document_hash": "", "timestamp": "", "verification_url": "", "block_number": 0}
        results["blockchain"] = bc_result

        # Report
        report_path = os.path.join(workdir, "report.pdf")
        try:
            rpt_mod = importlib.import_module("modules.report_generator")
            rpt_mod.generate_pdf_report(results, report_path)
        except Exception:
            pass
        report_b64 = _img_to_b64(report_path) if os.path.exists(report_path) else ""

        preview_path = os.path.join(workdir, "page_0.png")
        preview_b64 = _img_to_b64(preview_path) if os.path.exists(preview_path) else ""

        frontend_result = {
            "session_id": session_id,
            "filename": file.filename,
            "results": {
                "analyzed_pages": num_pages,
                "score": results["scoring"].get("score", 0),
                "status": results["scoring"].get("status", "error"),
                "reasons": results["scoring"].get("reasons", []),
                "deductions": results["scoring"].get("deductions", {}),
                "metadata_status": results["metadata"].get("status", "error"),
                "ocr_status": results["ocr"]["status"],
                "qr_status": results["qr"]["status"],
                "tampering_status": results["tampering"]["status"],
                "signature_status": results["signature"]["status"],
                "signature_count": results["signature"].get("signatures_count", 0),
                "signature_details": results["signature"].get("signature_details", []),
                "findings": findings,
                "blockchain": results["blockchain"],
                "report_b64": report_b64,
                "marked_images": ela_marked_b64,
                "signature_images": sig_highlight_b64,
                "preview_b64": preview_b64,
            }
        }

        shutil.rmtree(workdir, ignore_errors=True)
        logger.info(f"Session {session_id}: complete")
        return JSONResponse(content=frontend_result)

    except HTTPException:
        shutil.rmtree(workdir, ignore_errors=True)
        raise
    except Exception as e:
        logger.error(f"Session {session_id}: Unhandled: {traceback.format_exc()}")
        shutil.rmtree(workdir, ignore_errors=True)
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")
