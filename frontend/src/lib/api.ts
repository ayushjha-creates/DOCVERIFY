const API_BASE = process.env.NEXT_PUBLIC_API_URL || "";

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

export interface Base64Image {
  page: number;
  data: string;
}

export interface AnalysisResult {
  session_id: string;
  filename: string;
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
    preview_b64?: string;
    marked_images?: Base64Image[];
    signature_images?: Base64Image[];
    report_b64?: string;
  };
}

export async function analyzeDocument(file: File): Promise<AnalysisResult> {
  const formData = new FormData();
  formData.append("file", file);

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 45000);

  let response;
  try {
    response = await fetch(`${API_BASE}/api/analyze`, {
      method: "POST",
      body: formData,
      signal: controller.signal,
    });
  } catch (networkError) {
    clearTimeout(timeout);
    if (networkError instanceof DOMException && networkError.name === "AbortError") {
      throw new Error("Analysis timed out (took longer than 45 seconds). Large documents with many pages may exceed the server limit. Try a smaller file.");
    }
    throw new Error(`Network error: Unable to reach the server. ${networkError instanceof Error ? networkError.message : "Please check your connection."}`);
  }
  clearTimeout(timeout);

  if (!response.ok) {
    let detail = "Analysis failed";
    let statusCode = response.status;
    try {
      const errorBody = await response.json();
      detail = errorBody.detail || detail;
    } catch {
      try {
        detail = await response.text() || detail;
      } catch {
        detail = `Server returned ${statusCode}`;
      }
    }
    throw new Error(`${detail} (HTTP ${statusCode})`);
  }

  return response.json();
}

export function getReportUrl(sessionId: string): string {
  return `${API_BASE}/api/report/${sessionId}`;
}

export function getPreviewUrl(sessionId: string): string {
  return `${API_BASE}/api/temp/${sessionId}/preview.png`;
}

export function getMarkedImageUrl(sessionId: string): string {
  return `${API_BASE}/api/temp/${sessionId}/marked.png`;
}
