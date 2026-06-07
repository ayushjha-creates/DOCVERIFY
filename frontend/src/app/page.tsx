"use client";

import { useState, useCallback, useRef } from "react";
import { UploadSection } from "@/components/upload-section";
import { ScoreGauge } from "@/components/score-gauge";
import { DetailedReport } from "@/components/detailed-report";
import { VisualEvidence } from "@/components/visual-evidence";
import { ResultActions } from "@/components/result-actions";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Separator } from "@/components/ui/separator";
import { ScrollArea } from "@/components/ui/scroll-area";
import { analyzeDocument, AnalysisResult, getPreviewUrl, getMarkedImageUrl } from "@/lib/api";

type AppState = "welcome" | "uploaded" | "analyzing" | "results";

export default function Home() {
  const [state, setState] = useState<AppState>("welcome");
  const [file, setFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string>("");
  const [analyzing, setAnalyzing] = useState(false);
  const [progress, setProgress] = useState(0);
  const [progressMsg, setProgressMsg] = useState("");
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [error, setError] = useState<string>("");
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFileSelect = useCallback((f: File) => {
    setFile(f);
    setError("");
    const url = URL.createObjectURL(f);
    setPreviewUrl(url);
    setState("uploaded");
  }, []);

  const handleAnalyze = useCallback(async () => {
    if (!file) return;
    setAnalyzing(true);
    setError("");
    setState("analyzing");

    const steps = [
      { progress: 10, msg: "Preprocessing document..." },
      { progress: 25, msg: "Analyzing metadata..." },
      { progress: 40, msg: "Running OCR and text analysis..." },
      { progress: 55, msg: "Verifying QR codes..." },
      { progress: 70, msg: "Detecting image tampering..." },
      { progress: 85, msg: "Analyzing signatures..." },
      { progress: 95, msg: "Calculating authenticity score..." },
      { progress: 98, msg: "Generating blockchain verification..." },
      { progress: 100, msg: "Analysis complete!" },
    ];

    const interval = setInterval(() => {
      setProgress((p) => {
        const next = Math.min(p + 3, 95);
        const step = steps.find((s) => s.progress >= next);
        if (step) setProgressMsg(step.msg);
        return next;
      });
    }, 600);

    try {
      const res = await analyzeDocument(file);
      clearInterval(interval);
      setProgress(100);
      setProgressMsg("Analysis complete!");
      setTimeout(() => {
        setResult(res);
        setState("results");
      }, 500);
    } catch (err: unknown) {
      clearInterval(interval);
      setError(err instanceof Error ? err.message : "Analysis failed");
      setState("uploaded");
      setAnalyzing(false);
    }
  }, [file]);

  const handleUploadNew = useCallback(() => {
    fileInputRef.current?.click();
  }, []);

  const handleNewFileSelected = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (f) handleFileSelect(f);
  }, [handleFileSelect]);

  const handleReset = useCallback(() => {
    setState("welcome");
    setFile(null);
    setPreviewUrl("");
    setResult(null);
    setError("");
    setAnalyzing(false);
    setProgress(0);
    setProgressMsg("");
  }, []);

  const handleShare = useCallback(async () => {
    if (navigator.share && result) {
      try {
        await navigator.share({
          title: "DOCVERIFY AI - Document Verification",
          text: `Document authenticity score: ${result.results.score}% - ${result.results.status}`,
          url: window.location.href,
        });
      } catch { /* ignore */ }
    } else {
      await navigator.clipboard.writeText(window.location.href);
      alert("Link copied to clipboard!");
    }
  }, [result]);

  const r = result?.results;

  return (
    <div className="min-h-screen bg-gradient-to-b from-background to-muted/30">
      <header className="border-b border-border/40 backdrop-blur-sm bg-background/80 sticky top-0 z-50">
        <div className="max-w-6xl mx-auto px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <img src="/logo.jpeg" alt="DOCVERIFY AI" className="w-9 h-9 rounded-lg object-cover" />
            <span className="text-xl font-bold tracking-tight">DOCVERIFY<span className="text-primary"> AI</span></span>
          </div>
          <nav className="flex items-center gap-4">
            <a href="#" className="text-sm text-muted-foreground hover:text-foreground transition-colors">How it Works</a>
            <a href="#" className="text-sm text-muted-foreground hover:text-foreground transition-colors">About</a>
            <Button variant="outline" size="sm" className="gap-2">
              <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
                <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 17.93c-3.95-.49-7-3.85-7-7.93 0-.62.08-1.21.21-1.79L9 15v1c0 1.1.9 2 2 2v1.93zm6.9-2.54c-.26-.81-1-1.39-1.9-1.39h-1v-3c0-.55-.45-1-1-1H8v-2h2c.55 0 1-.45 1-1V7h2c1.1 0 2-.9 2-2v-.41c2.93 1.19 5 4.06 5 7.41 0 2.08-.8 3.97-2.1 5.39z" />
              </svg>
              EN
            </Button>
          </nav>
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-4 py-8">
        {state === "welcome" && (
          <div className="flex flex-col items-center pt-16 pb-24">
            <div className="text-center mb-12">
              <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-primary/10 text-primary text-sm font-medium mb-6">
                <span className="w-2 h-2 rounded-full bg-primary animate-pulse" />
                AI-Powered Forensics
              </div>
              <h1 className="text-5xl md:text-6xl font-bold tracking-tight mb-4">
                <span className="bg-gradient-to-r from-foreground via-foreground to-primary bg-clip-text text-transparent">DOCVERIFY</span>{' '}
                <span className="text-primary">AI</span>
              </h1>
              <p className="text-xl text-muted-foreground max-w-2xl mx-auto">
                Verify Document Authenticity with AI
              </p>
            </div>
            <UploadSection onFileSelect={handleFileSelect} />
            <div className="mt-16 grid grid-cols-1 md:grid-cols-3 gap-6 w-full max-w-3xl">
              {[
                { icon: "🔍", title: "Multi-Layer Forensics", desc: "5 parallel analysis engines check every aspect of your document" },
                { icon: "⚡", title: "Real-Time Results", desc: "Get comprehensive analysis with authenticity score in seconds" },
                { icon: "🔗", title: "Blockchain Verified", desc: "Document hash stored for tamper-proof verification" },
              ].map((f) => (
                <div key={f.title} className="text-center p-6 rounded-xl border bg-card/50 hover:bg-card transition-colors">
                  <span className="text-3xl mb-3 block">{f.icon}</span>
                  <h3 className="font-semibold mb-2">{f.title}</h3>
                  <p className="text-sm text-muted-foreground">{f.desc}</p>
                </div>
              ))}
            </div>
          </div>
        )}

        {state === "uploaded" && (
          <div className="max-w-2xl mx-auto pt-8">
            <div className="rounded-xl border bg-card p-6">
              <h2 className="text-xl font-semibold mb-4">Document Preview</h2>
              <div className="mb-6 rounded-lg bg-muted/50 p-4 flex items-center justify-center min-h-[200px]">
                {file?.type === "application/pdf" ? (
                  <div className="text-center py-8">
                    <svg className="w-16 h-16 mx-auto text-muted-foreground/50 mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z" />
                    </svg>
                    <p className="text-sm font-medium">{file?.name}</p>
                    <p className="text-xs text-muted-foreground mt-1">PDF Document ({(file?.size || 0) / 1024 > 1024 ? `${((file?.size || 0) / 1024 / 1024).toFixed(1)} MB` : `${((file?.size || 0) / 1024).toFixed(0)} KB`})</p>
                  </div>
                ) : previewUrl ? (
                  <img src={previewUrl} alt="Preview" className="max-h-[300px] object-contain rounded" />
                ) : null}
              </div>
              <div className="flex items-center gap-2 text-sm text-muted-foreground mb-6">
                <svg className="w-4 h-4 text-green-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
                File ready for analysis
              </div>
              {error && (
                <div className="mb-4 p-3 rounded-lg bg-destructive/10 border border-destructive/20 text-destructive text-sm">
                  {error}
                </div>
              )}
              <div className="flex gap-3">
                <Button size="lg" className="flex-1 gap-2" onClick={handleAnalyze} disabled={analyzing}>
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
                  </svg>
                  {analyzing ? "Analyzing..." : "Analyze Document"}
                </Button>
                <Button variant="outline" size="lg" onClick={handleReset}>
                  Cancel
                </Button>
              </div>
            </div>
          </div>
        )}

        {state === "analyzing" && (
          <div className="max-w-lg mx-auto pt-24 text-center">
            <div className="mb-8 relative">
              <div className="w-24 h-24 rounded-full bg-primary/10 flex items-center justify-center mx-auto">
                <svg className="w-12 h-12 text-primary animate-spin" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                </svg>
              </div>
            </div>
            <h2 className="text-2xl font-bold mb-2">Analyzing Document</h2>
            <p className="text-muted-foreground mb-8">{progressMsg}</p>
            <Progress value={progress} className="h-2 mb-2" />
            <p className="text-xs text-muted-foreground">{Math.round(progress)}% complete</p>
            <div className="mt-10 space-y-3 text-left max-w-sm mx-auto">
              {[
                { p: 10, label: "Preprocessing", msg: "Converting & cleaning document" },
                { p: 25, label: "Metadata", msg: "Extracting document metadata" },
                { p: 40, label: "OCR & Text", msg: "Running text recognition" },
                { p: 55, label: "QR Codes", msg: "Scanning for embedded codes" },
                { p: 70, label: "Tampering", msg: "Running ELA & forensic checks" },
                { p: 85, label: "Signatures", msg: "Analyzing stamps & signatures" },
                { p: 95, label: "Scoring", msg: "Computing final score" },
              ].map((s) => (
                <div key={s.label} className="flex items-center gap-3">
                  <div className={`w-6 h-6 rounded-full flex items-center justify-center shrink-0 ${
                    progress >= s.p
                      ? "bg-primary text-primary-foreground"
                      : "bg-muted text-muted-foreground"
                  }`}>
                    {progress >= s.p ? (
                      <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 13l4 4L19 7" />
                      </svg>
                    ) : (
                      <span className="text-xs font-medium">{s.p / 10}</span>
                    )}
                  </div>
                  <div className="flex-1">
                    <p className={`text-sm font-medium ${progress >= s.p ? "text-foreground" : "text-muted-foreground"}`}>
                      {s.label}
                    </p>
                    <p className="text-xs text-muted-foreground/70">{s.msg}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {state === "results" && r && (
          <div className="space-y-8 pb-16">
            <div className="text-center pt-4">
              <h1 className="text-3xl font-bold mb-2">Analysis Complete</h1>
              <p className="text-muted-foreground">{result.filename}</p>
              {r.analyzed_pages > 1 && (
                <p className="text-xs text-muted-foreground mt-1">
                  Analyzed {r.analyzed_pages} pages
                </p>
              )}
              <div className="mt-4">
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".pdf,.png,.jpg,.jpeg,.tiff,.bmp"
                  className="hidden"
                  onChange={handleNewFileSelected}
                />
                <Button size="lg" className="gap-2" onClick={handleUploadNew}>
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                  </svg>
                  Upload New Document
                </Button>
              </div>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
              <div className="lg:col-span-1">
                <div className="rounded-xl border bg-card p-6 sticky top-20">
                  <ScoreGauge score={r.score} />
                  <Separator className="my-6" />
                  <div className="space-y-4">
                    <h3 className="font-semibold text-sm text-muted-foreground uppercase tracking-wider">Deductions</h3>
                    {Object.entries(r.deductions).map(([k, v]) => (
                      <div key={k} className="flex items-center justify-between text-sm">
                        <span className="capitalize text-muted-foreground">
                          {k === "metadata" ? "Metadata" :
                           k === "ocr" ? "OCR / Text" :
                           k === "qr" ? "QR Codes" :
                           k === "tampering" ? "Tampering" :
                           k === "signature" ? "Signature" : k}
                        </span>
                        <span className={v > 0 ? "text-destructive font-medium" : "text-green-500 font-medium"}>
                          {v > 0 ? `-${v}` : "0"}
                        </span>
                      </div>
                    ))}
                    <Separator />
                    <div className="flex items-center justify-between text-sm font-bold">
                      <span>Total Deduction</span>
                      <span className="text-destructive">-{r.reasons.length > 0 ? Object.values(r.deductions).reduce((a, b) => a + b, 0) : 0}</span>
                    </div>
                  </div>
                  <Separator className="my-6" />
                  <div className="space-y-3">
                    <h3 className="font-semibold text-sm text-muted-foreground uppercase tracking-wider">Module Status</h3>
                    {([
                      ["metadata", "Metadata"],
                      ["ocr", "OCR / Text"],
                      ["qr", "QR Codes"],
                      ["tampering", "Tampering"],
                      ["signature", "Signature"],
                    ] as const).map(([key, label]) => {
                      const statusKey = `${key}_status` as keyof typeof r;
                      const status = r[statusKey] as string;
                      const isPassed = !["suspicious", "tampered", "error"].includes(status);
                      return (
                        <div key={key} className="flex items-center justify-between text-sm">
                          <span>{label}</span>
                          <Badge
                            variant={isPassed ? "outline" : "destructive"}
                            className={isPassed ? "text-green-600 border-green-600" : undefined}
                          >
                            {isPassed ? "Passed" : "Issues"}
                          </Badge>
                        </div>
                      );
                    })}
                  </div>
                  {r.blockchain && (
                    <>
                      <Separator className="my-6" />
                      <div className="space-y-2">
                        <h3 className="font-semibold text-sm text-muted-foreground uppercase tracking-wider">Blockchain</h3>
                        <div className="text-xs text-muted-foreground space-y-1">
                          <p className="truncate font-mono">Hash: {r.blockchain.blockchain_hash.slice(0, 20)}...</p>
                          <p>Block #{r.blockchain.block_number}</p>
                          <a
                            href={r.blockchain.verification_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-primary hover:underline inline-flex items-center gap-1"
                          >
                            Verify on Blockchain
                            <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                            </svg>
                          </a>
                        </div>
                      </div>
                    </>
                  )}
                </div>
              </div>

              <div className="lg:col-span-2 space-y-8">
                <VisualEvidence
                  previewB64={r.preview_b64}
                  markedImages={r.marked_images ?? undefined}
                  signatureImages={r.signature_images ?? undefined}
                  signatureCount={r.signature_count}
                  analyzedPages={r.analyzed_pages}
                />

                <div className="rounded-xl border bg-card p-6">
                  <h2 className="text-xl font-semibold mb-6">Findings & Evidence</h2>
                  <ScrollArea className="max-h-[600px] pr-4">
                    <DetailedReport
                      findings={r.findings}
                      deductions={r.deductions}
                    />
                  </ScrollArea>
                </div>
              </div>
            </div>

            <Separator />
            <ResultActions
              reportB64={r.report_b64}
              filename={result.filename}
              onReset={handleReset}
              onShare={handleShare}
            />
          </div>
        )}
      </main>

      <footer className="border-t border-border/40 mt-16">
        <div className="max-w-6xl mx-auto px-4 py-8 text-center">
          <p className="text-sm text-muted-foreground">
            <span>DOCVERIFY</span>{' '}<span className="text-primary">AI</span> — Advanced Document Forensics Platform
          </p>
          <p className="text-xs text-muted-foreground/60 mt-1">
            Powered by Multi-Layer Forensic Analysis &amp; Blockchain Verification
          </p>
        </div>
      </footer>
    </div>
  );
}
