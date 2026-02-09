import { randomUUID } from "crypto";
import fs from "fs/promises";
import path from "path";

import { createSceneInNotion, loadSceneFromNotion } from "./notion";

// ---------------------------------------------------------------------------
// Types (must match Python app/models.py JSON schema exactly)
// ---------------------------------------------------------------------------

export interface Variant {
  id: string;
  text: string;
  source: string;
}

export interface Beat {
  id: string;
  speaker: "AI" | "ACTOR";
  character: string;
  canonical: string | null;
  variants: Variant[];
  active_variant_id: string | null;
}

export interface Scene {
  scene_id: string;
  title: string;
  characters: Record<string, string>;
  voice: Record<string, string>;
  beats: Beat[];
}

export interface SessionState {
  status: "IDLE" | "RUNNING" | "READY_TO_LOCK" | "LOCKING" | "LOCKED";
  beat_index: number;
  last_talk_turn: "AI" | "ACTOR" | null;
  style: {
    tension: number;
    warmth: number;
    pace: number;
    pause_ms: number;
  };
  transcript: unknown[];
  director_events: unknown[];
  locked_script_text: string | null;
  actor_latest_takes: Record<string, string>;
  locked_notes: string[] | null;
}

export interface CreateSceneInput {
  title: string;
  script_text: string;
  ai_character_name: string;
  ai_voice_id: string;
}

// ---------------------------------------------------------------------------
// Parser (mirrors app/parser.py)
// ---------------------------------------------------------------------------

export class ScriptParseError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ScriptParseError";
  }
}

export function parseScript(
  scriptText: string,
  aiCharacterName: string
): Beat[] {
  const aiName = aiCharacterName.trim();
  if (!aiName) {
    throw new ScriptParseError("AI character name is required.");
  }

  const beats: Beat[] = [];
  let beatCount = 0;
  let aiSeen = false;

  const lines = scriptText.split("\n");
  for (let lineNo = 0; lineNo < lines.length; lineNo++) {
    const line = lines[lineNo].trim();
    if (!line) continue;

    if (!line.includes(":")) {
      throw new ScriptParseError(
        `Line ${lineNo + 1}: invalid format '${line}'. Use 'CHARACTER: <line>'.`
      );
    }

    const colonIdx = line.indexOf(":");
    const character = line.slice(0, colonIdx).trim();
    const canonical = line.slice(colonIdx + 1).trim();

    if (!character) {
      throw new ScriptParseError(
        `Line ${lineNo + 1}: character name is empty.`
      );
    }

    const isAi = character.toLowerCase() === aiName.toLowerCase();
    if (isAi && !canonical) {
      throw new ScriptParseError(
        `Line ${lineNo + 1}: AI beat for '${character}' must include text.`
      );
    }

    beatCount++;
    beats.push({
      id: `b${beatCount}`,
      speaker: isAi ? "AI" : "ACTOR",
      character,
      canonical: canonical || null,
      variants: [],
      active_variant_id: null,
    });
    aiSeen = aiSeen || isAi;
  }

  if (beats.length === 0) {
    throw new ScriptParseError("Script is empty.");
  }
  if (!aiSeen) {
    throw new ScriptParseError(
      `No lines found for AI character '${aiName}'. Use that exact character name in script.`
    );
  }

  return beats;
}

// ---------------------------------------------------------------------------
// Storage — Notion-backed for scenes, file-based for sessions
// ---------------------------------------------------------------------------

function dataDir(): string {
  return process.env.SCENE_DATA_DIR || path.resolve(process.cwd(), "..", "data", "scenes");
}

function sceneDirPath(sceneId: string): string {
  return path.join(dataDir(), sceneId);
}

async function ensureDir(dirPath: string): Promise<void> {
  await fs.mkdir(dirPath, { recursive: true });
}

/**
 * Save a scene to Notion.
 * Also writes a local JSON copy for the Python agent to use as fallback.
 */
export async function saveScene(scene: Scene): Promise<void> {
  // Write to both Notion and local disk in parallel.
  // Neither is blocking — if one fails the other still succeeds.
  const localWrite = (async () => {
    const dir = sceneDirPath(scene.scene_id);
    await ensureDir(dir);
    await fs.writeFile(
      path.join(dir, "scene.json"),
      JSON.stringify(scene, null, 2),
      "utf-8"
    );
  })();

  const notionWrite =
    process.env.NOTION_TOKEN && process.env.NOTION_DATABASE_ID
      ? createSceneInNotion(scene).catch((err) =>
          console.warn("Failed to save scene to Notion:", err)
        )
      : Promise.resolve();

  await Promise.all([localWrite, notionWrite]);
}

/**
 * Load a scene from Notion, falling back to local disk.
 */
export async function loadScene(sceneId: string): Promise<Scene> {
  try {
    return await loadSceneFromNotion(sceneId);
  } catch {
    // Fallback to local file
    const filePath = path.join(sceneDirPath(sceneId), "scene.json");
    const data = await fs.readFile(filePath, "utf-8");
    return JSON.parse(data) as Scene;
  }
}

/** Session state is ephemeral — keep on disk. */
export async function saveSession(
  sceneId: string,
  state: SessionState
): Promise<void> {
  const dir = sceneDirPath(sceneId);
  await ensureDir(dir);
  await fs.writeFile(
    path.join(dir, "session.json"),
    JSON.stringify(state, null, 2),
    "utf-8"
  );
}

// ---------------------------------------------------------------------------
// Scene creation (mirrors the POST /api/scenes logic in app/routes.py)
// ---------------------------------------------------------------------------

export function defaultSessionState(): SessionState {
  return {
    status: "IDLE",
    beat_index: 0,
    last_talk_turn: null,
    style: { tension: 0.5, warmth: 0.0, pace: 1.0, pause_ms: 350 },
    transcript: [],
    director_events: [],
    locked_script_text: null,
    actor_latest_takes: {},
    locked_notes: null,
  };
}

export async function createScene(input: CreateSceneInput): Promise<Scene> {
  const beats = parseScript(input.script_text, input.ai_character_name);

  const actorNames = [
    ...new Set(
      beats
        .filter((b) => b.speaker === "ACTOR" && b.character)
        .map((b) => b.character)
    ),
  ].sort();
  const actorLabel = actorNames.length > 0 ? actorNames.join(", ") : "ACTOR";

  const sceneId = randomUUID();
  const scene: Scene = {
    scene_id: sceneId,
    title: input.title,
    characters: { AI: input.ai_character_name, ACTOR: actorLabel },
    voice: { ai_voice_id: input.ai_voice_id },
    beats,
  };

  await saveScene(scene);
  await saveSession(sceneId, defaultSessionState());

  return scene;
}
