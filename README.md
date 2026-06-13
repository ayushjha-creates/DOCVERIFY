# DOCVERIFY AI

 AI-powered document authenticity verification platform. Upload a document — get a forensic analysis report with authenticity score, tampering evidence, signature detection, metadata forensics, QR validation, and a blockchain-anchored verification certificate.
---


## Overview

DOCVERIFY AI analyzes documents across five parallel forensic engines to produce a comprehensive authenticity score. Users upload a document (PDF, image), and the platform returns:

- **Authenticity Score** (0–100)
- **Per-module status** (clean / suspicious / tampered)
- **Detailed findings** with severity levels
- **Visual evidence** (ELA heatmaps, signature highlights)
- **Blockchain verification certificate**
- **Downloadable PDF report**

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        Client Browser                        │
│                        (Next.js SPA)                         │
└──────────────────┬──────────────────────────────────────────┘
                   │ POST /api/analyze (multipart/form-data)
                   ▼
┌─────────────────────────────────────────────────────────────┐
│                    Vercel Services Router                     │
│   / → frontend service    /api/* → api service (FastAPI)     │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────┐
│                    FastAPI Backend (api/)                     │
│                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐   │
│  │  Preprocess   │  │   Metadata   │  │  OCR Analysis    │   │
│  │  (PDF→Images) │─▶│  Analysis    │  │  (Tesseract)     │   │
│  └──────────────┘  └──────┬───────┘  └────────┬─────────┘   │
│                           │                    │              │
│  ┌──────────────┐  ┌──────▼───────┐  ┌────────▼─────────┐   │
│  │  QR Analysis  │  │  Tampering   │  │  Signature       │   │
│  │  (pyzbar)     │  │  Detection   │  │  Analysis        │   │
│  │               │  │  (ELA)       │  │  (Contour Detect)│   │
│  └──────────────┘  └──────┬───────┘  └────────┬─────────┘   │
│                           │                    │              │
│                           ▼                    ▼              │
│  ┌──────────────────────────────────────────────────────┐    │
│  │                 Scoring Engine                        │    │
│  │  Weighted aggregation of all module scores            │    │
│  └──────────────────────────┬───────────────────────────┘    │
│                             │                                 │
│                             ▼                                 │
│  ┌──────────────────────────────────────────────────────┐    │
│  │           Blockchain Verification                      │    │
│  │  SHA-256 hash → Timestamp → Verification URL          │    │
│  └──────────────────────────┬───────────────────────────┘    │
│                             │                                 │
│                             ▼                                 │
│  ┌──────────────────────────────────────────────────────┐    │
│  │           PDF Report Generator                        │    │
│  │  ReportLab → Base64-encoded downloadable PDF          │    │
│  └──────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

### Data Flow

 1. User uploads file via browser or `curl -F`
2. FastAPI writes file to `/tmp/{uuid}/original.{ext}`
3. Preprocessing converts to PNG pages at 200 DPI, applies CLAHE + denoising
4. Document classifier runs (keyword match on filename + OCR text)
5. Each page runs through all 4 image-based engines (OCR, QR, tamper, signature); metadata runs once
6. Per-page results aggregated via worst-status and max-deduction
7. Scoring engine computes final score with weights and anomaly scaling
8. Blockchain module hashes original file
9. PDF report generated via ReportLab
10. All results + base64-encoded images returned as JSON
11. `/tmp/{uuid}` cleaned up
12. Browser renders results


---

## Forensic Analysis Modules

### 1. Preprocessing (`preprocessing.py`)

Converts uploaded documents into analysis-ready image format.

| Input | Output | Method |
|---|---|---|
| PDF | PNG images (per page) | PyMuPDF / pdf2image |
| JPEG/PNG/TIFF | Normalized RGB image | Pillow |
| BMP | Converted to PNG | Pillow |

Options applied:
- DPI standardization (200 DPI for PDFs)
- Grayscale conversion for OCR
- Image deskewing
- Contrast normalization

### 2. Metadata Analysis (`metadata_analysis.py`)

Extracts and validates metadata from documents.


**Python libraries:** PyMuPDF (fitz) for PDFs, Pillow EXIF for images

**9 checks and their deductions:**

| Check | Trigger | Deduction |
|-------|---------|-----------|
| Suspicious Producer | Producer contains Canva, GIMP, Photoshop, ILovePDF, etc. | -15 pts |
| Future Timestamp | Creation or modification date is in the future | -20 pts |
| Created Today + Online Tool | Same-day creation with suspicious producer | -10 pts |
| Date Mismatch | Creation and modification differ by >3 days | -10 pts |
| Modified Before Creation | Modification date precedes creation (impossible) | -15 pts |
| Unusual Hour | Modified between midnight and 5am or after 10pm | -5 pts |
| AI Tool in Metadata | Producer/creator contains "ChatGPT", "Claude", "Gemini" | -15 pts |
| AI Image Generator | Producer contains "DALL-E", "Midjourney", "Stable Diffusion" | -20 pts |
| Missing Producer | Creator set but no producer → AI stripping indicator | -5 pts |


**Checks performed:**
- PDF metadata extraction (author, producer, creator, creation date)
- EXIF data extraction (for images)
- Software fingerprints (detects Adobe, Microsoft Office, etc.)
- Inconsistent or suspicious metadata fields
- Missing or forged metadata indicators

**Scoring factors:**
- Mismatched creation/modification dates
- Unusual software signatures
- Missing required metadata fields

### 3. OCR Analysis (`ocr_analysis.py`)

Extracts text from document images using Tesseract OCR.
**Libraries:** pytesseract, pdfplumber, OpenCV, NumPy

**Extraction strategy:**
- PDFs: try `pdfplumber` (native text extraction, preserves fonts) → fallback `pdf2image` + Tesseract
- Images: OTSU threshold + sharpening kernel → Tesseract

**8 analysis checks:**

1. **Low OCR confidence** — avg confidence < threshold, >30% of chars below 30% confidence
2. **Mixed font sizes within a line** — char height differs by >2.2× from line mean
3. **Inconsistent font in field** — coefficient of variation >0.5 in 2-6 word lines
4. **Alignment inconsistency** — std of left edges > mean × 0.5 with max gap >200px
5. **Suspicious keywords** — "edited", "tampered", "forged", "doctored", etc.
6. **Control characters / repetition** — Unicode control chars, >25 repeated chars
7. **AI-generated text patterns** — word-length std <1.5, AI phrases, low character diversity
8. **Unicode anomalies** — zero-width spaces, BOM, soft hyphens (>3 occurrences)

**Scoring:** Flag weights summed → total_weight 0=OK, 1=WARN/10pts, 2=WARN/15pts, 3+=FAIL/20pts


**Checks performed:**
- Full text extraction with confidence scoring
- Text consistency analysis across pages
- Detection of text overlays and alterations
- Font consistency checking
- Language detection

**Scoring factors:**
- Low OCR confidence regions
- Inconsistent text styles within a document
- Suspicious text placement (overlays)

### 4. QR Code Analysis (`qr_analysis.py`)

Detects and decodes QR codes within documents.
**Libraries:** OpenCV QRCodeDetector, pyzbar

**7-pass detection cascade:**

| Pass | Method | Image |
|------|--------|-------|
| 1 | `detectAndDecodeMulti` | Grayscale |
| 2 | `detectAndDecodeMulti` | OTSU-thresholded |
| 3 | Iterative mask-and-re-detect (8 rounds max) | Grayscale |
| 4 | `detectAndDecode` (single) | Grayscale |
| 5-6 | Overlapping horizontal tiles (left/center/right 72% strips) | Grayscale |
| 7 | pyzbar decode | 3 image variants (RGB, L, grayscale) |

**Validation per QR:**
- URL? → DNS resolution check + suspicious TLD detection (.xyz, .top, .tk, .ml, .ga, .cf)
- Non-URL? → passes as OK
- Duplicate data across QRs → DUPLICATE_QR_DATA flag

**Scoring:** OK=0, WARN=15 (if any QR is suspicious or duplicates exist), FAIL=30 (if any QR fails decode)


**Checks performed:**
- QR code detection and decoding
- Data format validation (URLs, text, numeric)
- Tampered or malformed QR code detection
- QR code placement analysis

**Scoring factors:**
- Decoding errors or invalid content
- Partially damaged QR codes
- Suspicious QR code placement

### 5. Tampering Detection (`tampering_detection.py`)

Uses Error Level Analysis (ELA) to identify image manipulation.

**Libraries:** OpenCV, NumPy, Pillow

**Non-AI forensic signals:**

| Technique | Method | Threshold | Deduction |
|-----------|--------|-----------|-----------|
| **ELA** | JPEG recompress at q90, pixel diff | >1% tampered = high, >0.3% = medium | -20 / -5 |
| **Noise Inconsistency** | 50×50 grid std-dev analysis | >2.5σ from mean in >7% of patches | -15 |
| **SIFT Copy-Move** | FLANN feature self-matching, Lowe ratio 0.75 | >30% of keypoints self-match | -10 |
| **Blur/Sharpness** | Laplacian variance per 100×100 grid | >3500 (AI sharp) / <50 (blurry) / >15% anomalous | -10 |

**AI-generation signals:**

| Signal | Method | Threshold | Deduction |
|--------|--------|-----------|-----------|
| Smooth Background | 40×40 patch std-dev mean | <3.0 (normal) / <2.0 (system docs) | -5 |
| Pixel-Perfect Borders | Canny edge ratio per edge | All 4 edges <0.002 | -5 |
| Rendered Text Texture | Gradient direction coherence | >0.90 (strong) / >0.82 (soft) | -10 / -5 |
| Unnatural Colour | HSV saturation mean | <0.015 | -5 |
| Inconsistent Resolution | FFT ring energy ratio | >100 | -5 |

**Multi-signal AI deduction rule (replaces individual AI deductions):**
- 0 AI flags → 0 deduction
- 1 AI flag → 0 deduction (suppressed from output)
- 2 AI flags → 10 deduction
- 3 AI flags → 20 deduction
- 4+ AI flags → 30 deduction

**Non-AI deduction** (ELA + noise + SIFT + blur) added on top.

**System-class forgiveness:** Background threshold loosened to 2.0; border + resolution checks skipped entirely.



**How ELA works:**

ELA exploits JPEG compression artifacts. When an image is re-saved at a known error level (e.g., 90% quality), unaltered regions exhibit predictable compression errors, while manipulated regions show different error levels.

**Checks performed:**
- Per-pixel ELA computation
- Adaptive thresholding for suspicious regions
- Morphological operations to cluster tampered areas
- Heatmap generation for visual evidence
- Copy-move forgery detection

**Scoring factors:**
- Percentage of tampered pixels
- Clustering of suspicious regions
- Severity of detected anomalies

### 6. Signature Analysis (`signature_analysis.py`)

Detects handwritten signatures and stamps using contour analysis.

**Libraries:** OpenCV, pytesseract, NumPy

**3-method cascade** (stops at first success):

| Method | Region | Technique |
|--------|--------|-----------|
| **Method 1: Ink Cluster** | Bottom 45% | Adaptive threshold + morph close + contour filter (aspect 1.2-12, solidity 0.04-0.65) |
| **Method 2: Dark Stroke** | Bottom half | Canny + dilate + top 5 contours by area |
| **Method 3: Colour Ink** | Bottom half | HSV blue mask (100-140, 50-255, 30-200) + dark mask (0-180, 0-255, 0-80) |

**Stamp detection:** Hough Circle Transform on full image, filtered by overlap with text.

**Doc-class-aware response:**
- `system` (boarding pass, ticket, receipt): No signature → status=OK, deduction=0
- `formal` (certificate, degree, passport): No signature → status=WARN, deduction=5
- `unknown`: No signature → status=OK, deduction=0

**Confidence:** Default 70% when region found.


**Checks performed:**
- Contour detection and filtering
- Aspect ratio and size analysis
- Signature region highlighting
- Stamp/round-seal detection
- Multiple signature counting

**Scoring factors:**
- Missing expected signatures
- Unusually large/small signatures
- Suspicious signature placement
- Stamp authenticity indicators

### 7. Scoring Engine (`scoring.py`)

Aggregates all module results into a single authenticity score.

### Module Weights

| Module | Weight | Rationale |
|--------|--------|-----------|
| Metadata | 1.5 | High signal-to-noise — metadata forgeries are either caught or clean |
| QR | 1.5 | High weight — QR tampering directly suggests fraud |
| Signature | 1.0 | Medium |
| Tamper | 0.5 | Deliberately lowered — CV techniques can false-positive |
| OCR | 0.3 | Lowest — OCR errors penalize legitimate scanned docs unfairly |

### Formula

```
module_score         = max(0, 100 - engine_deduction)
base_score           = Σ(module_score × weight) / Σ(weights)
raw_deductions_total = Σ(all_engine_deductions)
interim_score        = max(0, base_score - raw_deductions_total)
```

### Anomaly Scaling

```
anomaly_count = number of modules where deduction > 0

if anomaly_count >= 3:  scaling = 0.6
if anomaly_count == 2:  scaling = 0.75
else:                   scaling = 0.9

final_score = max(0, round(interim_score × scaling))
```

### Verdict Logic

```
if anomaly_count <= 1:  verdict = "Genuine"           (override, ignores score)
elif final_score >= 50: verdict = "Suspicious"
else:                   verdict = "Tampered"
```

The Genuine override ensures a clean document with one minor OCR glitch isn't classified as Tampered.

### System-Class Forgiveness

Applied before scoring: if a `system` document has tamper findings and all are AI-prefixed (none are non-AI tamper), the tamper deduction is zeroed out.

---

### 8. API Reference

### `GET /api/health`

```json
{ "status": "healthy", "app": "DOCVERIFY AI" }
```

### `GET /api/debug`

Returns library versions, import status, environment info, and bundled binary size. Useful for debugging Vercel cold-start issues.

### `POST /api/analyze`

**Request:** `multipart/form-data` with field `file`

**Supported formats:** PDF, PNG, JPG, JPEG, TIFF, BMP (max 20MB, 50 pages)

**Response (200):**

| Field | Type | Description |
|-------|------|-------------|
| `session_id` | string | UUID for this analysis session |
| `filename` | string | Original filename |
| `results.score` | number | Authenticity score 0-100 |
| `results.status` | string | "Genuine", "Suspicious", or "Tampered" |
| `results.base_score` | number | Pre-scaling weighted average |
| `results.total_deductions` | number | Sum of all module deductions |
| `results.anomaly_count` | number | Count of modules with deduction > 0 |
| `results.ai_likelihood_score` | number | 0.0-1.0 (informative only, not in scoring) |
| `results.reasons` | string[] | Human-readable reasons for score |
| `results.deductions` | object | Per-module: `{metadata, ocr, qr, tampering, signature}` |
| `results.engine_statuses` | object | Per-module status string |
| `results.findings` | object | Per-module array of `{type, title, detail, points, severity}` |
| `results.signature_details` | array | `{confidence, bbox, type, area, page}` |
| `results.qr_details` | array | `{data, position, status, flags}` |
| `results.blockchain` | object | `{blockchain_hash, document_hash, timestamp, verification_url}` |
| `results.report_b64` | string | Base64-encoded PDF report |
| `results.marked_images` | array | Base64-encoded ELA heatmaps per page |
| `results.signature_images` | array | Base64-encoded signature highlight overlays |
| `results.preview_b64` | string | Base64-encoded first-page preview |

**Response (400):** Invalid or unprocessable file

**Response (500):** Analysis failure (with error detail)

---






### 9. Blockchain Verification (`blockchain.py`)

Creates a verifiable record of the document analysis.

**Process:**
1. SHA-256 hash of the original document
2. Timestamp generation
3. Creation of a verification URL
4. Simulated block number assignment

**Output:**
- `blockchain_hash`: Unique identifier
- `document_hash`: SHA-256 of the document
- `timestamp`: ISO 8601 timestamp
- `verification_url`: Permalink for verification
- `block_number`: Sequential block identifier

### 9. Report Generator (`report_generator.py`)

Generates a downloadable PDF report using ReportLab.

**Report contents:**
- Document information (filename, date, pages)
- Overall authenticity score with status badge
- Per-module breakdown with scores
- Detailed findings table
- Visual evidence (ELA heatmaps, signature highlights)
- Blockchain verification certificate

---

## Scoring System

```
┌─────────────────────────────────────────────────────────────┐
│  Weighted Scoring Formula                                    │
│                                                              │
│  score = Σ(module_score × module_weight) / Σ(weights)        │
│                                                              │
│  Deductions are applied for each finding:                    │
│  - info (minor):   -2 points                                 │
│  - warning:        -5 points                                 │
│  - error:         -15 points                                 │
│                                                              │
│  Final deductions cap at -50 points per module               │
└─────────────────────────────────────────────────────────────┘
```

---

## Project Structure

```
.
├── api/                                    # Vercel FastAPI backend
│   ├── bin/                                # Bundled Tesseract binary
│   │   ├── tesseract                       # ARM64 macOS binary
│   │   └── tessdata/                       # Language data files
│   ├── modules/
│   │   ├── __init__.py
│   │   ├── preprocessing.py                # PDF/image preprocessing
│   │   ├── metadata_analysis.py            # Metadata extraction
│   │   ├── ocr_analysis.py                 # Tesseract OCR
│   │   ├── qr_analysis.py                  # QR detection
│   │   ├── tampering_detection.py          # ELA analysis
│   │   ├── signature_analysis.py           # Contour-based detection
│   │   ├── scoring.py                      # Score aggregation
│   │   ├── blockchain.py                   # Verification record
│   │   └── report_generator.py             # PDF generation
│   ├── __init__.py
│   ├── index.py                            # FastAPI application entrypoint
│   ├── requirements.txt                    # Python dependencies
│   └── sample/                             # Sample documents
│
├── backend/                                # Local Docker backend
│   ├── modules/                            # Same analysis modules
│   ├── Dockerfile
│   ├── main.py                             # FastAPI entrypoint
│   ├── requirements.txt
│   ├── sample/
│   └── venv/                               # Local virtual environment
│
├── frontend/                               # Next.js application
│   ├── public/
│   │   ├── favicon.ico
│   │   ├── favicon.png
│   │   └── logo.jpeg
│   ├── src/
│   │   ├── app/
│   │   │   ├── globals.css                 # Global styles / Tailwind
│   │   │   ├── layout.tsx                  # Root layout / metadata
│   │   │   └── page.tsx                    # Main application page
│   │   ├── components/
│   │   │   ├── ui/                         # Shadcn UI components
│   │   │   │   ├── badge.tsx
│   │   │   │   ├── button.tsx
│   │   │   │   ├── progress.tsx
│   │   │   │   ├── scroll-area.tsx
│   │   │   │   └── separator.tsx
│   │   │   ├── upload-section.tsx          # File upload with drag-and-drop
│   │   │   ├── score-gauge.tsx             # Circular score visualization
│   │   │   ├── analysis-progress.tsx       # Progress during analysis
│   │   │   ├── detailed-report.tsx         # Per-module findings
│   │   │   ├── visual-evidence.tsx         # ELA/signature images
│   │   │   └── result-actions.tsx          # Share, download, reset
│   │   └── lib/
│   │       └── api.ts                      # API client
│   ├── components.json                     # Shadcn config
│   ├── next.config.ts                      # Next.js configuration
│   ├── package.json
│   ├── postcss.config.mjs
│   ├── tsconfig.json
│   └── eslint.config.mjs
│
├── docker-compose.yml                      # Local development stack
├── start.sh                                # Quick-start script
├── vercel.json                             # Vercel Services configuration
└── README.md
```

---

## Deployment

 *Live:* [https://docverify-api.vercel.app](https://docverify-api.vercel.app)

The app is deployed as a single Vercel project using [Services](https://vercel.com/docs/services), with the Next.js frontend at `/` and the FastAPI backend at `/api`. Import the repo in the [Vercel Dashboard](https://vercel.com/new) with **Framework Preset** set to **Services** — `vercel.json` at the repo root handles the rest.


---

## Local Development

### Option 1: Docker Compose (Recommended)

```bash
# Clone the repository
git clone https://github.com/ayushjha-creates/DOCVERIFY.git
cd DOCVERIFY

# Start all services
docker compose up --build
```

This starts:
- **Frontend** at `http://localhost:3000`
- **Backend API** at `http://localhost:8000`
- **API Docs** (Swagger UI) at `http://localhost:8000/docs`

#### Docker Services

| Service | Image | Port | Depends On |
|---|---|---|---|
| `frontend` | `node:20-alpine` | `3000` | — |
| `backend` | `python:3.11-slim` | `8000` | — |

The Docker setup installs Tesseract OCR and all Python dependencies inside the container.

### Option 2: Manual Setup

#### Prerequisites

- Node.js 20+
- Python 3.11+
- Tesseract OCR
- npm or yarn

#### Backend Setup

```bash
# Navigate to backend
cd backend

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install Python dependencies
pip install -r requirements.txt

# Install Tesseract OCR (if not already installed)
# macOS:
brew install tesseract

# Ubuntu/Debian:
sudo apt-get install tesseract-ocr

# Verify installation
tesseract --version

# Start the API server
uvicorn main:app --reload --port 8000
```

The API is now available at `http://localhost:8000`. Swagger docs at `http://localhost:8000/docs`.

#### Frontend Setup

```bash
# Navigate to frontend
cd frontend

# Install dependencies
npm install

# Set API URL for local development
echo "NEXT_PUBLIC_API_URL=http://localhost:8000" > .env.local

# Start development server
npm run dev
```

The frontend is now available at `http://localhost:3000`.

#### Running Both (without Docker)

Open two terminal windows:

```bash
# Terminal 1: Backend
cd backend && source venv/bin/activate && uvicorn main:app --reload --port 8000

# Terminal 2: Frontend
cd frontend && npm run dev
```

### Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `NEXT_PUBLIC_API_URL` | No | `""` (same-origin) | API base URL. Set to `http://localhost:8000` for local dev. On Vercel, frontend and API share the same domain, so this stays empty. |

---

### Analyze Document

```
POST /api/analyze
Content-Type: multipart/form-data
```

**Parameters:**

| Parameter | Type | Required | Description |
|---|---|---|---|
| `file` | File | Yes | Document to analyze (PDF, PNG, JPG, JPEG, TIFF, BMP) |

**Supported file types:**

| Format | Max Size | Notes |
|---|---|---|
| PDF | 20 MB | Multi-page supported |
| PNG | 20 MB | — |
| JPG/JPEG | 20 MB | — |
| TIFF | 20 MB | Single-page recommended |
| BMP | 20 MB | Converted to PNG internally |

**Success Response (200):**

```json
{
  "session_id": "a1b2c3d4-...",
  "filename": "document.pdf",
  "results": {
    "analyzed_pages": 3,
    "score": 87,
    "status": "verified",
    "reasons": ["Document appears authentic"],
    "deductions": {
      "metadata": 0,
      "ocr": 5,
      "qr": 0,
      "tampering": 0,
      "signature": 0
    },
    "metadata_status": "clean",
    "ocr_status": "suspicious",
    "qr_status": "clean",
    "tampering_status": "clean",
    "signature_status": "signature_detected",
    "signature_count": 2,
    "signature_details": [
      {
        "confidence": 0.85,
        "bbox": [100, 200, 150, 50],
        "type": "signature",
        "area": 7500,
        "page": 1
      }
    ],
    "findings": {
      "metadata": [],
      "ocr": [
        {
          "type": "warning",
          "title": "Low OCR confidence on page 2",
          "detail": "Text region at (120, 340) has 62% confidence",
          "points": 5,
          "severity": "medium",
          "page": 2
        }
      ],
      "qr": [],
      "tampering": [],
      "signature": []
    },
    "blockchain": {
      "blockchain_hash": "0x7f3a...",
      "document_hash": "e3b0c442...",
      "timestamp": "2026-06-07T12:00:00Z",
      "verification_url": "https://verify.docverify.ai/0x7f3a...",
      "block_number": 42
    },
    "marked_images": [
      {
        "page": 1,
        "data": "base64-encoded-png"
      }
    ],
    "signature_images": [
      {
        "page": 1,
        "data": "base64-encoded-png"
      }
    ],
    "preview_b64": "base64-encoded-png",
    "report_b64": "base64-encoded-pdf"
  }
}
```

**Error Response (400):**
```json
{
  "detail": "Could not process document"
}
```

**Error Response (413):**
```json
{
  "detail": "File too large"
}
```

**Error Response (500):**
```json
{
  "detail": "Analysis failed: <error details>"
}
```

---

## Tech Stack

### Frontend

 | Technology | Purpose |
|-----------|---------|
| Static HTML + Tailwind CSS (CDN) | UI, served via Vercel edge |
| Next.js 16 (route handler) | Serves `public/index.html` at `/` |
| Google Fonts (Inter) | Typography |

### Infrastructure

| Service | Purpose |
|---------|---------|
| Vercel (Services) | Serverless hosting, CDN, routing |
| Vercel KV / Blob | Not used yet — available for caching |

---

## Local Development

### Prerequisites

- Python 3.11+
- Node.js 20+
- Tesseract OCR (`brew install tesseract` on macOS)


### Backend

| Technology | Version | Purpose |
|---|---|---|
 | Technology | Version | Purpose |
|-----------|---------|---------|
| Python | 3.11+ | Runtime |
| FastAPI | 1.x | ASGI web framework |
| OpenCV (headless) | 4.8+ | ELA, SIFT, noise, contours, QR detection |
| Tesseract OCR | 5.x | Character recognition (bundled ARM64 binary) |
| PyMuPDF (fitz) | 1.23+ | PDF rendering and metadata extraction |
| Pillow | 10.1+ | Image I/O, EXIF |
| NumPy | 1.24+ | Numerical operations |
| ReportLab | 4.0+ | PDF report generation |
| pyzbar | 0.1+ | QR/bar code decoding supplement |
| pdfplumber | 0.10+ | Native PDF text extraction |
| pdf2image | 1.16+ | PDF→image fallback |
| uv | — | Fast pip replacement (bundled for cold-start) |



### Infrastructure

| Technology | Purpose |
|---|---|
| Vercel (Services) | Hosting, serverless functions, CDN |
| Docker / Docker Compose | Local development environment |
| npm workspaces | Monorepo package management |

---

## Known Weaknesses

| Area | Issue | Impact |
|------|-------|--------|
| Performance | Sequential page loop | Scales O(n) with page count |
| Performance | Tesseract subprocess spawn per page | High latency, no process reuse |
| Performance | SIFT O(n²) matching | Slow on text-heavy, high-feature docs |
| Performance | Vercel 300s function timeout | Complex 50+ page docs may timeout |
| Accuracy | ELA false positives on multi-saved JPEGs | Clean images can show ELA errors |
| Accuracy | SIFT false positives on repeating patterns | Grids, tables, logos trigger copy-move |
| Accuracy | Signature detection only checks *presence* | Cannot authenticate signature against known sample |
| Accuracy | AI detection is statistical | High-quality prints can look "AI-like" |
| Dependency | Tesseract binary is ARM64-only | Fails on x86 Vercel functions without system Tesseract |
| Dependency | Vercel `/tmp` 512MB limit | Large docs with heatmaps can exceed space |
| Security | No authentication | Anyone can use the API (rate-limited only by Vercel) |
| Security | No malware scanning | Uploaded files not scanned for malicious content |
| Code quality | Zero test coverage | No unit/integration tests |

---

## Possible Improvements

**Near-term (next sprint):**
- Delete dead frontend files (`src/components/*`, `src/lib/*`, `globals.css`, `layout.tsx`)
- Add pytest suite for each module
- Parallelize page processing with `asyncio` or `ThreadPoolExecutor`
- Add API key authentication with rate limiting
- Store results in SQLite/PostgreSQL for session history

**Long-term (production):**
- Celery/Redis task queue to bypass Vercel 300s timeout
- Real blockchain verification (Ethereum smart contract or Stellar)
- GPU-based deepfake detection (EfficientNet fine-tuned on document forgeries)
- Multi-language OCR support (Hindi, Arabic, Chinese tessdata)
- Comparison mode — diff two documents
- Batch upload and analysis
- Webhook callbacks for async results
- Role-based access control for enterprise use

---

## License

MIT — see LICENSE file.

Built for hackathon demonstration. Not production enterprise software — results are indicative and should be verified through additional means.

## Performance & Limits

| Aspect | Limit |
|---|---|
| Max file size | 20 MB |
| Max pages (PDF) | 50 pages |
| Analysis timeout | 300 seconds (5 minutes) |
| Function memory | 1024 MB |
| Supported languages (OCR) | English (default), expandable via tessdata |

**Performance tips:**
- Single-page documents analyze fastest (usually 10–30 seconds)
- Large PDFs with many pages increase processing time linearly
- Documents with complex graphics take longer for ELA analysis
- High-resolution images are downscaled to 2000px on the longest edge

---

## Troubleshooting

### Common Issues

| Issue | Cause | Solution |
|---|---|---|
| `File too large` | Upload exceeds 20 MB | Compress or split the document |
| `Could not process document` | Unsupported format or corrupted file | Check file format (PDF/PNG/JPG/TIFF/BMP) |
| Analysis timeout | Document too complex or large | Reduce page count or image resolution |
| OCR returns no text | Scanned document without text layer | Ensure document is legible and properly scanned |
| CORS errors (local dev) | Backend not running or wrong port | Check `NEXT_PUBLIC_API_URL` is set to `http://localhost:8000` |
| `tesseract not found` | Tesseract not installed (local dev) | Run `brew install tesseract` (macOS) or `apt-get install tesseract-ocr` (Linux) |
| Deployment shows old version | Vercel cache | Trigger redeploy with **Clear Build Cache** |
| Services not working | Framework not set to Services | In Vercel dashboard, set Framework Preset → **Services** |

### Debugging

**Check API health:**
```bash
curl https://your-domain.vercel.app/api/health
```

**Test analysis with a local file:**
```bash
curl -X POST https://your-domain.vercel.app/api/analyze \
  -F "file=@sample.pdf"
```

**View Vercel function logs:**
```bash
vercel logs
```

**Check deployment status:**
```bash
vercel inspect
```

---

## Security

- **File validation**: File type and size are validated on both client and server
- **No persistent storage**: Uploaded files are processed in `/tmp` and deleted after analysis
- **CORS**: Allowed origins are configurable; set to `*` for development
- **Python dependencies**: Pinned versions in `requirements.txt`
- **No secrets in code**: Environment variables for configuration

---
