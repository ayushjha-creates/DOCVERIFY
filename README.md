# DOCVERIFY AI

A multi-layered document authenticity verification platform that uses AI-powered forensic analysis to detect tampering, verify signatures, analyze metadata, extract QR codes, and generate blockchain-verified authenticity reports.

----
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

1. User uploads a document via the Next.js frontend
2. Frontend sends the file as `multipart/form-data` to `/api/analyze`
3. API preprocesses the document (PDF→images, normalization)
4. Five analysis modules run in parallel on each page/image
5. Scoring engine aggregates results into a weighted score
6. Blockchain module creates a tamper-proof hash record
7. Report generator produces a PDF
8. Frontend renders the results in real-time

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
- DPI standardization (300 DPI for PDFs)
- Grayscale conversion for OCR
- Image deskewing
- Contrast normalization

### 2. Metadata Analysis (`metadata_analysis.py`)

Extracts and validates metadata from documents.

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

**Weight distribution:**

| Module | Weight | Description |
|---|---|---|
| Tampering Detection | 30% | Primary indicator of forgery |
| Metadata Analysis | 20% | Document provenance |
| OCR Analysis | 20% | Content integrity |
| QR Code Analysis | 15% | Embedded data integrity |
| Signature Analysis | 15% | Handwritten element authenticity |

**Score ranges:**

| Score | Status | Description |
|---|---|---|
| 80–100 | ✅ Verified | Document appears authentic |
| 50–79 | ⚠️ Suspicious | Possible alterations detected |
| 0–49 | ❌ Tampered | Strong evidence of forgery |

### 8. Blockchain Verification (`blockchain.py`)

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

**Live at:** [https://docverify-ai.vercel.app/](https://docverify-ai.vercel.app/)

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

## API Reference

### Health Check

```
GET /api/health
```

**Response:**
```json
{
  "status": "healthy",
  "app": "DOCVERIFY AI"
}
```

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

| Technology | Version | Purpose |
|---|---|---|
| Next.js | 16.2.7 | React framework with App Router |
| React | 19.2.4 | UI library |
| TypeScript | 5.x | Type safety |
| Tailwind CSS | 4.x | Utility-first styling |
| Shadcn UI | — | Primitive UI components |
| Lucide React | — | Icon library |
| Base UI | 1.5.0 | Headless UI primitives |

### Backend

| Technology | Version | Purpose |
|---|---|---|
| Python | 3.11+ | Runtime |
| FastAPI | 1.x | Web framework (ASGI) |
| Uvicorn | — | ASGI server |
| Pillow | 10.1+ | Image processing |
| OpenCV | 4.8+ | Computer vision (ELA, contours) |
| Tesseract OCR | 5.x | Optical character recognition |
| PyMuPDF (fitz) | 1.23+ | PDF rendering |
| pdf2image | 1.16+ | PDF-to-image conversion |
| pdfplumber | 0.10+ | PDF metadata extraction |
| ReportLab | 4.0+ | PDF report generation |
| NumPy | 1.24+ | Numerical operations |
| Pydantic | 2.5+ | Data validation |

### Infrastructure

| Technology | Purpose |
|---|---|
| Vercel (Services) | Hosting, serverless functions, CDN |
| Docker / Docker Compose | Local development environment |
| npm workspaces | Monorepo package management |

---

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
