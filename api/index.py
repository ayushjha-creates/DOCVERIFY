import os
import sys
import traceback

_api_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _api_dir)

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="DOCVERIFY AI API", version="1.0.0", root_path="/api")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health_check():
    return {"status": "healthy", "app": "DOCVERIFY AI"}


@app.post("/api/analyze")
async def analyze_document(file: UploadFile = File(...)):
    return JSONResponse(content={"message": "analyze endpoint hit", "filename": file.filename})
