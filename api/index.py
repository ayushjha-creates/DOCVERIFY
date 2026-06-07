import os
import sys
import json
import uuid
import base64
import io
import traceback
import shutil
import datetime

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
    import pytesseract as _pt
    _pt.pytesseract.tesseract_cmd = _tess_bin

sys.path.insert(0, _api_dir)

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from modules.preprocessing import preprocess_document
from modules.metadata_analysis import analyze_metadata
from modules.ocr_analysis import analyze_ocr
from modules.qr_analysis import analyze_qr_codes
from modules.tampering_detection import analyze_tampering
from modules.signature_analysis import analyze_signatures
from modules.scoring import calculate_score
from modules.blockchain import create_blockchain_verification
from modules.report_generator import generate_pdf_report

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


@app.post("/api/analyze")
async def analyze_document(file: UploadFile = File(...)):
    session_id = str(uuid.uuid4())
    workdir = f"/tmp/{session_id}"
    os.makedirs(workdir, exist_ok=True)

    file_ext = os.path.splitext(file.filename)[1].lower()
    safe_ext = file_ext if file_ext in ['.pdf', '.png', '.jpg', '.jpeg', '.tiff', '.bmp'] else '.pdf'
    file_path = os.path.join(workdir, f"original{safe_ext}")

    with open(file_path, "wb") as f:
        content = await file.read()
        f.write(content)

    try:
        images, cleaned_images = preprocess_document(file_path, output_dir=workdir)
        if not images:
            raise HTTPException(status_code=400, detail="Could not process document")

        num_pages = len(images)
        image_pool = cleaned_images if cleaned_images else images

        results = {}

        results["metadata"] = analyze_metadata(file_path)

        all_ocr = []
        all_qr = []
        all_tampering = []
        all_signature = []
        sig_details_all = []
        sig_highlight_b64 = []
        ela_marked_b64 = []

        for page_idx, page_img in enumerate(image_pool):
            page_num = page_idx + 1

            ocr_result = analyze_ocr(page_img)
            for f in ocr_result.get("findings", []):
                f["page"] = page_num
            all_ocr.append(ocr_result)

            qr_result = analyze_qr_codes(page_img)
            for f in qr_result.get("findings", []):
                f["page"] = page_num
            all_qr.append(qr_result)

            tamper_result = analyze_tampering(page_img, output_dir=workdir)
            for f in tamper_result.get("findings", []):
                f["page"] = page_num
            marked_path = tamper_result.get("marked_image_path")
            if marked_path and os.path.exists(marked_path):
                b64 = _img_to_b64(marked_path)
                if b64:
                    ela_marked_b64.append({"page": page_num, "data": b64})

            sig_result = analyze_signatures(page_img, output_dir=workdir)
            for f in sig_result.get("findings", []):
                f["page"] = page_num
            sig_hl = sig_result.get("highlight_path")
            if sig_hl and os.path.exists(sig_hl):
                b64 = _img_to_b64(sig_hl)
                if b64:
                    sig_highlight_b64.append({"page": page_num, "data": b64})
            sig_details_all.extend(
                {**sd, "page": page_num} for sd in sig_result.get("signature_details", [])
            )
            all_signature.append(sig_result)

        def worst_of(module_results, key="score"):
            scores = [r.get(key, 0) for r in module_results if r]
            return min(scores) if scores else 0

        def all_findings(module_results):
            merged = []
            for r in module_results:
                merged.extend(r.get("findings", []))
            return merged

        results["ocr"] = {
            "status": "suspicious" if any(r.get("status") == "suspicious" for r in all_ocr) else "clean",
            "score": worst_of(all_ocr),
            "findings": all_findings(all_ocr),
        }
        results["qr"] = {
            "status": "suspicious" if any(r.get("status") == "suspicious" for r in all_qr) else "clean",
            "score": worst_of(all_qr),
            "findings": all_findings(all_qr),
        }
        results["tampering"] = {
            "status": "tampered" if any(r.get("status") == "tampered" for r in all_tampering) else
                      "suspicious" if any(r.get("status") == "suspicious" for r in all_tampering) else "clean",
            "score": worst_of(all_tampering),
            "findings": all_findings(all_tampering),
        }
        results["signature"] = {
            "status": "no_signature" if all(r.get("status") == "no_signature" for r in all_signature) else
                      "suspicious" if any(r.get("status") == "suspicious" for r in all_signature) else
                      "signature_detected",
            "score": worst_of(all_signature),
            "findings": all_findings(all_signature),
            "signatures_count": sum(r.get("signatures_count", 0) for r in all_signature),
            "signature_details": sig_details_all,
        }

        results["analyzed_pages"] = num_pages
        results["scoring"] = calculate_score(results)
        results["blockchain"] = create_blockchain_verification(file_path, results)

        report_path = os.path.join(workdir, "report.pdf")
        generate_pdf_report(results, report_path)
        report_b64 = _img_to_b64(report_path) if os.path.exists(report_path) else ""

        frontend_result = {
            "session_id": session_id,
            "filename": file.filename,
            "results": {
                "analyzed_pages": num_pages,
                "score": results["scoring"]["score"],
                "status": results["scoring"]["status"],
                "reasons": results["scoring"]["reasons"],
                "deductions": results["scoring"]["deductions"],
                "metadata_status": results["metadata"]["status"],
                "ocr_status": results["ocr"]["status"],
                "qr_status": results["qr"]["status"],
                "tampering_status": results["tampering"]["status"],
                "signature_status": results["signature"]["status"],
                "signature_count": results["signature"].get("signatures_count", 0),
                "signature_details": results["signature"].get("signature_details", []),
                "findings": {
                    "metadata": results["metadata"]["findings"],
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
        return JSONResponse(content=frontend_result)

    except Exception as e:
        shutil.rmtree(workdir, ignore_errors=True)
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")
