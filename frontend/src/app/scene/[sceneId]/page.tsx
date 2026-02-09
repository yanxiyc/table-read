"use client";

import { useCallback, useEffect, useState } from "react";
import { use } from "react";
import {
  LiveKitRoom,
  RoomAudioRenderer,
  TrackToggle,
  useConnectionState,
} from "@livekit/components-react";
import "@livekit/components-styles";
import { Track } from "livekit-client";
import { Mic, MicOff, PhoneOff } from "lucide-react";
import { RehearsalPanel } from "@/components/RehearsalPanel";
import { ConnectionStatus } from "@/components/ConnectionStatus";

interface Scene {
  scene_id: string;
  title: string;
  characters: Record<string, string>;
  beats: Array<{
    speaker: string;
    character?: string;
    canonical?: string;
    active_variant_id?: string;
    variants?: Array<{ id: string; text: string }>;
  }>;
}

interface TokenResponse {
  token: string;
  serverUrl: string;
  room: string;
}

export default function ScenePage({
  params,
}: {
  params: Promise<{ sceneId: string }>;
}) {
  const { sceneId } = use(params);
  const [scene, setScene] = useState<Scene | null>(null);
  const [tokenData, setTokenData] = useState<TokenResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [connecting, setConnecting] = useState(false);

  useEffect(() => {
    fetch(`/api/scenes/${sceneId}`)
      .then((res) => {
        if (!res.ok) throw new Error("Scene not found");
        return res.json();
      })
      .then(setScene)
      .catch((err) => setError(err.message));
  }, [sceneId]);

  const handleConnect = useCallback(async () => {
    setConnecting(true);
    setError(null);
    try {
      // Get LiveKit token (agent handles scene start on connect)
      const res = await fetch("/api/token", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sceneId }),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.error || "Failed to get token");
      }

      setTokenData(await res.json());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Connection failed");
      setConnecting(false);
    }
  }, [sceneId]);

  if (error && !scene) {
    return (
      <main className="min-h-screen flex items-center justify-center">
        <div className="text-center space-y-2">
          <p className="text-[var(--destructive)]">{error}</p>
          <a href="/" className="text-sm text-[var(--accent)] underline">
            Back to home
          </a>
        </div>
      </main>
    );
  }

  if (!scene) {
    return (
      <main className="min-h-screen flex items-center justify-center">
        <p className="text-[var(--muted)]">Loading scene...</p>
      </main>
    );
  }

  // Pre-connection state
  if (!tokenData) {
    return (
      <main className="min-h-screen flex items-center justify-center p-6">
        <div className="w-full max-w-md text-center space-y-6">
          <div className="space-y-2">
            <h1 className="text-2xl font-bold tracking-tight">
              {scene.title}
            </h1>
            <p className="text-sm text-[var(--muted-foreground)]">
              {Object.values(scene.characters).join(" & ")} &middot;{" "}
              {scene.beats.length} beats
            </p>
          </div>

          {error && (
            <div className="text-sm text-[var(--destructive)] bg-[var(--destructive)]/10 border border-[var(--destructive)]/20 rounded-lg px-3 py-2">
              {error}
            </div>
          )}

          <button
            onClick={handleConnect}
            disabled={connecting}
            className="px-6 py-3 rounded-xl bg-[var(--accent)] text-white font-medium hover:opacity-90 disabled:opacity-50 transition"
          >
            {connecting ? "Connecting..." : "Connect & Start Rehearsal"}
          </button>

          <a
            href="/"
            className="block text-sm text-[var(--muted-foreground)] hover:text-[var(--foreground)] transition"
          >
            &larr; Create another scene
          </a>
        </div>
      </main>
    );
  }

  // Connected state: LiveKit room
  return (
    <LiveKitRoom
      token={tokenData.token}
      serverUrl={tokenData.serverUrl}
      connect={true}
      audio={true}
      className="min-h-screen"
    >
      <RoomAudioRenderer />
      <div className="min-h-screen flex flex-col">
        <SceneHeader scene={scene} />
        <RehearsalPanel scene={scene} />
      </div>
    </LiveKitRoom>
  );
}

function SceneHeader({ scene }: { scene: Scene }) {
  const connectionState = useConnectionState();

  return (
    <header className="flex items-center justify-between px-4 py-3 border-b border-[var(--border)] bg-[var(--card)]">
      <div className="flex items-center gap-3">
        <h1 className="text-lg font-semibold">{scene.title}</h1>
        <ConnectionStatus state={connectionState} />
      </div>
      <div className="flex items-center gap-2">
        <TrackToggle
          source={Track.Source.Microphone}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm border border-[var(--border)] hover:bg-[var(--border)] transition"
        >
          <Mic className="w-4 h-4" />
        </TrackToggle>
      </div>
    </header>
  );
}
