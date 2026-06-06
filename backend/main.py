import os
import sys
import json
import shutil
import uuid
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from modules.preprocessing import preprocess_document, get_image_preview
from modules.metadata_analysis import analyze_metadata
from modules.ocr_analysis import analyze_ocr
from modules.qr_analysis import analyze_qr_codes
from modules.tampering_detection import analyze_tampering
from modules.signature_analysis import analyze_signatures
from modules.scoring import calculate_score
from modules.blockchain import create_blockchain_verification
from modules.report_generator import generate_pdf_report

app = FastAPI(title="DOCVERIFY AI API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMP_DIR = os.path.join(BASE_DIR, "temp")
REPORTS_DIR = os.path.join(BASE_DIR, "reports")
SAMPLE_DIR = os.path.join(BASE_DIR, "sample")
os.makedirs(TEMP_DIR, exist_ok=True)
os.makedirs(REPORTS_DIR, exist_ok=True)
os.makedirs(SAMPLE_DIR, exist_ok=True)

@app.get("/api/health")
def health_check():
    return {"status": "healthy", "app": "DOCVERIFY AI"}

@app.post("/api/analyze")
async def analyze_document(file: UploadFile = File(...)):
    session_id = str(uuid.uuid4())
    session_dir = os.path.join(TEMP_DIR, session_id)
    os.makedirs(session_dir, exist_ok=True)

    file_ext = os.path.splitext(file.filename)[1].lower()
    safe_ext = file_ext if file_ext in ['.pdf', '.png', '.jpg', '.jpeg', '.tiff', '.bmp'] else '.pdf'
    file_path = os.path.join(session_dir, f"original{safe_ext}")

    with open(file_path, "wb") as f:
        content = await file.read()
        f.write(content)

    try:
        progress = {"status": "preprocessing", "progress": 10, "message": "Preprocessing document..."}
        images, cleaned_images = preprocess_document(file_path, output_dir=session_dir)
        if not images:
            raise HTTPException(status_code=400, detail="Could not process document")

        num_pages = len(images)
        image_pool = cleaned_images if cleaned_images else images

        preview_path = get_image_preview(image_pool[0])
        session_preview = os.path.join(session_dir, "preview.png")
        if os.path.exists(preview_path):
            shutil.copy2(preview_path, session_preview)

        results = {}

        # ── Metadata (document-level, run once) ──
        progress = {"status": "metadata", "progress": 15, "message": "Analyzing metadata..."}
        results["metadata"] = analyze_metadata(file_path)

        # ── Per-page analysis ──
        all_ocr = []
        all_qr = []
        all_tampering = []
        all_signature = []
        sig_details_all = []
        sig_highlight_urls = []
        ela_marked_urls = []

        for page_idx, page_img in enumerate(image_pool):
            page_num = page_idx + 1
            prefix = f"Page {page_num}: "

            progress = {"status": "ocr", "progress": 20 + int(page_idx * 50 / num_pages),
                        "message": f"Running OCR on page {page_num}/{num_pages}..."}
            ocr_result = analyze_ocr(page_img)
            for f in ocr_result.get("findings", []):
                f["page"] = page_num
            all_ocr.append(ocr_result)

            progress = {"status": "qr", "progress": 25 + int(page_idx * 50 / num_pages),
                        "message": f"Verifying QR codes on page {page_num}/{num_pages}..."}
            qr_result = analyze_qr_codes(page_img)
            for f in qr_result.get("findings", []):
                f["page"] = page_num
            all_qr.append(qr_result)

            progress = {"status": "tampering", "progress": 30 + int(page_idx * 50 / num_pages),
                        "message": f"Detecting tampering on page {page_num}/{num_pages}..."}
            tamper_result = analyze_tampering(page_img, output_dir=session_dir)
            for f in tamper_result.get("findings", []):
                f["page"] = page_num
            marked_path = tamper_result.get("marked_image_path")
            if marked_path and os.path.exists(marked_path):
                old_name = os.path.basename(marked_path)
                new_name = f"ela_overlay_p{page_num}.png"
                new_path = os.path.join(session_dir, new_name)
                if os.path.exists(marked_path) and old_name == "ela_overlay.png":
                    os.rename(marked_path, new_path)
                    tamper_result["marked_image_path"] = new_path
                ela_marked_urls.append({
                    "page": page_num,
                    "url": f"/api/temp/{session_id}/{new_name}"
                })
            all_tampering.append(tamper_result)

            progress = {"status": "signature", "progress": 35 + int(page_idx * 50 / num_pages),
                        "message": f"Analyzing signatures on page {page_num}/{num_pages}..."}
            sig_result = analyze_signatures(page_img, output_dir=session_dir)
            for f in sig_result.get("findings", []):
                f["page"] = page_num
            sig_hl = sig_result.get("highlight_path")
            if sig_hl and os.path.exists(sig_hl):
                old_name = os.path.basename(sig_hl)
                new_name = f"signature_overlay_p{page_num}.png"
                new_path = os.path.join(session_dir, new_name)
                if old_name == "signature_overlay.png":
                    os.rename(sig_hl, new_path)
                    sig_result["highlight_path"] = new_path
                sig_highlight_urls.append({
                    "page": page_num,
                    "url": f"/api/temp/{session_id}/{new_name}"
                })
            sig_details_all.extend(
                {**sd, "page": page_num} for sd in sig_result.get("signature_details", [])
            )
            all_signature.append(sig_result)

        # ── Aggregate results ──
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
        if ela_marked_urls:
            results["tampering"]["marked_image_urls"] = ela_marked_urls
            results["tampering"]["marked_image_url"] = ela_marked_urls[0]["url"]

        results["signature"] = {
            "status": "no_signature" if all(r.get("status") == "no_signature" for r in all_signature) else
                      "suspicious" if any(r.get("status") == "suspicious" for r in all_signature) else
                      "signature_detected",
            "score": worst_of(all_signature),
            "findings": all_findings(all_signature),
            "signatures_count": sum(r.get("signatures_count", 0) for r in all_signature),
            "signature_details": sig_details_all,
        }
        if sig_highlight_urls:
            results["signature"]["highlight_urls"] = sig_highlight_urls
            results["signature"]["highlight_url"] = sig_highlight_urls[0]["url"]

        results["analyzed_pages"] = num_pages

        progress = {"status": "scoring", "progress": 90, "message": "Calculating authenticity score..."}
        results["scoring"] = calculate_score(results)

        progress = {"status": "blockchain", "progress": 95, "message": "Generating blockchain verification..."}
        results["blockchain"] = create_blockchain_verification(file_path, results)

        progress = {"status": "complete", "progress": 100, "message": "Analysis complete!"}

        report_path = os.path.join(REPORTS_DIR, f"report_{session_id}.pdf")
        generate_pdf_report(results, report_path)
        results["report_url"] = f"/api/report/{session_id}"

        frontend_result = {
            "session_id": session_id,
            "filename": file.filename,
            "file_preview_url": f"/api/temp/{session_id}/preview.png",
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
                "report_url": results["report_url"],
                "marked_image_urls": results.get("tampering", {}).get("marked_image_urls", []),
                "marked_image_url": results.get("tampering", {}).get("marked_image_url"),
                "signature_image_urls": results.get("signature", {}).get("highlight_urls", []),
                "signature_image_url": results.get("signature", {}).get("highlight_url"),
            }
        }

        return JSONResponse(content=frontend_result)

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")

@app.get("/api/temp/{session_id}/preview.png")
def get_preview(session_id: str):
    preview_path = os.path.join(TEMP_DIR, session_id, "preview.png")
    if os.path.exists(preview_path):
        return FileResponse(preview_path, media_type="image/png")
    fallback = os.path.join(TEMP_DIR, session_id, "page_0_preview.png")
    if os.path.exists(fallback):
        return FileResponse(fallback, media_type="image/png")
    return JSONResponse({"error": "Preview not found"}, status_code=404)

@app.get("/api/temp/{session_id}/{filename}")
def get_temp_file(session_id: str, filename: str):
    file_path = os.path.join(TEMP_DIR, session_id, filename)
    if os.path.exists(file_path):
        return FileResponse(file_path, media_type="image/png")
    return JSONResponse({"error": "File not found"}, status_code=404)

@app.get("/api/report/{session_id}")
def get_report(session_id: str):
    report_path = os.path.join(REPORTS_DIR, f"report_{session_id}.pdf")
    if os.path.exists(report_path):
        return FileResponse(
            report_path,
            media_type="application/pdf",
            filename=f"DOCVERIFY_Report_{session_id[:8]}.pdf"
        )
    return JSONResponse({"error": "Report not found"}, status_code=404)

@app.post("/api/sample")
async def analyze_sample():
    sample_files = [f for f in os.listdir(SAMPLE_DIR) if f.lower().endswith(('.pdf', '.png', '.jpg', '.jpeg'))]
    if sample_files:
        sample_path = os.path.join(SAMPLE_DIR, sample_files[0])
        class FakeFile:
            def __init__(self, path, name):
                self.path = path
                self.filename = name
            async def read(self):
                with open(self.path, "rb") as f:
                    return f.read()
        fake = FakeFile(sample_path, sample_files[0])
        return await analyze_document(fake)
    return JSONResponse({"error": "No sample document found. Upload a sample.pdf to the sample folder."}, status_code=404)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
