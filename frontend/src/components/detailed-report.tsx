"use client";

import { Finding } from "@/lib/api";
import { Badge } from "@/components/ui/badge";

interface DetailedReportProps {
  findings: Record<string, Finding[]>;
  deductions: Record<string, number>;
}

const moduleLabels: Record<string, string> = {
  metadata: "Metadata Analysis",
  ocr: "OCR & Text Analysis",
  qr: "QR Code Verification",
  tampering: "Image Tampering Detection",
  signature: "Signature / Stamp Verification",
};

const moduleIcons: Record<string, string> = {
  metadata: "📄",
  ocr: "🔤",
  qr: "📱",
  tampering: "🔍",
  signature: "✍️",
};

const moduleDescriptions: Record<string, string> = {
  metadata: "File properties, creation date, author metadata",
  ocr: "Font consistency, alignment, text anomalies, suspicious keywords",
  qr: "Embedded QR code integrity and data verification",
  tampering: "ELA, noise patterns, copy-paste detection, blur analysis",
  signature: "Signature and stamp detection, placement verification",
};

function SeverityIcon({ severity, type }: { severity: string; type: string }) {
  if (type === "info") {
    return (
      <svg className="w-5 h-5 text-green-500 shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
    );
  }
  if (severity === "high") {
    return (
      <svg className="w-5 h-5 text-red-500 shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
    );
  }
  if (severity === "medium") {
    return (
      <svg className="w-5 h-5 text-orange-400 shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
      </svg>
    );
  }
  return (
    <svg className="w-5 h-5 text-green-500 shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
    </svg>
  );
}

function SeverityBadge({ severity }: { severity: string }) {
  const colors: Record<string, string> = {
    minor: "bg-green-100 text-green-700 border-green-200",
    medium: "bg-orange-100 text-orange-700 border-orange-200",
    high: "bg-red-100 text-red-700 border-red-200",
  };
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium border ${colors[severity] || "bg-gray-100 text-gray-700"}`}>
      {severity === "high" ? "High" : severity === "medium" ? "Medium" : "Info"}
    </span>
  );
}

export function DetailedReport({ findings, deductions }: DetailedReportProps) {
  const moduleEntries = Object.entries(moduleLabels);

  return (
    <div className="space-y-5">
      {moduleEntries.map(([key, label]) => {
        const items = findings[key] || [];
        const deduction = (deductions && deductions[key]) || 0;

        const hasError = items.some((f) => f.type === "error");
        const hasWarning = items.some((f) => f.type === "warning");

        return (
          <div key={key} className={`rounded-xl border bg-card overflow-hidden ${hasError ? "border-red-200" : hasWarning ? "border-orange-200" : "border-green-200"}`}>
            {/* Header */}
            <div className="flex items-center justify-between px-5 py-4 border-b bg-muted/20">
              <div className="flex items-center gap-3">
                <span className="text-2xl">{moduleIcons[key]}</span>
                <div>
                  <h3 className="font-semibold text-foreground text-base">{label}</h3>
                  <p className="text-xs text-muted-foreground">{moduleDescriptions[key]}</p>
                </div>
              </div>
              <div className="flex items-center gap-3">
                {hasError && <Badge variant="destructive">Issues Found</Badge>}
                {hasWarning && !hasError && <Badge variant="secondary">Warnings</Badge>}
                {!hasError && !hasWarning && <Badge variant="outline" className="text-green-600 border-green-600 bg-green-50">Passed</Badge>}
                {deduction > 0 && (
                  <span className="text-sm font-bold text-destructive bg-destructive/10 px-2.5 py-1 rounded-md">
                    -{deduction} pts
                  </span>
                )}
                {deduction === 0 && items.length > 0 && (
                  <span className="text-xs text-green-600 font-medium">+0 pts</span>
                )}
              </div>
            </div>

            {/* Items */}
            {items.length > 0 && (
              <div className="divide-y">
                {items.map((finding, idx) => (
                  <div key={idx} className={`px-5 py-3.5 flex gap-3 ${finding.type === "error" ? "bg-red-50/30" : finding.type === "warning" ? "bg-orange-50/20" : ""}`}>
                    <SeverityIcon severity={finding.severity} type={finding.type} />
                    <div className="flex-1 min-w-0">
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0">
                          <p className="text-sm font-medium text-foreground">
                            {finding.title}
                            {finding.field_location && (
                              <span className="text-muted-foreground font-normal"> &mdash; <span className="font-mono text-xs bg-muted px-1.5 py-0.5 rounded">{finding.field_location}</span></span>
                            )}
                          </p>
                          <p className="text-xs text-muted-foreground mt-0.5">{finding.detail}</p>
                          <div className="flex items-center gap-2 mt-1.5 flex-wrap">
                            <SeverityBadge severity={finding.severity} />
                            {finding.page && finding.page > 0 && (
                              <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-blue-50 text-blue-700 border border-blue-200">
                                Page {finding.page}
                              </span>
                            )}
                            {finding.points > 0 && (
                              <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-red-50 text-red-700 border border-red-200">
                                -{finding.points} pts
                              </span>
                            )}
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* Empty state */}
            {items.length === 0 && (
              <div className="px-5 py-4 text-sm text-muted-foreground">
                No findings for this module.
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
