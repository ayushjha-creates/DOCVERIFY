import os
import sys
import json
import uuid
import base64
import io
import traceback
import shutil
import datetime
import time
import logging
import subprocess

_api_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _api_dir)

# ── Auto-install missing packages at cold start ──
def _ensure_deps():
    _t0 = time.monotonic()
    _MAX_TOTAL = 8.0
    req_file = os.path.join(_api_dir, "requirements.txt")
    if not os.path.exists(req_file):
        return
    missing = []
    critical = ["fitz", "PIL", "numpy", "cv2", "reportlab", "pytesseract"]
    for mod in critical:
        try:
            __import__(mod)
        except ImportError:
            missing.append(mod)
    if not missing:
        return
    if time.monotonic() - _t0 > _MAX_TOTAL:
        return

    target_dir = "/tmp/docverify_packages"
    os.makedirs(target_dir, exist_ok=True)
    if target_dir not in sys.path:
        sys.path.insert(0, target_dir)
    os.environ.setdefault("PYTHONPATH", "")
    if target_dir not in os.environ["PYTHONPATH"]:
        os.environ["PYTHONPATH"] = f"{target_dir}:{os.environ['PYTHONPATH']}"
    print(f"[deps] Missing: {missing}. Installing to {target_dir}...", flush=True)

    install_ok = False

    # Try uv first
    if time.monotonic() - _t0 < _MAX_TOTAL:
        uv_path = os.path.join(_api_dir, "_uv")
        if os.path.isdir(uv_path):
            uv_bin = None
            for root, dirs, files in os.walk(uv_path):
                for f in files:
                    if f == "uv":
                        uv_bin = os.path.join(root, f)
                        break
            if uv_bin and os.path.isfile(uv_bin):
                remaining = max(1, int(_MAX_TOTAL - (time.monotonic() - _t0)))
                try:
                    r = subprocess.run(
                        [uv_bin, "pip", "install", "--target", target_dir, "-r", req_file],
                        capture_output=True, text=True, timeout=remaining
                    )
                    if r.returncode == 0:
                        print(f"[deps] uv install OK", flush=True)
                        install_ok = True
                    else:
                        print(f"[deps] uv failed: {r.stderr[-200:]}", flush=True)
                except subprocess.TimeoutExpired:
                    print(f"[deps] uv install timed out", flush=True)
                except Exception as e:
                    print(f"[deps] uv error: {e}", flush=True)

    # Fallback: pip
    if not install_ok and time.monotonic() - _t0 < _MAX_TOTAL:
        remaining = max(1, int(_MAX_TOTAL - (time.monotonic() - _t0)))
        try:
            r = subprocess.run(
                [sys.executable, "-m", "pip", "install", "--target", target_dir,
                 "-r", req_file],
                capture_output=True, text=True, timeout=remaining
            )
            if r.returncode == 0:
                print(f"[deps] pip install OK", flush=True)
                install_ok = True
            else:
                print(f"[deps] pip failed: {r.stderr[-200:]}", flush=True)
        except subprocess.TimeoutExpired:
            print(f"[deps] pip install timed out", flush=True)
        except Exception as e:
            print(f"[deps] pip error: {e}", flush=True)

    if install_ok:
        import importlib
        for mod in missing:
            try:
                importlib.import_module(mod)
                print(f"[deps] {mod} now available", flush=True)
            except Exception as e:
                print(f"[deps] {mod} still failing: {e}", flush=True)

_ensure_deps()

# ── Ensure bundled tesseract binary is executable (Vercel FS may be read-only) ──
try:
    _tess_bin = os.path.join(_api_dir, "bin", "tesseract")
    if os.path.exists(_tess_bin):
        os.chmod(_tess_bin, 0o755)
        _lib_dir = os.path.join(_api_dir, "bin", "lib")
        if os.path.isdir(_lib_dir):
            for f in os.listdir(_lib_dir):
                fp = os.path.join(_lib_dir, f)
                if os.path.isfile(fp) and (f.endswith(".so") or ".so." in f):
                    os.chmod(fp, 0o755)
except OSError:
    pass  # read-only FS on Vercel

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
        if path.lower().endswith(".pdf"):
            with open(path, "rb") as f:
                return base64.b64encode(f.read()).decode()
        from PIL import Image
        img = Image.open(path)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode()
    except Exception:
        return ""


def _test_import(mod_name):
    try:
        import importlib
        importlib.import_module(mod_name)
        return "loaded"
    except Exception as e:
        return f"crashed: {e}"


@app.get("/health")
def health_check():
    return {"status": "healthy", "app": "DOCVERIFY AI"}


@app.get("/debug")
def debug_check():
    results = {"status": "ok", "libraries": {}, "modules": {}, "env": {}}

    for lib in ["numpy", "PIL", "cv2", "fitz", "pytesseract", "reportlab", "pdfplumber", "pdf2image", "fastapi", "pyzbar"]:
        results["libraries"][lib] = _test_import(lib)

    # Also test in-process imports
    results["imports_in_process"] = {}
    for lib in ["numpy", "PIL", "cv2", "fitz", "pytesseract", "reportlab", "pyzbar"]:
        try:
            mod = __import__(lib)
            ver = getattr(mod, "__version__", "unknown")
            results["imports_in_process"][lib] = f"ok (v{ver})"
        except Exception as e:
            results["imports_in_process"][lib] = f"error: {e}"

    results["env"]["cwd"] = os.getcwd()
    results["env"]["python"] = sys.version
    results["env"]["api_dir"] = _api_dir
    results["env"]["api_dir_files"] = os.listdir(_api_dir)
    vendor_path = os.path.join(_api_dir, "_vendor")
    if os.path.exists(vendor_path):
        results["env"]["vendor_contents"] = os.listdir(vendor_path)[:50]
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
        MAX_PAGES = 3
        if num_pages > MAX_PAGES:
            image_pool = image_pool[:MAX_PAGES]
            num_pages = MAX_PAGES
            logger.info(f"Session {session_id}: truncated to {MAX_PAGES} pages (had {len(images)})")
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
                qr_r = qr_mod.analyse_qr(page_img)
            except Exception as e:
                qr_r = {"status": "FAIL", "deduction": 30, "qr_count": 0, "details": f"QR analysis error: {e}", "individual_results": [], "flags": []}
            if qr_r:
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

        def _worst_engine_status(results_list):
            if not results_list:
                return "OK"
            for r in results_list:
                s = r.get("status", "")
                if s in ("tampered", "fail", "error"):
                    return "FAIL"
            for r in results_list:
                s = r.get("status", "")
                if s in ("suspicious", "warn"):
                    return "WARN"
            return "OK"

        # ── Build normalized engine_results for scoring ──
        engine_results = {}

        meta_score = meta_result.get("score", 0) if meta_result else 0
        engine_results["metadata"] = {
            "status": meta_result.get("status", "OK"),
            "deduction": min(abs(meta_score), 20) if meta_score < 0 else 0,
        }

        ocr_agg_status = _worst_engine_status(all_ocr)
        ocr_agg_score = worst_of(all_ocr)
        engine_results["ocr"] = {
            "status": ocr_agg_status,
            "deduction": min(abs(ocr_agg_score), 20) if ocr_agg_score < 0 else 0,
        }

        qr_agg_status = "OK"
        qr_agg_deduct = 0
        all_qr_details = []
        if all_qr:
            status_rank = {"OK": 0, "WARN": 1, "FAIL": 2}
            worst = max(all_qr, key=lambda r: status_rank.get(r.get("status", "OK"), 0))
            qr_agg_status = worst.get("status", "OK")
            qr_agg_deduct = max(r.get("deduction", 0) for r in all_qr)
            for r in all_qr:
                all_qr_details.extend(r.get("individual_results", []))
        engine_results["qr"] = {"status": qr_agg_status, "deduction": qr_agg_deduct}
        qr_dbg = {}
        if all_qr:
            for r in all_qr:
                if r.get("_dbg"):
                    qr_dbg = r["_dbg"]

        tamper_agg_status = _worst_engine_status(all_tampering)
        tamper_agg_score = worst_of(all_tampering)
        engine_results["tamper"] = {
            "status": tamper_agg_status,
            "deduction": min(abs(tamper_agg_score), 35) if tamper_agg_score < 0 else 0,
        }

        sig_agg_status = _worst_engine_status(all_signature)
        sig_agg_score = worst_of(all_signature)
        if sig_agg_status == "OK" and all(r.get("status") == "no_signature" for r in all_signature):
            sig_agg_status = "OK"
        engine_results["signature"] = {
            "status": sig_agg_status,
            "deduction": min(abs(sig_agg_score), 15) if sig_agg_score < 0 else 0,
        }

        has_duplicate = any("DUPLICATE_QR_DATA" in r.get("flags", []) for r in all_qr)

        findings["ocr"] = all_findings(all_ocr)
        findings["tampering"] = all_findings(all_tampering)
        findings["signature"] = all_findings(all_signature)

        # Scoring
        try:
            score_mod = importlib.import_module("modules.scoring")
            score_result = score_mod.calculate_final_score(engine_results, has_duplicate)
        except Exception as e:
            print(f"[scoring] Error: {e}", flush=True)
            import traceback as tb
            tb.print_exc()
            score_result = {"score": 0, "verdict": "TAMPERED", "breakdown": {}}
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
                "score": score_result.get("score", 0),
                "status": score_result.get("verdict", "TAMPERED"),
                "breakdown": score_result.get("breakdown", {}),
                "engine_statuses": {k: v["status"] for k, v in engine_results.items()},
                "metadata_status": engine_results["metadata"]["status"],
                "ocr_status": engine_results["ocr"]["status"],
                "qr_status": engine_results["qr"]["status"],
                "tampering_status": engine_results["tamper"]["status"],
                "signature_status": engine_results["signature"]["status"],
                "signature_count": sum(r.get("signatures_count", 0) for r in all_signature),
                "signature_details": sig_details_all,
                "qr_details": all_qr_details,
                "qr_detection_debug": qr_dbg,
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
