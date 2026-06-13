"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { useAuth } from "@/lib/auth-context";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "";

interface Finding {
  type: "info" | "warning" | "error";
  title: string;
  detail: string;
  points: number;
  severity: "minor" | "medium" | "high";
  field_location?: string;
  page?: number;
}

interface AnalysisResult {
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
    findings: Record<string, Finding[]>;
    blockchain?: {
      blockchain_hash: string;
      document_hash: string;
      timestamp: string;
      verification_url: string;
      block_number: number;
    };
    report_b64?: string;
    total_deductions?: number;
    anomaly_count?: number;
  };
}

const steps = [
  { p: 10, msg: "Preprocessing document..." },
  { p: 25, msg: "Analyzing metadata..." },
  { p: 40, msg: "Running OCR and text analysis..." },
  { p: 55, msg: "Verifying QR codes..." },
  { p: 70, msg: "Detecting image tampering..." },
  { p: 85, msg: "Analyzing signatures..." },
  { p: 95, msg: "Calculating authenticity score..." },
  { p: 98, msg: "Generating blockchain verification..." },
  { p: 100, msg: "Analysis complete!" },
];

export default function HomePage() {
  const { user, token, login, signup, logout, loading } = useAuth();

  // --- Overlay state ---
  const [activeOverlay, setActiveOverlay] = useState<string | null>(null);
  const closeOverlay = useCallback(() => setActiveOverlay(null), []);

  // --- Auth form state (within login overlay) ---
  const [authMode, setAuthMode] = useState<"login" | "signup">("login");
  const [authEmail, setAuthEmail] = useState("");
  const [authPassword, setAuthPassword] = useState("");
  const [authName, setAuthName] = useState("");
  const [authError, setAuthError] = useState("");
  const [authSubmitting, setAuthSubmitting] = useState(false);

  const openLogin = useCallback(() => {
    setActiveOverlay("login");
    setAuthMode("login");
    setAuthEmail("");
    setAuthPassword("");
    setAuthName("");
    setAuthError("");
  }, []);

  const handleAuthSubmit = useCallback(async (e: React.FormEvent) => {
    e.preventDefault();
    setAuthError("");
    setAuthSubmitting(true);
    try {
      if (authMode === "login") {
        await login(authEmail, authPassword);
      } else {
        await signup(authName, authEmail, authPassword);
      }
      setActiveOverlay(null);
    } catch (err: any) {
      setAuthError(err.message || "Authentication failed");
    } finally {
      setAuthSubmitting(false);
    }
  }, [authMode, authEmail, authPassword, authName, login, signup]);

  // --- File state ---
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFileChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setSelectedFile(file);
      setError("");
    }
  }, []);

  // --- Analysis state ---
  const [analyzing, setAnalyzing] = useState(false);
  const [progress, setProgress] = useState(0);
  const [progressMsg, setProgressMsg] = useState("");
  const [error, setError] = useState("");
  const [results, setResults] = useState<AnalysisResult | null>(null);
  const resultDataRef = useRef<AnalysisResult | null>(null);

  const handleVerifyClick = useCallback(() => {
    if (!selectedFile) {
      fileInputRef.current?.click();
      return;
    }
    startAnalysis(selectedFile);
  }, [selectedFile]);

  const startAnalysis = useCallback(async (file: File) => {
    setAnalyzing(true);
    setProgress(0);
    setProgressMsg("Preprocessing document...");
    setError("");

    const interval = setInterval(() => {
      setProgress(prev => {
        const next = Math.min(prev + 3, 95);
        const step = steps.find(s => s.p >= next);
        if (step) setProgressMsg(step.msg);
        return next;
      });
    }, 600);

    const formData = new FormData();
    formData.append("file", file);

    const headers: Record<string, string> = {};
    if (token) headers["Authorization"] = `Bearer ${token}`;

    try {
      const res = await fetch(`${API_BASE}/api/analyze`, {
        method: "POST",
        body: formData,
        headers: headers as HeadersInit,
      });
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error((errData.detail || "Analysis failed") + " (HTTP " + res.status + ")");
      }
      const data: AnalysisResult = await res.json();
      clearInterval(interval);
      setProgress(100);
      setProgressMsg("Analysis complete!");
      resultDataRef.current = data;
      setTimeout(() => {
        setAnalyzing(false);
        setResults(data);
      }, 600);
    } catch (err: any) {
      clearInterval(interval);
      setAnalyzing(false);
      setError(err.message || "Analysis failed");
    }
  }, [token]);

  const goHome = useCallback(() => {
    setResults(null);
    setSelectedFile(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
    window.scrollTo({ top: 0, behavior: "smooth" });
  }, []);

  const downloadReport = useCallback((b64: string, filename: string) => {
    const byteChars = atob(b64);
    const bytes = new Uint8Array(byteChars.length);
    for (let i = 0; i < byteChars.length; i++) bytes[i] = byteChars.charCodeAt(i);
    const blob = new Blob([bytes], { type: "application/pdf" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename.replace(/\.[^/.]+$/, "") + "_report.pdf";
    a.click();
    URL.revokeObjectURL(url);
  }, []);

  const shareResults = useCallback(() => {
    const data = resultDataRef.current;
    if (!data) return;
    const r = data.results;
    if (navigator.share) {
      navigator.share({
        title: "DOCVERIFY AI - Document Verification",
        text: "Document authenticity score: " + r.score + "% - " + r.status,
        url: window.location.href,
      }).catch(() => {});
    } else {
      navigator.clipboard.writeText(window.location.href);
      alert("Link copied to clipboard!");
    }
  }, []);

  const [stars, setStars] = useState<{ left: string; top: string; size: number; delay: string; duration: string }[]>([]);
  useEffect(() => {
    const generated = Array.from({ length: 180 }, () => ({
      left: Math.random() * 100 + "%",
      top: Math.random() * 100 + "%",
      size: Math.random() * 2.5 + 1,
      delay: Math.random() * 5 + "s",
      duration: Math.random() * 3 + 2 + "s",
    }));
    setStars(generated);
  }, []);

  const r = results?.results;

  return (
    <>
      <style>{`
        .star { position: absolute; border-radius: 50%; background: #fff; opacity: 0.5; animation: twinkle 3s ease-in-out infinite alternate; }
        @keyframes twinkle { 0% { opacity: 0.2; } 100% { opacity: 0.9; } }
        @keyframes scan-line { 0% { top: 0; } 100% { top: 100%; } }
        @keyframes float { 0%, 100% { transform: translateY(0); } 50% { transform: translateY(-6px); } }
        @keyframes fade-in-up { 0% { opacity: 0; transform: translateY(16px); } 100% { opacity: 1; transform: translateY(0); } }
        @keyframes orbit-dot { 0%, 100% { transform: translate(0, 0); opacity: 0.6; } 25% { transform: translate(12px, -18px); opacity: 1; } 50% { transform: translate(-8px, -30px); opacity: 0.4; } 75% { transform: translate(-20px, -10px); opacity: 0.8; } }
        @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
        @keyframes pulse-ring { 0% { transform: translate(-50%, -50%) scale(1); opacity: 0.5; } 100% { transform: translate(-50%, -50%) scale(1.6); opacity: 0; } }
        .nav-link { color: rgba(255,255,255,0.6); transition: color 0.2s; font-size: 15px; font-weight: 500; cursor: pointer; text-decoration: none; }
        .nav-link:hover { color: #fff; }
        .hover-glow { display: inline-block; position: relative; background: linear-gradient(90deg, #fff 0%, #fff 40%, #F5A623 40%, #F5A623 100%); background-size: 250% 100%; -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; background-position: 0 0; transition: background-position 0.6s ease, filter 0.4s ease; cursor: default; }
        .hover-glow:hover { background-position: 100% 0; filter: drop-shadow(0 0 20px rgba(245,166,35,0.4)); }
        .hover-glow::after { content: ''; position: absolute; bottom: 4px; left: 0; right: 0; height: 6px; background: rgba(245,166,35,0); filter: blur(8px); border-radius: 4px; transition: background 0.6s ease; }
        .hover-glow:hover::after { background: rgba(245,166,35,0.2); }
        .verify-stat { padding: 8px 14px; border-radius: 9999px; background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.06); font-size: 12px; font-weight: 500; color: #fff; display: flex; align-items: center; gap: 5px; opacity: 0; animation: fade-in-up 0.6s ease forwards; }
        .verify-stat:nth-child(1) { animation-delay: 0.1s; }
        .verify-stat:nth-child(2) { animation-delay: 0.3s; }
        .verify-stat:nth-child(3) { animation-delay: 0.5s; }
      `}</style>

      {/* Stars */}
      <div className="stars" style={{ position: "fixed", inset: 0, pointerEvents: "none", zIndex: 0 }}>
        {stars.map((s, i) => (
          <div key={i} className="star" style={{
            left: s.left, top: s.top, width: s.size + "px", height: s.size + "px",
            animationDelay: s.delay, animationDuration: s.duration,
          }} />
        ))}
      </div>

      <input type="file" ref={fileInputRef} accept=".pdf,.png,.jpg,.jpeg,.tiff,.bmp" style={{ display: "none" }}
        onChange={handleFileChange} />

      {/* Navbar */}
      <nav style={{ background: "rgba(0,0,0,0.85)", backdropFilter: "blur(12px)", borderBottom: "1px solid rgba(255,255,255,0.05)" }}
        className="fixed top-0 left-0 right-0 z-50 h-16 flex items-center">
        <div className="max-w-7xl mx-auto px-6 w-full flex items-center justify-between">
          <a href="/" className="flex items-center gap-3" onClick={() => { if (!analyzing) { setResults(null); setSelectedFile(null); } }}>
            <img src="/logo.jpeg" alt="DOCVERIFY AI" style={{ width: 36, height: 36, borderRadius: 8, objectFit: "cover" }} />
            <span className="font-bold text-lg tracking-tight hidden sm:inline" style={{ color: "#fff" }}>
              DOCVERIFY <span style={{ color: "#f53c23" }}>AI</span>
            </span>
          </a>
          <div className="nav-links flex items-center gap-8" style={{ display: "flex" }}>
            <a href="#how-it-works" className="nav-link">How it Works</a>
            <a href="#" className="nav-link" onClick={(e) => { e.preventDefault(); setActiveOverlay("pricing"); }}>Pricing</a>
            {user ? (
              <span className="flex items-center gap-3">
                <span style={{ color: "rgba(255,255,255,0.8)", fontSize: 14, fontWeight: 600 }}>{user.name}</span>
                <button onClick={logout}
                  style={{ background: "rgba(255,255,255,0.06)", border: "1px solid rgba(255,255,255,0.08)", color: "rgba(255,255,255,0.6)", padding: "8px 18px", borderRadius: 9999, fontSize: 13, fontWeight: 600, cursor: "pointer" }}>
                  Sign Out
                </button>
              </span>
            ) : (
              <a href="#" className="nav-link" onClick={(e) => { e.preventDefault(); openLogin(); }}>Sign In</a>
            )}
          </div>
          <button className="btn-gold" onClick={() => window.open("https://chatgpt.com", "_blank")}
            style={{ background: "linear-gradient(135deg, #F5A623, #D4870A)", color: "#000", fontWeight: 600, padding: "12px 28px", borderRadius: 9999, display: "inline-flex", alignItems: "center", gap: 10, fontSize: 15, transition: "all 0.3s", border: "none", cursor: "pointer" }}>
            <span style={{ width: 24, height: 24, borderRadius: "50%", background: "rgba(0,0,0,0.2)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 13 }}>AI</span>
            Chat with Alex
          </button>
        </div>
      </nav>

      {/* Hero Section */}
      {!results && (
        <section className="hero-section relative min-h-screen flex items-center" style={{ paddingTop: 80 }}>
          <div style={{ position: "absolute", bottom: -120, left: "50%", transform: "translateX(-50%)", width: 900, height: 500, borderRadius: "50%", background: "radial-gradient(ellipse at center bottom, rgba(245, 166, 35, 0.5) 0%, rgba(212, 135, 10, 0.25) 30%, rgba(200, 120, 0, 0.08) 55%, transparent 75%)", filter: "blur(40px)", zIndex: 1, pointerEvents: "none" }} />
          <div className="max-w-7xl mx-auto px-6 w-full relative z-10">
            <div className="hero-layout flex items-start justify-between gap-16">
              <div className="flex-1 max-w-2xl">
                <h1 className="hero-headline text-7xl lg:text-8xl font-black leading-[1.05] tracking-tight">
                  <span className="hover-glow">AI-Powered</span><br />
                  <span className="hover-glow">Document Authentication</span><br />
                  <span className="hover-glow">and Fraud Detection</span>
                </h1>
              </div>
              <div className="hero-right flex-1 max-w-md pt-4">
                <div style={{ width: "100%", maxWidth: 340, margin: "0 auto", position: "relative" }}>
                  <div style={{ position: "absolute", width: 4, height: 4, borderRadius: "50%", background: "#F5A623", boxShadow: "0 0 6px #F5A623", pointerEvents: "none", animation: "orbit-dot 5s ease-in-out infinite", top: 0, left: "10%", animationDelay: "0s" }} />
                  <div style={{ position: "absolute", width: 5, height: 5, borderRadius: "50%", background: "#F5A623", boxShadow: "0 0 6px #F5A623", pointerEvents: "none", animation: "orbit-dot 5s ease-in-out infinite", top: "5%", right: "5%", animationDelay: "1s" }} />
                  <div style={{ position: "absolute", width: 4, height: 4, borderRadius: "50%", background: "#F5A623", boxShadow: "0 0 6px #F5A623", pointerEvents: "none", animation: "orbit-dot 5s ease-in-out infinite", bottom: "30%", left: 0, animationDelay: "2s" }} />
                  <div style={{ position: "absolute", width: 3, height: 3, borderRadius: "50%", background: "#F5A623", boxShadow: "0 0 6px #F5A623", pointerEvents: "none", animation: "orbit-dot 5s ease-in-out infinite", bottom: "10%", right: "8%", animationDelay: "0.5s" }} />
                  <div style={{ position: "absolute", width: 5, height: 5, borderRadius: "50%", background: "#F5A623", boxShadow: "0 0 6px #F5A623", pointerEvents: "none", animation: "orbit-dot 5s ease-in-out infinite", top: "40%", left: "-8%", animationDelay: "3s" }} />
                  <div style={{ position: "absolute", width: 5, height: 5, borderRadius: "50%", background: "#F5A623", boxShadow: "0 0 6px #F5A623", pointerEvents: "none", animation: "orbit-dot 5s ease-in-out infinite", top: "60%", right: "-5%", animationDelay: "1.5s" }} />
                  <div style={{ position: "absolute", width: 3, height: 3, borderRadius: "50%", background: "#F5A623", boxShadow: "0 0 6px #F5A623", pointerEvents: "none", animation: "orbit-dot 5s ease-in-out infinite", bottom: "45%", left: "5%", animationDelay: "4s" }} />
                  <div style={{ position: "absolute", width: 5, height: 5, borderRadius: "50%", background: "#F5A623", boxShadow: "0 0 6px #F5A623", pointerEvents: "none", animation: "orbit-dot 5s ease-in-out infinite", top: "20%", right: "10%", animationDelay: "2.5s" }} />

                  <div onClick={() => fileInputRef.current?.click()}
                    style={{ width: "100%", height: 150, border: selectedFile ? "2px solid #22c55e" : "2px dashed rgba(245,166,35,0.4)", borderRadius: 16, background: selectedFile ? "rgba(34,197,94,0.04)" : "rgba(255,255,255,0.03)", backdropFilter: "blur(10px)", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 8, position: "relative", overflow: "hidden", transition: "border-color 0.3s, background 0.3s", cursor: "pointer" }}>
                    <div style={{ position: "absolute", left: "10%", width: "80%", height: 2, background: "linear-gradient(90deg, transparent, #F5A623, transparent)", boxShadow: "0 0 12px #F5A623", animation: "scan-line 2.5s ease-in-out infinite", pointerEvents: "none" }} />
                    <div style={{ width: 40, height: 40, borderRadius: "50%", background: "rgba(245,166,35,0.12)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 20, color: "#F5A623", animation: "float 2s ease-in-out infinite", position: "relative", zIndex: 1 }}>&#8593;</div>
                    <div style={{ fontSize: 15, fontWeight: 600, color: "#fff", position: "relative", zIndex: 1 }}>
                      {selectedFile ? selectedFile.name : "Drop your document here"}
                    </div>
                    <div style={{ fontSize: 12, color: "rgba(255,255,255,0.4)", position: "relative", zIndex: 1 }}>
                      {selectedFile ? Math.round(selectedFile.size / 1024) > 1024 ? (Math.round(selectedFile.size / 1024) / 1024).toFixed(1) + " MB" : Math.round(selectedFile.size / 1024) + " KB" : "PDF \u00B7 PNG \u00B7 JPG \u00B7 TIFF"}
                    </div>
                  </div>

                  {error && (
                    <div style={{ marginTop: 16, padding: "12px 16px", background: "rgba(239,68,68,0.1)", border: "1px solid rgba(239,68,68,0.3)", borderRadius: 12, fontSize: 13, color: "#ef4444" }}>
                      {error}
                    </div>
                  )}

                  <div className="verify-btn-wrap" style={{ position: "relative", display: "inline-flex", margin: "24px auto 0", width: "100%", justifyContent: "center" }}>
                    <div className="pulse-ring" style={{ position: "absolute", top: "50%", left: "50%", width: 280, height: 64, borderRadius: 9999, border: "2px solid #F5A623", transform: "translate(-50%, -50%) scale(1)", opacity: 0, pointerEvents: "none", animation: "pulse-ring 2.5s ease-out infinite" }} />
                    <div className="pulse-ring" style={{ position: "absolute", top: "50%", left: "50%", width: 280, height: 64, borderRadius: 9999, border: "2px solid #F5A623", transform: "translate(-50%, -50%) scale(1)", opacity: 0, pointerEvents: "none", animation: "pulse-ring 2.5s ease-out 0.8s infinite" }} />
                    <button onClick={handleVerifyClick}
                      style={{ position: "relative", zIndex: 2, width: 280, height: 64, borderRadius: 9999, background: "linear-gradient(135deg, #F5A623, #EA580C)", border: "none", display: "flex", alignItems: "center", justifyContent: "center", gap: 12, fontSize: 18, fontWeight: 800, color: "#000", cursor: "pointer", transition: "all 0.3s ease" }}>
                      <span style={{ display: "inline-flex", alignItems: "center", justifyContent: "center", fontSize: 22 }}>
                        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                          <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
                          <path d="M9 12l2 2 4-4" />
                        </svg>
                      </span>
                      {selectedFile ? "Verify Document" : "Select Document"}
                    </button>
                  </div>

                  <div style={{ display: "inline-flex", alignItems: "center", gap: 8, padding: "8px 18px", borderRadius: 9999, background: "rgba(255,255,255,0.06)", border: "1px solid rgba(255,255,255,0.08)", fontSize: 12, fontWeight: 500, color: "rgba(255,255,255,0.6)", marginTop: 20, animation: "float 3s ease-in-out infinite" }}>
                    <span style={{ width: 6, height: 6, borderRadius: "50%", background: "#22c55e", display: "inline-block", flexShrink: 0 }} />
                    256-bit Encrypted &middot; Blockchain Verified
                  </div>
                  <div style={{ display: "flex", gap: 8, marginTop: 16, justifyContent: "center" }}>
                    <span className="verify-stat">&#128269; 50K+ Docs Verified</span>
                    <span className="verify-stat">&#9889; 2s Avg Speed</span>
                    <span className="verify-stat">&#128737; 99.9% Accuracy</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>
      )}

      {/* How It Works section (always visible) */}
      {!results && (
        <section id="how-it-works" style={{ padding: "80px 24px", background: "#0a0f1a", borderTop: "1px solid rgba(255,255,255,0.04)" }}>
          <div style={{ maxWidth: 900, margin: "0 auto" }}>
            <h2 style={{ fontSize: 36, fontWeight: 800, textAlign: "center", marginBottom: 8 }}>
              How <span style={{ color: "#F5A623" }}>DOCVERIFY AI</span> Works
            </h2>
            <p style={{ color: "rgba(255,255,255,0.5)", textAlign: "center", maxWidth: 680, margin: "0 auto 56px", fontSize: 16, lineHeight: 1.7 }}>
              An advanced document verification platform designed to detect forged, manipulated, or suspicious documents using Artificial Intelligence and Digital Forensics.
            </p>

            {[
              { num: 1, title: "Upload Your Document", desc: "Users can upload documents in PDF, JPG, PNG, TIFF, or other supported formats. The system securely processes each file and prepares it for forensic analysis." },
              { num: 2, title: "AI-Powered Multi-Layer Verification", desc: null, subs: [
                { label: "Metadata Verification", text: "The system extracts document metadata and checks creation and modification dates, author and software information, missing or altered metadata, and suspicious editing history." },
                { label: "OCR Content Analysis", text: "Using Optical Character Recognition (OCR), DOCVERIFY AI extracts all text from the document, detects text alterations and overlays, identifies inconsistent fonts and formatting, and checks content integrity across pages." },
                { label: "QR Code Validation", text: "If a document contains QR codes, the platform decodes embedded information, validates URLs and encoded data, detects damaged or manipulated QR codes, and verifies placement consistency." },
                { label: "Tampering Detection", text: "Advanced Error Level Analysis (ELA) identifies edited regions within images, hidden modifications, copy-move forgeries, compression inconsistencies, and image manipulation patterns." },
                { label: "Signature &amp; Seal Verification", text: "The platform analyzes handwritten signatures, official stamps and seals, signature positioning, missing or duplicated signatures, and unusual signature characteristics." },
              ] },
              { num: 3, title: "Authenticity Scoring", desc: null },
              { num: 4, title: "Fraud Detection Report", desc: "DOCVERIFY AI generates a detailed forensic report containing overall authenticity score, module-wise analysis results, severity-based findings, tampering indicators, signature verification results, QR code validation details, and visual evidence with forensic highlights." },
              { num: 5, title: "Blockchain Verification Certificate", desc: "For every analyzed document, DOCVERIFY AI creates a secure SHA-256 document hash, timestamped verification record, unique verification identifier, and blockchain-based verification certificate. This creates a tamper-resistant proof that the document was analyzed and verified at a specific point in time." },
            ].map((step) => (
              <div key={step.num} style={{ marginBottom: 56 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 16, marginBottom: step.subs ? 20 : 16 }}>
                  <span style={{ background: "#F5A623", color: "#000", width: 40, height: 40, borderRadius: "50%", display: "flex", alignItems: "center", justifyContent: "center", fontWeight: 800, fontSize: 18, flexShrink: 0 }}>{step.num}</span>
                  <h3 style={{ fontSize: 24, fontWeight: 700 }}>{step.title}</h3>
                </div>
                {step.desc && <p style={{ color: "rgba(255,255,255,0.55)", lineHeight: 1.7, marginLeft: 56 }}>{step.desc}</p>}
                {step.subs && (
                  <div style={{ marginLeft: 56, display: "grid", gap: 24 }}>
                    {step.subs.map((sub) => (
                      <div key={sub.label} style={{ background: "#111827", borderRadius: 12, padding: 24, border: "1px solid rgba(255,255,255,0.05)" }}>
                        <h4 style={{ fontWeight: 700, fontSize: 18, marginBottom: 8, color: "#F5A623" }}>{sub.label}</h4>
                        <p style={{ color: "rgba(255,255,255,0.5)", fontSize: 14, lineHeight: 1.7 }}>{sub.text}</p>
                      </div>
                    ))}
                  </div>
                )}
                {step.num === 3 && (
                  <div style={{ marginLeft: 56, display: "grid", gap: 12, marginTop: 20 }}>
                    <div style={{ background: "#111827", borderRadius: 8, padding: "16px 20px", borderLeft: "4px solid #22c55e" }}>
                      <strong style={{ color: "#22c55e" }}>80–100:</strong> <span style={{ color: "rgba(255,255,255,0.6)" }}>Verified Document</span>
                    </div>
                    <div style={{ background: "#111827", borderRadius: 8, padding: "16px 20px", borderLeft: "4px solid #F5A623" }}>
                      <strong style={{ color: "#F5A623" }}>50–79:</strong> <span style={{ color: "rgba(255,255,255,0.6)" }}>Suspicious Document</span>
                    </div>
                    <div style={{ background: "#111827", borderRadius: 8, padding: "16px 20px", borderLeft: "4px solid #ef4444" }}>
                      <strong style={{ color: "#ef4444" }}>0–49:</strong> <span style={{ color: "rgba(255,255,255,0.6)" }}>Tampered or Potentially Fake Document</span>
                    </div>
                  </div>
                )}
              </div>
            ))}

            <div style={{ marginTop: 64, paddingTop: 48, borderTop: "1px solid rgba(255,255,255,0.06)" }}>
              <h2 style={{ fontSize: 28, fontWeight: 800, textAlign: "center", marginBottom: 8 }}>
                How <span style={{ color: "#F5A623" }}>DOCVERIFY AI</span> Detects Fake Documents
              </h2>
              <p style={{ color: "rgba(255,255,255,0.5)", textAlign: "center", maxWidth: 600, margin: "0 auto 36px", fontSize: 15 }}>
                Fake or manipulated documents often leave digital traces. DOCVERIFY AI identifies these traces by examining:
              </p>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px,1fr))", gap: 12 }}>
                {["Altered text and overwritten content", "Image editing artifacts", "Inconsistent metadata", "Forged signatures and stamps", "Modified QR codes", "Unusual formatting patterns", "Copy-paste tampering attempts", "Hidden image manipulations"].map((text) => (
                  <div key={text} style={{ background: "rgba(245,166,35,0.06)", border: "1px solid rgba(245,166,35,0.1)", borderRadius: 8, padding: "14px 16px", textAlign: "center", fontSize: 14, color: "rgba(255,255,255,0.65)" }}>
                    {text}
                  </div>
                ))}
              </div>
              <p style={{ color: "rgba(255,255,255,0.45)", textAlign: "center", marginTop: 28, fontSize: 15, lineHeight: 1.7 }}>
                By combining AI analysis, digital forensics, OCR technology, and blockchain verification, DOCVERIFY AI helps organizations, institutions, and individuals identify fraudulent documents with greater confidence and accuracy.
              </p>
            </div>

            <div style={{ marginTop: 64, padding: 40, background: "linear-gradient(135deg, rgba(245,166,35,0.06), rgba(212,135,10,0.03))", borderRadius: 16, border: "1px solid rgba(245,166,35,0.1)", textAlign: "center" }}>
              <h2 style={{ fontSize: 28, fontWeight: 800, marginBottom: 24 }}>
                Why Choose <span style={{ color: "#F5A623" }}>DOCVERIFY AI</span>?
              </h2>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(170px,1fr))", gap: 12, textAlign: "center" }}>
                {["AI-Powered Verification", "Multi-Layer Fraud Detection", "Real-Time Analysis", "Blockchain Verification Certificate", "Detailed Forensic Reports", "Secure & Privacy-Focused Processing", "Fast and Accurate Results"].map((text) => (
                  <div key={text} style={{ padding: 12, color: "rgba(255,255,255,0.7)", fontSize: 14 }}>
                    &#10003; {text}
                  </div>
                ))}
              </div>
            </div>
          </div>
        </section>
      )}

      {/* Results Section */}
      {results && r && (
        <section className="results-section active" style={{ display: "block", paddingTop: 100, paddingBottom: 60, minHeight: "100vh", position: "relative", zIndex: 10 }}>
          <div className="max-w-6xl mx-auto px-4">
            <div className="text-center pt-4 mb-8">
              <button onClick={goHome}
                style={{ background: "rgba(255,255,255,0.06)", border: "1px solid rgba(255,255,255,0.08)", color: "rgba(255,255,255,0.6)", padding: "10px 24px", borderRadius: 9999, fontSize: 14, fontWeight: 600, cursor: "pointer", transition: "all 0.3s", marginBottom: 20, display: "inline-flex", alignItems: "center", gap: 8 }}>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M19 12H5M12 19l-7-7 7-7" /></svg>
                Back to Home
              </button>
              <h1 style={{ fontSize: 32, fontWeight: 800, marginBottom: 8 }}>Analysis Complete</h1>
              <p style={{ color: "rgba(255,255,255,0.5)", fontSize: 15 }}>{results.filename}</p>
              {r.analyzed_pages > 1 && (
                <p style={{ color: "rgba(255,255,255,0.35)", fontSize: 13, marginTop: 4 }}>Analyzed {r.analyzed_pages} pages</p>
              )}
            </div>

            <div style={{ maxWidth: 900, margin: "0 auto", display: "grid", gap: 32 }}>
              {/* Score Gauge */}
              <div className="result-card" style={{ background: "#111827", borderRadius: 16, border: "1px solid rgba(255,255,255,0.06)", padding: 24, textAlign: "center" }}>
                <ScoreGaugeComponent score={r.score} />
                <div style={{ display: "flex", justifyContent: "center", gap: 32, marginTop: 16, fontSize: 13, color: "rgba(255,255,255,0.4)" }}>
                  <span>Total Deductions: <strong style={{ color: "#ef4444" }}>{r.total_deductions || 0}</strong></span>
                  <span>Anomalies: <strong style={{ color: r.score >= 80 ? "#22c55e" : r.score >= 50 ? "#F5A623" : "#ef4444" }}>{r.anomaly_count || 0}</strong></span>
                </div>
              </div>

              {/* Module Status Cards */}
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
                {[
                  ["metadata", r.metadata_status],
                  ["ocr", r.ocr_status],
                  ["qr", r.qr_status],
                  ["tampering", r.tampering_status],
                  ["signature", r.signature_status],
                ].map(([key, status]) => {
                  const deduction = (r.deductions && r.deductions[key]) || 0;
                  const hasIssues = (status as string).toLowerCase() !== "ok" && (status as string).toLowerCase() !== "clean" && (status as string).toLowerCase() !== "passed";
                  return (
                    <div key={key as string} className="result-card" style={{ background: "#111827", borderRadius: 16, border: "1px solid rgba(255,255,255,0.06)", padding: "20px 24px", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                      <div>
                        <div style={{ fontWeight: 700, fontSize: 16, textTransform: "capitalize", marginBottom: 4 }}>{key as string}</div>
                        <div style={{ fontSize: 13, color: "rgba(255,255,255,0.5)" }}>
                          Status: <span style={{ textTransform: "capitalize", color: "rgba(255,255,255,0.7)" }}>{status as string}</span>
                          {deduction > 0 && <span style={{ color: "#ef4444" }}> -{deduction} pts</span>}
                        </div>
                      </div>
                      <span style={{ fontSize: 12, padding: "4px 14px", borderRadius: 9999, fontWeight: 600, background: hasIssues ? "rgba(239,68,68,0.1)" : "rgba(34,197,94,0.1)", color: hasIssues ? "#ef4444" : "#22c55e", border: "1px solid " + (hasIssues ? "rgba(239,68,68,0.2)" : "rgba(34,197,94,0.2)") }}>
                        {hasIssues ? "Issues" : "Passed"}
                      </span>
                    </div>
                  );
                })}
              </div>

              {/* Blockchain */}
              {r.blockchain && (
                <div className="result-card" style={{ background: "#111827", borderRadius: 16, border: "1px solid rgba(255,255,255,0.06)", padding: 24 }}>
                  <h3 style={{ fontSize: 18, fontWeight: 700, marginBottom: 16 }}>Blockchain Verification</h3>
                  <div style={{ fontSize: 13, color: "rgba(255,255,255,0.5)", fontFamily: "monospace", wordBreak: "break-all" }}>
                    <p>Hash: {r.blockchain.blockchain_hash ? r.blockchain.blockchain_hash.slice(0, 30) + "..." : "N/A"}</p>
                    <p>Block #{r.blockchain.block_number || "N/A"}</p>
                    {r.blockchain.verification_url && (
                      <a href={r.blockchain.verification_url} target="_blank" rel="noopener noreferrer"
                        style={{ color: "#F5A623", textDecoration: "underline", display: "inline-flex", alignItems: "center", gap: 4, marginTop: 8 }}>
                        Verify on Blockchain
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                          <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
                          <polyline points="15 3 21 3 21 9" />
                          <line x1="10" y1="14" x2="21" y2="3" />
                        </svg>
                      </a>
                    )}
                  </div>
                </div>
              )}

              {/* Findings */}
              {r.findings && (
                <div className="result-card" style={{ background: "#111827", borderRadius: 16, border: "1px solid rgba(255,255,255,0.06)", padding: 24 }}>
                  <h3 style={{ fontSize: 18, fontWeight: 700, marginBottom: 16 }}>Findings & Evidence</h3>
                  {Object.entries(r.findings).map(([engine, items]) => {
                    if (!items || (items as Finding[]).length === 0) return null;
                    return (
                      <div key={engine} style={{ marginBottom: 16 }}>
                        <h4 style={{ fontSize: 14, fontWeight: 600, color: "#F5A623", textTransform: "capitalize", marginBottom: 8 }}>{engine}</h4>
                        {(items as Finding[]).map((f, i) => {
                          const fColor = f.type === "error" ? "#ef4444" : f.type === "warning" ? "#F5A623" : "rgba(255,255,255,0.5)";
                          return (
                            <div key={i} style={{ padding: 12, background: "rgba(255,255,255,0.03)", borderRadius: 8, marginBottom: 8, borderLeft: "3px solid " + fColor }}>
                              <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 2 }}>{f.title}</div>
                              {f.detail && <div style={{ fontSize: 12, color: "rgba(255,255,255,0.45)" }}>{f.detail}</div>}
                              {f.points > 0 && <div style={{ fontSize: 11, color: "#ef4444", marginTop: 4 }}>-{f.points} pts</div>}
                            </div>
                          );
                        })}
                      </div>
                    );
                  })}
                </div>
              )}

              {/* Actions */}
              <div className="result-card" style={{ background: "#111827", borderRadius: 16, border: "1px solid rgba(255,255,255,0.06)", padding: 24, display: "flex", gap: 12, justifyContent: "center" }}>
                <button onClick={() => r.report_b64 && downloadReport(r.report_b64!, results.filename)}
                  style={{ background: "linear-gradient(135deg,#F5A623,#D4870A)", color: "#000", padding: "12px 28px", borderRadius: 9999, fontSize: 14, fontWeight: 700, border: "none", cursor: "pointer", display: "inline-flex", alignItems: "center", gap: 8 }}>
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" /><polyline points="7 10 12 15 17 10" /><line x1="12" y1="15" x2="12" y2="3" /></svg>
                  Download Report
                </button>
                <button onClick={shareResults}
                  style={{ background: "rgba(255,255,255,0.06)", border: "1px solid rgba(255,255,255,0.08)", color: "rgba(255,255,255,0.7)", padding: "12px 28px", borderRadius: 9999, fontSize: 14, fontWeight: 600, cursor: "pointer", display: "inline-flex", alignItems: "center", gap: 8 }}>
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="18" cy="5" r="3" /><circle cx="6" cy="12" r="3" /><circle cx="18" cy="19" r="3" /><line x1="8.59" y1="13.51" x2="15.42" y2="17.49" /><line x1="15.41" y1="6.51" x2="8.59" y2="10.49" /></svg>
                  Share
                </button>
              </div>
            </div>
          </div>
        </section>
      )}

      {/* Footer */}
      <footer id="main-footer" style={{ borderTop: "1px solid rgba(255,255,255,0.06)", padding: "32px 24px", textAlign: "center" }}>
        <div style={{ display: "flex", justifyContent: "center", alignItems: "center", gap: 32, flexWrap: "wrap" }}>
          <a href="#" style={{ color: "rgba(255,255,255,0.5)", transition: "color 0.2s", display: "flex", alignItems: "center", gap: 6, fontSize: 14, textDecoration: "none" }}
            onMouseOver={(e) => (e.currentTarget.style.color = "#fff")} onMouseOut={(e) => (e.currentTarget.style.color = "rgba(255,255,255,0.5)")}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z" /><polyline points="22,6 12,13 2,6" /></svg>
            Email
          </a>
          <a href="#" onClick={(e) => { e.preventDefault(); openLogin(); }}
            style={{ color: "rgba(255,255,255,0.5)", transition: "color 0.2s", display: "flex", alignItems: "center", gap: 6, fontSize: 14, textDecoration: "none", cursor: "pointer" }}
            onMouseOver={(e) => (e.currentTarget.style.color = "#fff")} onMouseOut={(e) => (e.currentTarget.style.color = "rgba(255,255,255,0.5)")}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4" /><polyline points="10 17 15 12 10 7" /><line x1="15" y1="12" x2="3" y2="12" /></svg>
            Sign In
          </a>
          <a href="#" style={{ color: "rgba(255,255,255,0.5)", transition: "color 0.2s", display: "flex", alignItems: "center", gap: 6, fontSize: 14, textDecoration: "none" }}
            onMouseOver={(e) => (e.currentTarget.style.color = "#fff")} onMouseOut={(e) => (e.currentTarget.style.color = "rgba(255,255,255,0.5)")}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" /><circle cx="12" cy="7" r="4" /></svg>
            About Us
          </a>
          <a href="#" onClick={(e) => { e.preventDefault(); setActiveOverlay("terms"); }}
            style={{ color: "rgba(255,255,255,0.5)", transition: "color 0.2s", display: "flex", alignItems: "center", gap: 6, fontSize: 14, textDecoration: "none", cursor: "pointer" }}
            onMouseOver={(e) => (e.currentTarget.style.color = "#fff")} onMouseOut={(e) => (e.currentTarget.style.color = "rgba(255,255,255,0.5)")}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><polyline points="14 2 14 8 20 8" /><line x1="16" y1="13" x2="8" y2="13" /><line x1="16" y1="17" x2="8" y2="17" /></svg>
            Terms &amp; Conditions
          </a>
        </div>
        <p style={{ color: "rgba(255,255,255,0.2)", fontSize: 13, marginTop: 20 }}>&copy; 2026 DOCVERIFY AI. All rights reserved.</p>
      </footer>

      {/* Analyzing Overlay */}
      {analyzing && (
        <div className="analyzing-overlay active" style={{ position: "fixed", inset: 0, zIndex: 999, background: "rgba(0,0,0,0.92)", display: "flex", alignItems: "center", justifyContent: "center" }}>
          <div style={{ textAlign: "center", maxWidth: 400 }}>
            <div style={{ width: 80, height: 80, borderRadius: "50%", border: "4px solid rgba(245,166,35,0.2)", borderTopColor: "#F5A623", animation: "spin 1s linear infinite", margin: "0 auto 24px" }} />
            <h2 style={{ fontSize: 24, fontWeight: 700, marginBottom: 8 }}>Analyzing Document</h2>
            <p style={{ color: "rgba(255,255,255,0.5)", marginBottom: 24 }}>{progressMsg}</p>
            <div style={{ width: "100%", height: 6, background: "rgba(255,255,255,0.06)", borderRadius: 3, overflow: "hidden" }}>
              <div style={{ height: "100%", background: "linear-gradient(90deg, #F5A623, #EA580C)", borderRadius: 3, transition: "width 0.4s ease", width: progress + "%" }} />
            </div>
            <p style={{ color: "rgba(255,255,255,0.3)", fontSize: 12, marginTop: 8 }}>{progress}% complete</p>
          </div>
        </div>
      )}

      {/* Login Overlay */}
      {activeOverlay === "login" && (
        <div className="overlay open" style={{ position: "fixed", inset: 0, zIndex: 999, background: "#0D0D0D", overflowY: "auto" }}>
          <button onClick={closeOverlay}
            style={{ position: "fixed", top: 20, right: 24, background: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.08)", color: "rgba(255,255,255,0.4)", width: 40, height: 40, borderRadius: "50%", fontSize: 20, cursor: "pointer", zIndex: 1000, display: "flex", alignItems: "center", justifyContent: "center" }}>
            &times;
          </button>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", minHeight: "100vh" }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "center", padding: "48px 40px" }}>
              <div style={{ width: "100%", maxWidth: 440 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 40 }}>
                  <div style={{ width: 42, height: 42, background: "linear-gradient(135deg,#F5A623,#EA580C)", borderRadius: 10, display: "flex", alignItems: "center", justifyContent: "center", fontWeight: 900, fontSize: 22, color: "#000" }}>D</div>
                  <span style={{ fontSize: 20, fontWeight: 800, color: "#fff" }}>DocVerify<span style={{ color: "#F5A623" }}>AI</span></span>
                </div>
                <h1 style={{ fontSize: 40, fontWeight: 800, color: "#fff", marginBottom: 12, lineHeight: 1.15 }}>
                  {authMode === "login" ? "Welcome Back!" : "Create Account"}
                </h1>
                <p style={{ color: "rgba(255,255,255,0.5)", fontSize: 15, lineHeight: 1.7, marginBottom: 36 }}>
                  {authMode === "login"
                    ? "Upload certificates, receipts, and PDFs. Detect possible tampering signals such as metadata mismatches, duplicate QR codes, edited text regions, and inconsistent formatting."
                    : "Sign up to save your analysis history, download reports, and track document verifications across sessions."}
                </p>
                <form onSubmit={handleAuthSubmit}>
                  {authMode === "signup" && (
                    <div style={{ marginBottom: 20 }}>
                      <label style={{ display: "block", fontSize: 13, fontWeight: 600, color: "rgba(255,255,255,0.6)", marginBottom: 6 }}>Full Name</label>
                      <input type="text" placeholder="John Doe" value={authName} required
                        onChange={(e) => setAuthName(e.target.value)}
                        style={{ width: "100%", padding: "14px 16px", background: "#1a1a1a", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 12, color: "#fff", fontSize: 15, outline: "none" }} />
                    </div>
                  )}
                  <div style={{ marginBottom: 20 }}>
                    <label style={{ display: "block", fontSize: 13, fontWeight: 600, color: "rgba(255,255,255,0.6)", marginBottom: 6 }}>Email</label>
                    <input type="email" placeholder="your@email.com" value={authEmail} required
                      onChange={(e) => setAuthEmail(e.target.value)}
                      style={{ width: "100%", padding: "14px 16px", background: "#1a1a1a", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 12, color: "#fff", fontSize: 15, outline: "none" }} />
                  </div>
                  <div style={{ marginBottom: 20 }}>
                    <label style={{ display: "block", fontSize: 13, fontWeight: 600, color: "rgba(255,255,255,0.6)", marginBottom: 6 }}>Password</label>
                    <input type="password" placeholder="Enter password" value={authPassword} required minLength={6}
                      onChange={(e) => setAuthPassword(e.target.value)}
                      style={{ width: "100%", padding: "14px 16px", background: "#1a1a1a", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 12, color: "#fff", fontSize: 15, outline: "none" }} />
                  </div>
                  {authError && (
                    <p style={{ color: "#ef4444", fontSize: 13, marginBottom: 12 }}>{authError}</p>
                  )}
                  <button type="submit" disabled={authSubmitting}
                    style={{ width: "100%", padding: 14, border: "none", borderRadius: 9999, fontSize: 16, fontWeight: 700, cursor: authSubmitting ? "not-allowed" : "pointer", background: "linear-gradient(135deg,#F5A623,#EA580C)", color: "#000", marginTop: 8, opacity: authSubmitting ? 0.7 : 1 }}>
                    {authSubmitting ? "Please wait..." : authMode === "login" ? "Sign In" : "Sign Up"}
                  </button>
                </form>
                <div style={{ display: "flex", alignItems: "center", gap: 16, margin: "28px 0", color: "rgba(255,255,255,0.2)", fontSize: 13 }}>
                  <span style={{ flex: 1, height: 1, background: "rgba(255,255,255,0.06)" }}></span>or continue with<span style={{ flex: 1, height: 1, background: "rgba(255,255,255,0.06)" }}></span>
                </div>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12 }}>
                  {[
                    { name: "Google", icon: <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 01-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z" /> },
                    { name: "GitHub", icon: <path d="M12 0C5.37 0 0 5.37 0 12c0 5.3 3.44 9.8 8.2 11.39.6.11.82-.26.82-.58 0-.28-.01-1.04-.02-2.05-3.34.72-4.04-1.61-4.04-1.61-.55-1.39-1.34-1.76-1.34-1.76-1.08-.74.08-.73.08-.73 1.2.09 1.83 1.24 1.83 1.24 1.07 1.83 2.8 1.3 3.48.99.11-.77.42-1.3.76-1.6-2.66-.3-5.46-1.33-5.46-5.93 0-1.31.47-2.38 1.24-3.22-.12-.3-.54-1.52.12-3.17 0 0 1-.32 3.3 1.23a11.5 11.5 0 016 0c2.28-1.55 3.29-1.23 3.29-1.23.66 1.65.24 2.87.12 3.17.77.84 1.23 1.91 1.23 3.22 0 4.61-2.8 5.63-5.48 5.92.43.37.82 1.1.82 2.22 0 1.61-.01 2.9-.01 3.3 0 .32.22.7.84.58A12 12 0 0024 12c0-6.63-5.37-12-12-12z" /> },
                    { name: "Microsoft", icon: <path d="M11.4 24H0V12.6h11.4V24zM24 24H12.6V12.6H24V24zM11.4 11.4H0V0h11.4v11.4zm12.6 0H12.6V0H24v11.4z" /> },
                  ].map(({ name, icon }) => (
                    <button key={name} type="button"
                      style={{ padding: 12, borderRadius: 12, border: "1px solid rgba(255,255,255,0.1)", background: "transparent", color: "rgba(255,255,255,0.7)", fontSize: 13, fontWeight: 500, cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center", gap: 8 }}>
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">{icon}</svg>
                      {name}
                    </button>
                  ))}
                </div>
                <p style={{ textAlign: "center", marginTop: 28, fontSize: 14, color: "rgba(255,255,255,0.35)" }}>
                  {authMode === "login" ? "Don't have an account? " : "Already have an account? "}
                  <a href="#" onClick={(e) => { e.preventDefault(); setAuthMode(authMode === "login" ? "signup" : "login"); setAuthError(""); }}
                    style={{ color: "#F5A623", textDecoration: "none", fontWeight: 600 }}>
                    {authMode === "login" ? "Sign Up" : "Sign In"}
                  </a>
                </p>
              </div>
            </div>
            <div style={{ background: "#0D0D0D", position: "relative", display: "flex", alignItems: "flex-end", justifyContent: "flex-end", padding: 48, overflow: "hidden" }}>
              <div style={{ position: "absolute", bottom: -80, right: -80, width: 600, height: 600, borderRadius: "50%", background: "radial-gradient(circle,rgba(120,60,0,0.4) 0%,transparent 70%)", pointerEvents: "none" }} />
              <div style={{ position: "relative", zIndex: 2, maxWidth: 420, background: "rgba(255,255,255,0.06)", backdropFilter: "blur(16px)", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 16, padding: 28 }}>
                <div style={{ display: "flex", gap: 8, marginBottom: 20 }}>
                  <span style={{ padding: "4px 14px", borderRadius: 9999, fontSize: 12, fontWeight: 500, background: "rgba(0,0,0,0.5)", color: "rgba(255,255,255,0.7)", border: "1px solid rgba(255,255,255,0.06)" }}>AI Verification</span>
                  <span style={{ padding: "4px 14px", borderRadius: 9999, fontSize: 12, fontWeight: 500, background: "rgba(0,0,0,0.5)", color: "rgba(255,255,255,0.7)", border: "1px solid rgba(255,255,255,0.06)" }}>Document Security</span>
                </div>
                <h3 style={{ fontSize: 22, fontWeight: 700, color: "#fff", lineHeight: 1.3, marginBottom: 14 }}>Detect document fraud before it becomes a problem.</h3>
                <p style={{ fontSize: 14, lineHeight: 1.7, color: "rgba(255,255,255,0.5)" }}>
                  <strong style={{ color: "#F5A623", fontWeight: 600 }}>DocVerifyAI</strong> automatically analyzes certificates, receipts, invoices and PDFs to identify metadata inconsistencies, duplicate QR codes, suspicious edits and formatting anomalies using advanced AI-powered verification.
                </p>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Pricing Overlay */}
      {activeOverlay === "pricing" && (
        <div className="overlay open" style={{ position: "fixed", inset: 0, zIndex: 999, background: "#0D0D0D", overflowY: "auto" }}>
          <button onClick={closeOverlay}
            style={{ position: "fixed", top: 20, right: 24, background: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.08)", color: "rgba(255,255,255,0.4)", width: 40, height: 40, borderRadius: "50%", fontSize: 20, cursor: "pointer", zIndex: 1000, display: "flex", alignItems: "center", justifyContent: "center" }}>
            &times;
          </button>
          <div className="overlay-inner" style={{ maxWidth: 1120, margin: "0 auto", padding: "100px 24px 80px", textAlign: "center" }}>
            <div style={{ display: "inline-flex", alignItems: "center", gap: 8, padding: "8px 20px", borderRadius: 9999, fontSize: 14, fontWeight: 500, color: "#fff", background: "rgba(255,255,255,0.06)", border: "1px solid rgba(255,255,255,0.1)", marginBottom: 24 }}>&#128640; Premium Subscription Plans</div>
            <h2 style={{ fontSize: 40, fontWeight: 800, color: "#fff", marginBottom: 14, lineHeight: 1.15 }}>Choose Your Verification Plan</h2>
            <p style={{ maxWidth: 640, margin: "0 auto 56px", fontSize: 15, lineHeight: 1.7, color: "rgba(255,255,255,0.5)" }}>Protect your organization from forged certificates, tampered invoices and fraudulent documents using AI-powered verification technology.</p>
            <div className="pricing-grid" style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 24, alignItems: "start" }}>
              {[
                { name: "Starter", price: "$0", desc: "Perfect for students and individual users.", features: ["10 Document Checks per day", "QR Code Validation", "Metadata Analysis", "Email Support", "Basic Reports"], featured: false },
                { name: "Professional", price: "$9", desc: "Best for startups and institutions.", features: ["Unlimited Verification", "Advanced AI Detection", "Forgery Heatmaps", "Priority Support", "Detailed Analytics", "Fraud Risk Score"], featured: true },
                { name: "Enterprise", price: "$15", desc: "For universities, banks and large organizations.", features: ["Unlimited Team Access", "API Integration", "Custom AI Models", "Dedicated Manager", "Advanced Security", "Compliance Dashboard"], featured: false },
              ].map((plan) => (
                <div key={plan.name} style={{
                  background: "#1C1C1C", border: plan.featured ? "2px solid #F5A623" : "1px solid rgba(255,255,255,0.08)",
                  borderRadius: 16, padding: "36px 28px", textAlign: "left", position: "relative", zIndex: plan.featured ? 2 : 1,
                }}>
                  {plan.featured && (
                    <div style={{ position: "absolute", top: -14, left: "50%", transform: "translateX(-50%)", background: "#F5A623", color: "#000", fontSize: 13, fontWeight: 700, padding: "6px 20px", borderRadius: 9999, whiteSpace: "nowrap" }}>
                      Most Popular
                    </div>
                  )}
                  <h3 style={{ fontSize: 22, fontWeight: 700, color: "#fff", marginBottom: 8 }}>{plan.name}</h3>
                  <div style={{ marginBottom: 12 }}><span style={{ fontSize: 52, fontWeight: 800, color: "#fff", lineHeight: 1 }}>{plan.price}</span><span style={{ fontSize: 15, color: "rgba(255,255,255,0.4)", marginLeft: 4 }}>/month</span></div>
                  <p style={{ fontSize: 14, color: "rgba(255,255,255,0.5)", marginBottom: 24, lineHeight: 1.5 }}>{plan.desc}</p>
                  <ul style={{ listStyle: "none", padding: 0, margin: "0 0 32px", display: "flex", flexDirection: "column", gap: 14 }}>
                    {plan.features.map((f) => (
                      <li key={f} style={{ fontSize: 14, color: "rgba(255,255,255,0.65)", display: "flex", alignItems: "center", gap: 10 }}>
                        <span style={{ color: "#F5A623", fontWeight: 700, fontSize: 16 }}>&#10003;</span> {f}
                      </li>
                    ))}
                  </ul>
                  <button style={{
                    width: "100%", padding: 14, borderRadius: 9999, fontSize: 15, fontWeight: 700, cursor: "pointer",
                    background: plan.featured ? "linear-gradient(135deg,#F5A623,#D4870A)" : plan.name === "Enterprise" ? "transparent" : "linear-gradient(135deg,#F5A623,#D4870A)",
                    color: plan.name === "Enterprise" ? "#F5A623" : "#000",
                    border: plan.name === "Enterprise" ? "2px solid #F5A623" : "none",
                  }}>
                    {plan.name === "Enterprise" ? "Contact Sales" : plan.name === "Starter" ? "Get Started" : "Upgrade Now"}
                  </button>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Terms Overlay */}
      {activeOverlay === "terms" && (
        <div className="overlay open" style={{ position: "fixed", inset: 0, zIndex: 999, background: "#0D0D0D", overflowY: "auto" }}>
          <button onClick={closeOverlay}
            style={{ position: "fixed", top: 20, right: 24, background: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.08)", color: "rgba(255,255,255,0.4)", width: 40, height: 40, borderRadius: "50%", fontSize: 20, cursor: "pointer", zIndex: 1000, display: "flex", alignItems: "center", justifyContent: "center" }}>
            &times;
          </button>
          <div style={{ maxWidth: 760, margin: "0 auto", padding: "100px 24px 80px", textAlign: "left" }}>
            <h1 style={{ fontSize: 36, fontWeight: 800, color: "#fff", marginBottom: 8 }}>Terms &amp; Conditions</h1>
            <p style={{ fontSize: 14, color: "rgba(255,255,255,0.35)", marginBottom: 32 }}>Last Updated: June 2026</p>
            <p style={{ fontSize: 15, lineHeight: 1.7, color: "rgba(255,255,255,0.6)", marginBottom: 12 }}>Welcome to DocVerify AI. By accessing or using our platform, you agree to comply with and be bound by these Terms &amp; Conditions.</p>
            {[
              { title: "1. Acceptance of Terms", text: "By using DocVerify AI, you acknowledge that you have read, understood, and accepted these Terms &amp; Conditions and our Privacy Policy." },
              { title: "2. Service Description", text: "DocVerify AI provides AI-powered document authenticity analysis and verification services. The platform analyzes uploaded documents and generates authenticity scores, forensic findings, and verification reports." },
              { title: "3. User Responsibilities", items: ["Upload only documents that you own or have legal authorization to verify.", "Provide accurate information when using the platform.", "Use the service only for lawful purposes.", "Not attempt to reverse engineer, disrupt, or misuse the platform."] },
              { title: "4. Prohibited Uses", items: ["Upload malicious, illegal, or copyrighted content without authorization.", "Use the platform for fraud, identity theft, or unlawful activities.", "Attempt to gain unauthorized access to system resources or data."] },
              { title: "5. AI Analysis Disclaimer", text: "Verification results are generated using artificial intelligence and forensic analysis techniques. Results are provided for informational purposes only. DocVerify AI does not guarantee 100% accuracy. Users should seek professional verification for legal, financial, or regulatory decisions." },
              { title: "6. Data Processing", text: "Uploaded documents are processed solely to provide verification services. Documents may be stored temporarily for analysis purposes. We implement reasonable security measures to protect user data." },
              { title: "7. Intellectual Property", text: "All platform content, software, algorithms, logos, and trademarks belong to DocVerify AI and are protected by applicable intellectual property laws." },
              { title: "8. Limitation of Liability", items: ["Any indirect, incidental, or consequential damages.", "Decisions made based on AI-generated authenticity reports.", "Loss of data resulting from technical failures beyond our control."] },
              { title: "9. Account Suspension", text: "We reserve the right to suspend or terminate accounts that violate these Terms &amp; Conditions or engage in suspicious activities." },
            ].map((section) => (
              <div key={section.title}>
                <h2 style={{ fontSize: 20, fontWeight: 700, color: "#F5A623", marginTop: 32, marginBottom: 10 }}>{section.title}</h2>
                {section.text && <p style={{ fontSize: 15, lineHeight: 1.7, color: "rgba(255,255,255,0.6)", marginBottom: 12 }}>{section.text}</p>}
                {section.items && (
                  <ul style={{ margin: "0 0 12px 24px", padding: 0, listStyle: "disc" }}>
                    {section.items.map((item, i) => (
                      <li key={i} style={{ fontSize: 15, lineHeight: 1.7, color: "rgba(255,255,255,0.6)", marginBottom: 4 }}>{item}</li>
                    ))}
                  </ul>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </>
  );
}

function ScoreGaugeComponent({ score }: { score: number }) {
  const radius = 110;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (score / 100) * circumference;
  const scoreColor = score >= 80 ? "#22c55e" : score >= 50 ? "#F5A623" : "#ef4444";
  const scoreLabel = score >= 80 ? "Genuine" : score >= 50 ? "Suspicious" : "Tampered";

  return (
    <div style={{ position: "relative", width: 236, height: 236, margin: "0 auto" }}>
      <svg width="236" height="236" viewBox="0 0 236 236" style={{ transform: "rotate(-90deg)" }}>
        <circle cx="118" cy="118" r={radius} fill="none" stroke="rgba(255,255,255,0.05)" strokeWidth="16" />
        <circle cx="118" cy="118" r={radius} fill="none" stroke={scoreColor} strokeWidth="16"
          strokeDasharray={circumference} strokeDashoffset={offset} strokeLinecap="round"
          style={{ transition: "all 1.5s ease-out" }} />
      </svg>
      <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center" }}>
        <span style={{ fontSize: 48, fontWeight: 800, color: scoreColor }}>{score}%</span>
        <span style={{ fontSize: 18, fontWeight: 600, color: scoreColor }}>{scoreLabel}</span>
      </div>
    </div>
  );
}
