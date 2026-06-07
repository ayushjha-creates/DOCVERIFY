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

# ── Bootstrap tesseract path BEFORE any module imports ──
_api_dir = os.path.dirname(os.path.abspath(__file__))
_bin_dir = os.path.join(_api_dir, "bin")
_tess_bin = os.path.join(_bin_dir, "tesseract")
_tessdata = os.path.join(_bin_dir, "tessdata")
_lib_dir = os.path.join(_bin_dir, "lib")

if os.path.exists(_tess_bin):
    os.environ["TESSDATA_PREFIX"] = _tessdata
    _existing_ld = os.environ.get("LD_LIBRARY_PATH", "")
    os.environ["LD_LIBRARY_PATH"] = (
        f"{_lib_dir}:{_existing_ld}" if _existing_ld else _lib_dir
    )
    try:
        import pytesseract as _pt
        _pt.pytesseract.tesseract_cmd = _tess_bin
    except Exception:
        pass

sys.path.insert(0, _api_dir)

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

logging.basicConfig(level=logging.INFO, stream=sys.stdout)
logger = logging.getLogger("docverify")

def _import_module(module_name):
    try:
        return __import__(f"modules.{module_name}", fromlist=[module_name])
    except ImportError as e:
        logger.error(f"Failed to import modules.{module_name}: {e}")
        return None

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


def _img_to_b64_cv(path: str) -> str:
    try:
        from PIL import Image
        img = Image.open(path)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode()
    except Exception:
        return ""


@app.get("/api/health")
def health_check():
    return {"status": "healthy", "app": "DOCVERIFY AI"}


def _run_module(module_name, func_name, *args, **kwargs):
    mod = _import_module(module_name)
    if mod is None:
        error_msg = f"Module '{module_name}' could not be loaded — missing dependency"
        logger.error(error_msg)
        return {
            "status": "error",
            "score": 0,
            "findings": [{
                "type": "error",
                "title": f"{module_name} unavailable",
                "detail": error_msg,
                "points": 0,
                "severity": "high"
            }]
        }
    func = getattr(mod, func_name, None)
    if func is None:
        error_msg = f"Function '{func_name}' not found in module '{module_name}'"
        logger.error(error_msg)
        return {
            "status": "error",
            "score": 0,
            "findings": [{
                "type": "error",
                "title": f"{func_name} not found",
                "detail": error_msg,
                "points": 0,
                "severity": "high"
            }]
        }
    try:
        logger.info(f"Running {module_name}.{func_name}...")
        result = func(*args, **kwargs)
        logger.info(f"{module_name}.{func_name} completed")
        return result
    except Exception as e:
        tb = traceback.format_exc()
        logger.error(f"Error in {module_name}.{func_name}: {e}\n{tb}")
        return {
            "status": "error",
            "score": 0,
            "findings": [{
                "type": "error",
                "title": f"{module_name} failed",
                "detail": f"{func_name} error: {str(e)}",
                "points": 0,
                "severity": "high"
            }]
        }


@app.post("/api/analyze")
async def analyze_document(file: UploadFile = File(...)):
    session_id = str(uuid.uuid4())
    workdir = f"/tmp/{session_id}"
    os.makedirs(workdir, exist_ok=True)
    logger.info(f"Session {session_id}: analyzing file '{file.filename}'")

    file_ext = os.path.splitext(file.filename)[1].lower()
    safe_ext = file_ext if file_ext in ['.pdf', '.png', '.jpg', '.jpeg', '.tiff', '.bmp'] else '.pdf'
    file_path = os.path.join(workdir, f"original{safe_ext}")

    try:
        content = await file.read()
        with open(file_path, "wb") as f:
            f.write(content)
        logger.info(f"Session {session_id}: saved file to {file_path} ({len(content)} bytes)")
    except Exception as e:
        shutil.rmtree(workdir, ignore_errors=True)
        raise HTTPException(status_code=400, detail=f"Failed to save uploaded file: {str(e)}")

    try:
        preprocess_result = _run_module("preprocessing", "preprocess_document", file_path, output_dir=workdir)
        if preprocess_result is None or preprocess_result.get("status") == "error":
            shutil.rmtree(workdir, ignore_errors=True)
            detail = "Could not process document"
            if preprocess_result and preprocess_result.get("findings"):
                detail = preprocess_result["findings"][0].get("detail", detail)
            raise HTTPException(status_code=400, detail=detail)

        if isinstance(preprocess_result, tuple):
            images, cleaned_images = preprocess_result
        else:
            raise HTTPException(status_code=500, detail="Preprocessing returned unexpected result")

        if not images:
            raise HTTPException(status_code=400, detail="Could not extract any pages from the document")

        num_pages = len(images)
        image_pool = cleaned_images if cleaned_images else images
        logger.info(f"Session {session_id}: {num_pages} pages to analyze")

        results = {}
        results["metadata"] = _run_module("metadata_analysis", "analyze_metadata", file_path)

        all_ocr = []
        all_qr = []
        all_tampering = []
        all_signature = []
        sig_details_all = []
        sig_highlight_b64 = []
        ela_marked_b64 = []

        for page_idx, page_img in enumerate(image_pool):
            page_num = page_idx + 1
            logger.info(f"Session {session_id}: analyzing page {page_num}/{num_pages}")

            ocr_result = _run_module("ocr_analysis", "analyze_ocr", page_img)
            if ocr_result:
                for ff in ocr_result.get("findings", []):
                    ff["page"] = page_num
                all_ocr.append(ocr_result)
            else:
                all_ocr.append({"status": "error", "score": 0, "findings": [{"type": "error", "title": "OCR unavailable", "detail": "OCR module returned no result", "points": 0, "severity": "high", "page": page_num}]})

            qr_result = _run_module("qr_analysis", "analyze_qr_codes", page_img)
            if qr_result:
                for ff in qr_result.get("findings", []):
                    ff["page"] = page_num
                all_qr.append(qr_result)
            else:
                all_qr.append({"status": "error", "score": 0, "findings": []})

            tamper_result = _run_module("tampering_detection", "analyze_tampering", page_img, output_dir=workdir)
            if tamper_result:
                for ff in tamper_result.get("findings", []):
                    ff["page"] = page_num
                marked_path = tamper_result.get("marked_image_path")
                if marked_path and os.path.exists(marked_path):
                    b64 = _img_to_b64(marked_path)
                    if b64:
                        ela_marked_b64.append({"page": page_num, "data": b64})
                all_tampering.append(tamper_result)
            else:
                all_tampering.append({"status": "error", "score": 0, "findings": [{"type": "error", "title": "Tampering detection unavailable", "detail": "Tampering module returned no result", "points": 0, "severity": "high", "page": page_num}]})

            sig_result = _run_module("signature_analysis", "analyze_signatures", page_img, output_dir=workdir)
            if sig_result:
                for ff in sig_result.get("findings", []):
                    ff["page"] = page_num
                sig_hl = sig_result.get("highlight_path")
                if sig_hl and os.path.exists(sig_hl):
                    b64 = _img_to_b64(sig_hl)
                    if b64:
                        sig_highlight_b64.append({"page": page_num, "data": b64})
                sig_details_all.extend(
                    {**sd, "page": page_num} for sd in sig_result.get("signature_details", [])
                )
                all_signature.append(sig_result)
            else:
                all_signature.append({"status": "error", "score": 0, "findings": [], "signatures_count": 0, "signature_details": []})

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
            "score": worst_of(all_ocr),
            "findings": all_findings(all_ocr),
        }
        results["qr"] = {
            "status": "error" if any(r.get("status") == "error" for r in all_qr) else
                      "suspicious" if any(r.get("status") == "suspicious" for r in all_qr) else "clean",
            "score": worst_of(all_qr),
            "findings": all_findings(all_qr),
        }
        results["tampering"] = {
            "status": "error" if any(r.get("status") == "error" for r in all_tampering) else
                      "tampered" if any(r.get("status") == "tampered" for r in all_tampering) else
                      "suspicious" if any(r.get("status") == "suspicious" for r in all_tampering) else "clean",
            "score": worst_of(all_tampering),
            "findings": all_findings(all_tampering),
        }
        results["signature"] = {
            "status": "error" if any(r.get("status") == "error" for r in all_signature) else
                      "no_signature" if all(r.get("status") == "no_signature" for r in all_signature) else
                      "suspicious" if any(r.get("status") == "suspicious" for r in all_signature) else
                      "signature_detected",
            "score": worst_of(all_signature),
            "findings": all_findings(all_signature),
            "signatures_count": sum(r.get("signatures_count", 0) for r in all_signature),
            "signature_details": sig_details_all,
        }

        results["analyzed_pages"] = num_pages
        results["scoring"] = _run_module("scoring", "calculate_score", results)
        results["blockchain"] = _run_module("blockchain", "create_blockchain_verification", file_path, results)

        report_path = os.path.join(workdir, "report.pdf")
        _run_module("report_generator", "generate_pdf_report", results, report_path)
        report_b64 = _img_to_b64(report_path) if os.path.exists(report_path) else ""

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
                "preview_b64": "",
            }
        }

        preview_path = os.path.join(workdir, "page_0.png")
        if os.path.exists(preview_path):
            frontend_result["results"]["preview_b64"] = _img_to_b64(preview_path)

        shutil.rmtree(workdir, ignore_errors=True)
        logger.info(f"Session {session_id}: analysis complete")
        return JSONResponse(content=frontend_result)

    except HTTPException:
        shutil.rmtree(workdir, ignore_errors=True)
        raise
    except Exception as e:
        tb = traceback.format_exc()
        logger.error(f"Session {session_id}: Unhandled error: {e}\n{tb}")
        shutil.rmtree(workdir, ignore_errors=True)
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")
