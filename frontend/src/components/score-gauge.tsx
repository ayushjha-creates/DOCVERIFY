"use client";

import { cn } from "@/lib/utils";

interface ScoreGaugeProps {
  score: number;
  size?: "sm" | "lg";
}

export function ScoreGauge({ score, size = "lg" }: ScoreGaugeProps) {
  const isLarge = size === "lg";
  const radius = isLarge ? 110 : 70;
  const strokeWidth = isLarge ? 16 : 12;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (score / 100) * circumference;

  const getColor = (s: number) => {
    if (s >= 80) return { stroke: "#22c55e", bg: "rgba(34,197,94,0.15)", text: "text-green-500" };
    if (s >= 40) return { stroke: "#eab308", bg: "rgba(234,179,8,0.15)", text: "text-yellow-500" };
    return { stroke: "#ef4444", bg: "rgba(239,68,68,0.15)", text: "text-red-500" };
  };

  const getLabel = (s: number) => {
    if (s >= 80) return "Genuine";
    if (s >= 40) return "Suspicious";
    return "Tampered";
  };

  const color = getColor(score);
  const label = getLabel(score);

  return (
    <div className="flex flex-col items-center gap-2">
      <div className="relative" style={{ width: (radius + strokeWidth) * 2, height: (radius + strokeWidth) * 2 }}>
        <svg
          width="100%"
          height="100%"
          viewBox={`0 0 ${(radius + strokeWidth) * 2} ${(radius + strokeWidth) * 2}`}
          className="transform -rotate-90"
        >
          <circle
            cx={radius + strokeWidth}
            cy={radius + strokeWidth}
            r={radius}
            fill="none"
            stroke={color.bg}
            strokeWidth={strokeWidth}
          />
          <circle
            cx={radius + strokeWidth}
            cy={radius + strokeWidth}
            r={radius}
            fill="none"
            stroke={color.stroke}
            strokeWidth={strokeWidth}
            strokeDasharray={circumference}
            strokeDashoffset={offset}
            strokeLinecap="round"
            className="transition-all duration-1000 ease-out"
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className={cn("font-bold tracking-tight", isLarge ? "text-5xl" : "text-3xl", color.text)}>
            {score}%
          </span>
          <span className={cn("font-semibold mt-1", isLarge ? "text-lg" : "text-sm", color.text)}>
            {label}
          </span>
        </div>
      </div>
    </div>
  );
}
