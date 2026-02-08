"use client";

import { useEffect, useRef } from "react";
import type { TranscriptEvent } from "@/hooks/useTableReadStatus";

interface TranscriptPanelProps {
  transcript: TranscriptEvent[];
}

export function TranscriptPanel({ transcript }: TranscriptPanelProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [transcript]);

  return (
    <div className="flex flex-col h-full">
      <h2 className="text-sm font-semibold text-[var(--muted-foreground)] uppercase tracking-wider px-4 py-3 border-b border-[var(--border)]">
        Transcript
      </h2>
      <div ref={containerRef} className="flex-1 overflow-y-auto p-4 space-y-2">
        {transcript.length === 0 && (
          <p className="text-sm text-[var(--muted)] italic">
            Waiting for dialogue...
          </p>
        )}
        {transcript.map((event, idx) => (
          <div key={idx} className="text-sm animate-fade-in">
            <span className="font-semibold text-[var(--accent)]">
              {event.meta?.character || event.speaker}:
            </span>{" "}
            <span className="text-[var(--foreground)]">{event.text}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
