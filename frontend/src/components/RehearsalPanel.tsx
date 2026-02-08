"use client";

import { useTableReadStatus } from "@/hooks/useTableReadStatus";
import { ScriptPanel } from "./ScriptPanel";
import { TranscriptPanel } from "./TranscriptPanel";
import { DirectorPanel } from "./DirectorPanel";
import { LockedOutput } from "./LockedOutput";

interface Scene {
  beats: Array<{
    speaker: string;
    character?: string;
    canonical?: string;
    active_variant_id?: string;
    variants?: Array<{ id: string; text: string }>;
  }>;
}

interface RehearsalPanelProps {
  scene: Scene;
}

export function RehearsalPanel({ scene }: RehearsalPanelProps) {
  const { beatState, directorFeedback, lockedScript } = useTableReadStatus();

  const beats = beatState?.beats || scene.beats;
  const currentBeatIndex = beatState?.beat_index ?? -1;
  const transcript = beatState?.transcript || [];

  return (
    <div className="flex-1 flex flex-col gap-3 p-3 overflow-hidden">
      {/* Main grid */}
      <div className="flex-1 grid grid-cols-1 lg:grid-cols-3 gap-3 min-h-0">
        {/* Script panel — left column */}
        <div className="lg:col-span-1 bg-[var(--card)] border border-[var(--border)] rounded-xl overflow-hidden">
          <ScriptPanel beats={beats} currentBeatIndex={currentBeatIndex} />
        </div>

        {/* Right column: transcript + director */}
        <div className="lg:col-span-2 flex flex-col gap-3 min-h-0">
          <div className="flex-1 bg-[var(--card)] border border-[var(--border)] rounded-xl overflow-hidden">
            <TranscriptPanel transcript={transcript} />
          </div>
          <div className="h-64 lg:h-72 bg-[var(--card)] border border-[var(--border)] rounded-xl overflow-hidden">
            <DirectorPanel feedback={directorFeedback} />
          </div>
        </div>
      </div>

      {/* Locked output (appears when scene is locked) */}
      <LockedOutput lockedScript={lockedScript} />
    </div>
  );
}
