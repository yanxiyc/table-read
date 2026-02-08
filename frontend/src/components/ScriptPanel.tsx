"use client";

import { useEffect, useRef } from "react";
import { cn } from "@/lib/utils";
import type { BeatInfo } from "@/hooks/useTableReadStatus";

interface ScriptPanelProps {
  beats: BeatInfo[];
  currentBeatIndex: number;
}

export function ScriptPanel({ beats, currentBeatIndex }: ScriptPanelProps) {
  const listRef = useRef<HTMLOListElement>(null);
  const currentRef = useRef<HTMLLIElement>(null);

  useEffect(() => {
    currentRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [currentBeatIndex]);

  return (
    <div className="flex flex-col h-full">
      <h2 className="text-sm font-semibold text-[var(--muted-foreground)] uppercase tracking-wider px-4 py-3 border-b border-[var(--border)]">
        Script
      </h2>
      <ol ref={listRef} className="flex-1 overflow-y-auto p-2 space-y-1">
        {beats.map((beat, idx) => {
          const isCurrent = idx === currentBeatIndex;
          const activeVariant = beat.active_variant_id
            ? beat.variants?.find((v) => v.id === beat.active_variant_id)
            : null;
          const text =
            beat.speaker === "AI"
              ? activeVariant?.text || beat.canonical || ""
              : beat.canonical || "";
          const label = beat.character || beat.speaker;

          return (
            <li
              key={idx}
              ref={isCurrent ? currentRef : undefined}
              className={cn(
                "px-3 py-2 rounded-lg text-sm transition-colors",
                isCurrent
                  ? "bg-[var(--accent)]/10 border border-[var(--accent)]/30 text-[var(--foreground)]"
                  : idx < currentBeatIndex
                    ? "text-[var(--muted)] opacity-60"
                    : "text-[var(--muted-foreground)]"
              )}
            >
              <span
                className={cn(
                  "font-semibold",
                  isCurrent && "text-[var(--accent)]"
                )}
              >
                {label}:
              </span>{" "}
              {text}
            </li>
          );
        })}
      </ol>
    </div>
  );
}
