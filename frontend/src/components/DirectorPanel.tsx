"use client";

import { cn } from "@/lib/utils";
import type { DirectorFeedback } from "@/hooks/useTableReadStatus";

interface DirectorPanelProps {
  feedback: DirectorFeedback | null;
}

const engagementWidths: Record<string, string> = {
  low: "w-1/3",
  medium: "w-2/3",
  high: "w-full",
};

const engagementColors: Record<string, string> = {
  low: "bg-amber-500",
  medium: "bg-blue-500",
  high: "bg-emerald-500",
};

export function DirectorPanel({ feedback }: DirectorPanelProps) {
  if (!feedback) {
    return (
      <div className="flex flex-col h-full">
        <h2 className="text-sm font-semibold text-[var(--muted-foreground)] uppercase tracking-wider px-4 py-3 border-b border-[var(--border)]">
          AI Director
        </h2>
        <div className="flex-1 flex items-center justify-center p-4">
          <p className="text-sm text-[var(--muted)] italic">
            Waiting for performance...
          </p>
        </div>
      </div>
    );
  }

  const isActing = feedback.is_acting;
  const engagement = feedback.emotional_engagement || "low";

  return (
    <div className="flex flex-col h-full">
      <h2 className="text-sm font-semibold text-[var(--muted-foreground)] uppercase tracking-wider px-4 py-3 border-b border-[var(--border)]">
        AI Director
      </h2>
      <div className="flex-1 p-4 space-y-4">
        {/* Verdict + Rating row */}
        <div className="flex items-center justify-between">
          <span
            className={cn(
              "inline-flex px-3 py-1 rounded-full text-xs font-bold uppercase tracking-wide",
              isActing
                ? "bg-teal-500/15 text-teal-400 border border-teal-500/30 animate-pulse-acting"
                : "bg-amber-500/15 text-amber-400 border border-amber-500/30 animate-pulse-narrating"
            )}
          >
            {isActing ? "Acting" : "Reading"}
          </span>
          <span className="text-2xl font-bold text-[var(--accent)]">
            {feedback.overall_rating ?? "--"}/10
          </span>
        </div>

        {/* Engagement meter */}
        <div className="space-y-1.5">
          <div className="flex justify-between text-xs">
            <span className="text-[var(--muted-foreground)]">Engagement</span>
            <span className="font-medium capitalize">{engagement}</span>
          </div>
          <div className="h-2 bg-[var(--border)] rounded-full overflow-hidden">
            <div
              className={cn(
                "h-full rounded-full transition-all duration-500",
                engagementWidths[engagement],
                engagementColors[engagement]
              )}
            />
          </div>
        </div>

        {/* Director note */}
        <div className="p-3 rounded-lg bg-[var(--background)] border border-[var(--border)] text-sm italic text-[var(--muted-foreground)]">
          {feedback.director_note || "No notes."}
        </div>
      </div>
    </div>
  );
}
