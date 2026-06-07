"use client";

import { useCallback, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface UploadSectionProps {
  onFileSelect: (file: File) => void;
}

export function UploadSection({ onFileSelect }: UploadSectionProps) {
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleDrag = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
  }, []);

  const handleDragIn = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragging(true);
  }, []);

  const handleDragOut = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragging(false);
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      e.stopPropagation();
      setDragging(false);
      const files = Array.from(e.dataTransfer.files);
      const file = files.find(
        (f) =>
          f.type === "application/pdf" ||
          f.type.startsWith("image/")
      );
      if (file) onFileSelect(file);
    },
    [onFileSelect]
  );

  const handleClick = () => inputRef.current?.click();

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) onFileSelect(file);
  };

  return (
    <div
      className={cn(
        "relative flex flex-col items-center justify-center w-full max-w-xl mx-auto p-12 rounded-2xl border-2 border-dashed transition-all duration-300 cursor-pointer",
        dragging
          ? "border-primary bg-primary/5 scale-[1.02]"
          : "border-muted-foreground/25 hover:border-primary/50 hover:bg-muted/30"
      )}
      onDragEnter={handleDragIn}
      onDragLeave={handleDragOut}
      onDragOver={handleDrag}
      onDrop={handleDrop}
      onClick={handleClick}
    >
      <input
        ref={inputRef}
        type="file"
        accept=".pdf,.png,.jpg,.jpeg,.tiff,.bmp"
        className="hidden"
        onChange={handleChange}
      />
      <div className="mb-6 relative">
        <div className="w-20 h-20 rounded-full bg-primary/10 flex items-center justify-center mx-auto">
          <svg
            className="w-10 h-10 text-primary"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={1.5}
              d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"
            />
          </svg>
        </div>
      </div>
      <p className="text-lg font-semibold mb-2">
        {dragging ? "Drop your document here" : "Upload Document"}
      </p>
      <p className="text-sm text-muted-foreground text-center mb-6 max-w-sm">
        Drag & drop your PDF, certificate, receipt, or invoice here, or click to browse
      </p>
      <Button variant="default" size="lg" className="gap-2">
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M12 4v16m8-8H4"
          />
        </svg>
        Browse Files
      </Button>
      <p className="mt-4 text-xs text-muted-foreground">
        Supports PDF, PNG, JPG, TIFF (max 20MB)
      </p>
    </div>
  );
}
