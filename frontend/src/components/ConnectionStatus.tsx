"use client";

import { ConnectionState } from "livekit-client";
import { cn } from "@/lib/utils";

interface ConnectionStatusProps {
  state: ConnectionState;
}

const labels: Record<string, string> = {
  [ConnectionState.Connected]: "Connected",
  [ConnectionState.Connecting]: "Connecting",
  [ConnectionState.Reconnecting]: "Reconnecting",
  [ConnectionState.Disconnected]: "Disconnected",
};

export function ConnectionStatus({ state }: ConnectionStatusProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold",
        state === ConnectionState.Connected &&
          "bg-emerald-500/10 text-emerald-400",
        state === ConnectionState.Connecting &&
          "bg-amber-500/10 text-amber-400",
        state === ConnectionState.Reconnecting &&
          "bg-amber-500/10 text-amber-400",
        state === ConnectionState.Disconnected && "bg-red-500/10 text-red-400"
      )}
    >
      <span
        className={cn(
          "w-1.5 h-1.5 rounded-full",
          state === ConnectionState.Connected && "bg-emerald-400",
          state === ConnectionState.Connecting && "bg-amber-400 animate-pulse",
          state === ConnectionState.Reconnecting &&
            "bg-amber-400 animate-pulse",
          state === ConnectionState.Disconnected && "bg-red-400"
        )}
      />
      {labels[state] || "Unknown"}
    </span>
  );
}
