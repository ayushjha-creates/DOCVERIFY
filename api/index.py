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

SAMPLE_DIR = os.path.join(_api_dir, "sample")
os.makedirs(SAMPLE_DIR, exist_ok=True)


def _img_to_b64(path: str) -> str:
    try:
        from PIL import Image
        img = Image.open(path)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode()
    except Exception:
        return ""


def _import_module(module_name):
    try:
        return __import__(f"modules.{module_name}", fromlist=[module_name])
    except Exception as e:
        logger.error(f"Failed to import modules.{module_name}: {traceback.format_exc()}")
        return None


@app.get("/health")
def health_check():
    return {"status": "healthy", "app": "DOCVERIFY AI"}


@app.get("/debug")
def debug_check():
    results = {"status": "ok", "modules": {}, "libraries": {}, "env": {}}
    for name in [
        "preprocessing", "metadata_analysis", "ocr_analysis", "qr_analysis",
        "tampering_detection", "signature_analysis", "scoring", "blockchain",
        "report_generator"
    ]:
        mod = _import_module(name)
        results["modules"][name] = "loaded" if mod is not None else "failed"
    for lib_name, lib_import in [
        ("cv2", "cv2"), ("pytesseract", "pytesseract"), ("fitz (PyMuPDF)", "fitz"),
        ("PIL", "PIL"), ("numpy", "numpy"), ("reportlab", "reportlab"),
        ("pdfplumber", "pdfplumber"),
    ]:
        try:
            __import__(lib_import)
            results["libraries"][lib_name] = "loaded"
        except Exception as e:
            results["libraries"][lib_name] = f"failed: {e}"
    results["env"]["cwd"] = os.getcwd()
    results["env"]["python"] = sys.version
    results["env"]["api_dir"] = _api_dir
    results["env"]["api_dir_files"] = os.listdir(_api_dir)
    bin_path = os.path.join(_api_dir, "bin")
    results["env"]["bin_exists"] = os.path.exists(bin_path)
    return results


def _run_module(module_name, func_name, *args, **kwargs):
    mod = _import_module(module_name)
    if mod is None:
        return {"status": "error", "score": 0, "findings": [{"type": "error", "title": f"{module_name} unavailable", "detail": f"Module '{module_name}' could not be loaded", "points": 0, "severity": "high"}]}
    func = getattr(mod, func_name, None)
    if func is None:
        return {"status": "error", "score": 0, "findings": [{"type": "error", "title": f"{func_name} not found", "detail": f"Function '{func_name}' not found in '{module_name}'", "points": 0, "severity": "high"}]}
    try:
        logger.info(f"Running {module_name}.{func_name}...")
        result = func(*args, **kwargs)
        logger.info(f"{module_name}.{func_name} completed")
        return result
    except Exception as e:
        logger.error(f"Error in {module_name}.{func_name}: {traceback.format_exc()}")
        return {"status": "error", "score": 0, "findings": [{"type": "error", "title": f"{module_name} failed", "detail": f"{func_name} error: {str(e)}", "points": 0, "severity": "high"}]}


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
        pp_result = _run_module("preprocessing", "preprocess_document", file_path, output_dir=workdir)
        if pp_result is None or pp_result.get("status") == "error":
            shutil.rmtree(workdir, ignore_errors=True)
            raise HTTPException(status_code=400, detail=(pp_result["findings"][0]["detail"] if pp_result and pp_result.get("findings") else "Could not process document"))

        if not isinstance(pp_result, tuple) or not pp_result[0]:
            shutil.rmtree(workdir, ignore_errors=True)
            raise HTTPException(status_code=400, detail="Could not extract any pages from the document")

        images, cleaned_images = pp_result
        num_pages = len(images)
        image_pool = cleaned_images if cleaned_images else images
        logger.info(f"Session {session_id}: {num_pages} pages")

        results = {}
        results["metadata"] = _run_module("metadata_analysis", "analyze_metadata", file_path) or {"status": "error", "score": 0, "findings": []}

        all_ocr, all_qr, all_tampering, all_signature = [], [], [], []
        sig_details_all, sig_highlight_b64, ela_marked_b64 = [], [], []

        for page_idx, page_img in enumerate(image_pool):
            page_num = page_idx + 1

            for mod_name, func_name, collector in [
                ("ocr_analysis", "analyze_ocr", all_ocr),
                ("qr_analysis", "analyze_qr_codes", all_qr),
            ]:
                result = _run_module(mod_name, func_name, page_img)
                if result:
                    for ff in result.get("findings", []):
                        ff["page"] = page_num
                    collector.append(result)

            tr = _run_module("tampering_detection", "analyze_tampering", page_img, output_dir=workdir)
            if tr:
                for ff in tr.get("findings", []):
                    ff["page"] = page_num
                mp = tr.get("marked_image_path")
                if mp and os.path.exists(mp):
                    b64 = _img_to_b64(mp)
                    if b64:
                        ela_marked_b64.append({"page": page_num, "data": b64})
                all_tampering.append(tr)

            sr = _run_module("signature_analysis", "analyze_signatures", page_img, output_dir=workdir)
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

        results["analyzed_pages"] = num_pages
        results["scoring"] = _run_module("scoring", "calculate_score", results) or {"score": 0, "status": "error", "reasons": ["Scoring unavailable"], "deductions": {}}
        results["blockchain"] = _run_module("blockchain", "create_blockchain_verification", file_path, results) or {}

        report_path = os.path.join(workdir, "report.pdf")
        _run_module("report_generator", "generate_pdf_report", results, report_path)
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
                "findings": {
                    "metadata": results["metadata"].get("findings", []),
                    "ocr": results["ocr"]["findings"],
                    "qr": results["qr"]["findings"],
                    "tampering": results["tampering"]["findings"],
                    "signature": results["signature"]["findings"],
                },
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
