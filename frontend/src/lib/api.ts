const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export interface Finding {
  type: "info" | "warning" | "error";
  title: string;
  detail: string;
  points: number;
  severity: "minor" | "medium" | "high";
  field_location?: string;
  page?: number;
}

export interface BlockchainInfo {
  blockchain_hash: string;
  document_hash: string;
  timestamp: string;
  verification_url: string;
  block_number: number;
}

export interface SignatureDetail {
  confidence: number;
  bbox: [number, number, number, number];
  type: "signature" | "stamp";
  area: number;
  page?: number;
}

export interface PageImage {
  page: number;
  url: string;
}

export interface AnalysisResult {
  session_id: string;
  filename: string;
  file_preview_url: string;
  results: {
    analyzed_pages: number;
    score: number;
    status: string;
    reasons: string[];
    deductions: Record<string, number>;
    metadata_status: string;
    ocr_status: string;
    qr_status: string;
    tampering_status: string;
    signature_status: string;
    signature_count: number;
    signature_details: SignatureDetail[];
    findings: Record<string, Finding[]>;
    blockchain: BlockchainInfo;
    report_url: string;
    marked_image_urls?: PageImage[];
    marked_image_url?: string;
    signature_image_urls?: PageImage[];
    signature_image_url?: string;
  };
}

export async function analyzeDocument(file: File): Promise<AnalysisResult> {
  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch(`${API_BASE}/api/analyze`, {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: "Analysis failed" }));
    throw new Error(error.detail || "Analysis failed");
  }

  return response.json();
}

export function getReportUrl(sessionId: string): string {
  return `${API_BASE}/api/report/${sessionId}`;
}

export function getPreviewUrl(sessionId: string): string {
  return `${API_BASE}/api/temp/${sessionId}/preview.png`;
}

export function getMarkedImageUrl(url: string): string {
  return `${API_BASE}${url}`;
}
