"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function CreateScenePage() {
  const router = useRouter();
  const [title, setTitle] = useState("");
  const [aiCharacterName, setAiCharacterName] = useState("");
  const [voiceId, setVoiceId] = useState("");
  const [scriptText, setScriptText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      const res = await fetch(`${API_URL}/api/scenes`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title,
          ai_character_name: aiCharacterName,
          ai_voice_id: voiceId,
          script_text: scriptText,
        }),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `Request failed: ${res.status}`);
      }

      const data = await res.json();
      router.push(`/scene/${data.scene_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create scene");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="min-h-screen flex items-center justify-center p-6">
      <div className="w-full max-w-xl space-y-6">
        <div className="text-center space-y-2">
          <h1 className="text-3xl font-bold tracking-tight">Table Read</h1>
          <p className="text-[var(--muted-foreground)] text-sm">
            Create a scene to start your AI-powered rehearsal
          </p>
        </div>

        <form
          onSubmit={handleSubmit}
          className="space-y-4 bg-[var(--card)] border border-[var(--border)] rounded-xl p-6"
        >
          <div className="space-y-1.5">
            <label htmlFor="title" className="text-sm font-medium">
              Scene Title
            </label>
            <input
              id="title"
              type="text"
              required
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g. Romeo & Juliet — Balcony Scene"
              className="w-full px-3 py-2 rounded-lg bg-[var(--background)] border border-[var(--border)] text-sm focus:outline-none focus:ring-2 focus:ring-[var(--accent)] transition"
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <label htmlFor="character" className="text-sm font-medium">
                AI Character Name
              </label>
              <input
                id="character"
                type="text"
                required
                value={aiCharacterName}
                onChange={(e) => setAiCharacterName(e.target.value)}
                placeholder="e.g. Juliet"
                className="w-full px-3 py-2 rounded-lg bg-[var(--background)] border border-[var(--border)] text-sm focus:outline-none focus:ring-2 focus:ring-[var(--accent)] transition"
              />
            </div>
            <div className="space-y-1.5">
              <label htmlFor="voiceId" className="text-sm font-medium">
                Voice ID
              </label>
              <input
                id="voiceId"
                type="text"
                required
                value={voiceId}
                onChange={(e) => setVoiceId(e.target.value)}
                placeholder="Cartesia voice ID"
                className="w-full px-3 py-2 rounded-lg bg-[var(--background)] border border-[var(--border)] text-sm focus:outline-none focus:ring-2 focus:ring-[var(--accent)] transition"
              />
            </div>
          </div>

          <div className="space-y-1.5">
            <label htmlFor="script" className="text-sm font-medium">
              Script
            </label>
            <textarea
              id="script"
              required
              rows={10}
              value={scriptText}
              onChange={(e) => setScriptText(e.target.value)}
              placeholder={`CHARACTER_NAME: Their line here\nAI_CHARACTER: AI's response line\n...`}
              className="w-full px-3 py-2 rounded-lg bg-[var(--background)] border border-[var(--border)] text-sm font-mono focus:outline-none focus:ring-2 focus:ring-[var(--accent)] transition resize-y"
            />
          </div>

          {error && (
            <div className="text-sm text-[var(--destructive)] bg-[var(--destructive)]/10 border border-[var(--destructive)]/20 rounded-lg px-3 py-2">
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full py-2.5 rounded-lg bg-[var(--accent)] text-white font-medium text-sm hover:opacity-90 disabled:opacity-50 transition"
          >
            {loading ? "Creating..." : "Create Scene"}
          </button>
        </form>
      </div>
    </main>
  );
}
