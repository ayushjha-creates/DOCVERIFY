"use client";

import { useState } from "react";

interface PageImage {
  page: number;
  url: string;
}

interface VisualEvidenceProps {
  originalUrl: string;
  markedImageUrls?: PageImage[];
  signatureImageUrls?: PageImage[];
  signatureCount?: number;
  analyzedPages?: number;
}

export function VisualEvidence({
  originalUrl,
  markedImageUrls,
  signatureImageUrls,
  signatureCount,
  analyzedPages,
}: VisualEvidenceProps) {
  const hasMarked = markedImageUrls && markedImageUrls.length > 0;
  const hasSignature = signatureImageUrls && signatureImageUrls.length > 0;

  const tabs: { key: string; label: string }[] = [
    { key: "original", label: "Original Document" },
  ];
  if (hasMarked) {
    tabs.push({ key: "marked", label: "Tamper Heatmap (ELA)" });
  }
  if (hasSignature) {
    tabs.push({
      key: "signature",
      label: `Signatures (${signatureCount || 0})`,
    });
  }

  const [activeTab, setActiveTab] = useState(tabs[0]?.key || "original");
  const [activePage, setActivePage] = useState(1);

  const currentMarkedUrl =
    hasMarked && markedImageUrls
      ? markedImageUrls.find((p) => p.page === activePage)?.url ||
        markedImageUrls[0]?.url
      : undefined;

  const currentSignatureUrl =
    hasSignature && signatureImageUrls
      ? signatureImageUrls.find((p) => p.page === activePage)?.url ||
        signatureImageUrls[0]?.url
      : undefined;

  const totalPages = analyzedPages || 1;

  return (
    <div className="space-y-4">
      <div className="flex gap-2 flex-wrap">
        {tabs.map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
              activeTab === tab.key
                ? "bg-primary text-primary-foreground"
                : "bg-muted hover:bg-muted/80"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {totalPages > 1 && activeTab !== "original" && (
        <div className="flex gap-1 items-center text-sm text-muted-foreground">
          <span>Page:</span>
          {Array.from({ length: totalPages }, (_, i) => i + 1).map((p) => (
            <button
              key={p}
              onClick={() => setActivePage(p)}
              className={`px-2.5 py-1 rounded text-xs font-medium transition-colors ${
                activePage === p
                  ? "bg-primary text-primary-foreground"
                  : "bg-muted hover:bg-muted/80"
              }`}
            >
              {p}
            </button>
          ))}
        </div>
      )}

      <div className="rounded-xl border bg-card overflow-hidden">
        {activeTab === "original" && (
          <div className="p-4">
            <img
              src={originalUrl}
              alt="Original document"
              className="w-full max-h-[500px] object-contain rounded-lg"
            />
          </div>
        )}
        {activeTab === "marked" && currentMarkedUrl && (
          <div className="p-4">
            <img
              src={currentMarkedUrl}
              alt="ELA tamper heatmap"
              className="w-full max-h-[500px] object-contain rounded-lg"
            />
            <p className="text-xs text-muted-foreground mt-3 text-center">
              Red/blue areas indicate regions with inconsistent compression
              levels — potential tampering
            </p>
          </div>
        )}
        {activeTab === "signature" && currentSignatureUrl && (
          <div className="p-4">
            <img
              src={currentSignatureUrl}
              alt="Signature detection overlay"
              className="w-full max-h-[500px] object-contain rounded-lg"
            />
            <p className="text-xs text-muted-foreground mt-3 text-center">
              Red boxes = detected signatures, Green boxes = detected stamps
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
