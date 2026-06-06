"use client";

import { useState } from "react";
import type { Base64Image } from "@/lib/api";

interface VisualEvidenceProps {
  previewB64?: string;
  markedImages?: Base64Image[];
  signatureImages?: Base64Image[];
  signatureCount?: number;
  analyzedPages?: number;
}

export function VisualEvidence({
  previewB64,
  markedImages,
  signatureImages,
  signatureCount,
  analyzedPages,
}: VisualEvidenceProps) {
  const hasMarked = markedImages && markedImages.length > 0;
  const hasSignature = signatureImages && signatureImages.length > 0;

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

  const currentMarked =
    hasMarked && markedImages
      ? markedImages.find((p) => p.page === activePage) ||
        markedImages[0]
      : undefined;

  const currentSignature =
    hasSignature && signatureImages
      ? signatureImages.find((p) => p.page === activePage) ||
        signatureImages[0]
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
        {activeTab === "original" && previewB64 && (
          <div className="p-4">
            <img
              src={`data:image/png;base64,${previewB64}`}
              alt="Original document"
              className="w-full max-h-[500px] object-contain rounded-lg"
            />
          </div>
        )}
        {activeTab === "marked" && currentMarked && (
          <div className="p-4">
            <img
              src={`data:image/png;base64,${currentMarked.data}`}
              alt="ELA tamper heatmap"
              className="w-full max-h-[500px] object-contain rounded-lg"
            />
            <p className="text-xs text-muted-foreground mt-3 text-center">
              Red/blue areas indicate regions with inconsistent compression
              levels — potential tampering
            </p>
          </div>
        )}
        {activeTab === "signature" && currentSignature && (
          <div className="p-4">
            <img
              src={`data:image/png;base64,${currentSignature.data}`}
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
