"use client";

import type { LockedScript } from "@/hooks/useTableReadStatus";

interface LockedOutputProps {
  lockedScript: LockedScript | null;
}

export function LockedOutput({ lockedScript }: LockedOutputProps) {
  if (!lockedScript) return null;

  return (
    <div className="animate-fade-in border border-[var(--accent)]/30 rounded-xl bg-[var(--card)] overflow-hidden">
      <div className="px-4 py-3 border-b border-[var(--border)] bg-[var(--accent)]/5">
        <h2 className="text-sm font-semibold text-[var(--accent)] uppercase tracking-wider">
          Locked Script
        </h2>
      </div>
      <div className="p-4 space-y-4">
        <pre className="whitespace-pre-wrap text-sm font-mono text-[var(--foreground)] leading-relaxed">
          {lockedScript.locked_script_text}
        </pre>

        {lockedScript.locked_notes && lockedScript.locked_notes.length > 0 && (
          <div className="space-y-2">
            <h3 className="text-xs font-semibold text-[var(--muted-foreground)] uppercase tracking-wider">
              Notes
            </h3>
            <ul className="space-y-1">
              {lockedScript.locked_notes.map((note, idx) => (
                <li
                  key={idx}
                  className="text-sm text-[var(--muted-foreground)] pl-3 border-l-2 border-[var(--border)]"
                >
                  {note}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
}
