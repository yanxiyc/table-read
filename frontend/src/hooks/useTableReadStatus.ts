"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRoomContext } from "@livekit/components-react";
import { RpcInvocationData } from "livekit-client";

export interface TranscriptEvent {
  speaker: string;
  text: string;
  meta?: {
    character?: string;
    beat_index?: number;
  };
}

export interface BeatInfo {
  speaker: string;
  character?: string;
  canonical?: string;
  active_variant_id?: string;
  variants?: Array<{ id: string; text: string }>;
}

export interface BeatState {
  beat_index: number;
  status: string;
  transcript: TranscriptEvent[];
  beats?: BeatInfo[];
  locked_script_text?: string;
  locked_notes?: string[];
}

export interface DirectorFeedback {
  is_acting: boolean;
  is_narrating: boolean;
  emotional_engagement: "low" | "medium" | "high";
  overall_rating: number;
  director_note: string;
}

export interface LockedScript {
  locked_script_text: string;
  locked_notes: string[];
}

export function useTableReadStatus() {
  const room = useRoomContext();
  const [beatState, setBeatState] = useState<BeatState | null>(null);
  const [directorFeedback, setDirectorFeedback] =
    useState<DirectorFeedback | null>(null);
  const [lockedScript, setLockedScript] = useState<LockedScript | null>(null);
  const registeredRef = useRef(false);

  useEffect(() => {
    if (!room?.localParticipant || registeredRef.current) return;
    registeredRef.current = true;

    // RPC: beat_update
    room.localParticipant.registerRpcMethod(
      "beat_update",
      async (data: RpcInvocationData) => {
        try {
          const parsed = JSON.parse(data.payload) as BeatState;
          setBeatState(parsed);
        } catch (e) {
          console.error("Failed to parse beat_update:", e);
        }
        return JSON.stringify({ ok: true });
      }
    );

    // RPC: director_feedback
    room.localParticipant.registerRpcMethod(
      "director_feedback",
      async (data: RpcInvocationData) => {
        try {
          const parsed = JSON.parse(data.payload) as DirectorFeedback;
          setDirectorFeedback(parsed);
        } catch (e) {
          console.error("Failed to parse director_feedback:", e);
        }
        return JSON.stringify({ ok: true });
      }
    );

    // Byte stream: locked_script
    room.registerByteStreamHandler("locked_script", async (reader) => {
      try {
        const chunks = await reader.readAll();
        const decoder = new TextDecoder();
        const text = chunks.map((c) => decoder.decode(c, { stream: true })).join("") + decoder.decode();
        const data = JSON.parse(text) as LockedScript;
        setLockedScript(data);
      } catch (e) {
        console.error("Failed to handle locked_script stream:", e);
      }
    });
  }, [room]);

  const reset = useCallback(() => {
    setBeatState(null);
    setDirectorFeedback(null);
    setLockedScript(null);
    registeredRef.current = false;
  }, []);

  return { beatState, directorFeedback, lockedScript, reset };
}
