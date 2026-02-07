# MVP Architecture Spec (2 roles): Director-driven Voice Rehearsal (Cartesia + Python)

## Goal

Build a demo app where a director creates a scene (script + casting), presses **Start Scene**, and the system runs a hands-free rehearsal loop:

1. AI speaks scripted line (Character AI)
2. Actor replies (mic)
3. AI speaks next scripted line
4. Actor replies
5. Director can interject with **“reader ...”** commands to modify performance, rewrite lines, or rewind the scene.
6. Director ends with **“ok scene, lock this version”** → stops and outputs updated script + take notes.

### Constraints (MVP)

* Single scene; script is plain text or JSON beats.
* Only one mic input (director + actor share mic).
* Director intent is primarily detected by spoken cue **“reader”**, but system also listens for "stop/again" commands during pauses.
* Actor lines don’t need to match script; just transcribe and log.
* AI lines are driven by script beats + optional variants.
* Minimal UI (FastAPI-served HTML) is fine.

---

## Components

### 1) Web UI (Minimal)

Two pages:

**/create**

* Scene title
* Script input (textarea or upload)
* Character names:
  * AI character name (e.g., “MOTHER”)
  * Actor character name (e.g., “YOU”)
* Cartesia voice_id for AI character
* Button: Save scene → returns `scene_id`

**/scene/{scene_id}**

* Button: Start Scene
* **Active Script Panel**: Displays the full script. **Highlights the current beat** (AI or Actor).
* Transcript panel (log of what was actually said/detected).
* Status badge: IDLE / RUNNING / LOCKED
* After lock: show “Locked Script” + “Notes”

---

## Script Format (Simple)

Plain text with alternating beats. For MVP, require explicit tags:

Example `script.txt`:

```
AI: You’re late.
ACTOR:
AI: Don’t do this here.
ACTOR:
AI: Fine. Say it.
ACTOR:
```

Parsing rules:

* Line starts with `AI:` → AI beat with text
* Line equals `ACTOR:` → actor turn placeholder

---

## Data Model

### Scene JSON

```json
{
  "scene_id": "uuid",
  "title": "kitchen_tense",
  "characters": {"AI":"MOTHER","ACTOR":"YOU"},
  "voice": {"ai_voice_id":"cartesia_voice_123"},
  "beats": [
    {"id":"b1","speaker":"AI","canonical":"You’re late.","variants":[],"active_variant":null},
    {"id":"b2","speaker":"ACTOR"},
    {"id":"b3","speaker":"AI","canonical":"Don’t do this here.","variants":[],"active_variant":null},
    {"id":"b4","speaker":"ACTOR"}
  ]
}
```

### Session State (in-memory; persist on lock)

```python
SessionState:
  status: IDLE|RUNNING|LOCKING|LOCKED
  beat_index: int
  last_talk_turn: "AI" | "ACTOR" | None
  style:
    tension: float  # 0..1
    warmth: float   # -1..1
    pace: float     # ~0.8..1.2
    pause_ms: int
  transcript: list[{ts, speaker, text, meta}]
  director_events: list[{ts, cmd, target_beat_id, applied}]
  locked_script_text: str | None
  actor_latest_takes: dict[str, str] # map beat_id -> transcription text
  locked_notes: list[str] | None
```

Persist under `data/scenes/{scene_id}/`.

---

## Backend (FastAPI)

### Endpoints

* `POST /api/scenes` → create and store scene from script/config, return `scene_id`
* `GET /api/scenes/{scene_id}` → fetch scene
* `POST /api/scenes/{scene_id}/start` → start runtime loop (background task/thread)
* `GET /api/scenes/{scene_id}/state` → returns status, transcript, beat_index, locked outputs

---

## Runtime Logic (Core Loop)

### Start Scene

* sets `status=RUNNING`, `beat_index=0`, `style=defaults`

### run_scene(scene_id)

Loop while RUNNING:

1. **Check for Interruption/Command**:
   * Before processing current beat, check if `director_queue` has pending command (from separate listen thread/loop).
   * Or, if single-threaded (MVP): The "Listen" phase below handles classification.

2. If current beat is **AI**:
   * **Wait briefly (500ms?)** to allow Director interrupt ("Wait", "Hold on").
   * choose `text_to_speak`: `active_variant` if exists else `canonical`.
   * `tts_speak(text_to_speak, voice_id, style)`
   * append transcript: `{speaker:"AI", text, meta:{beat_id, style_snapshot}}`
   * `last_talk_turn = "AI"`
   * `beat_index += 1`

3. If current beat is **ACTOR**:
   * **Listen Loop**:
     * Listen for utterance (VAD end-of-speech).
     * STT → `text`
     * **Classification**:
       * **(A) Lock Phrase**: `text` contains "lock this version" → `lock_scene()`, break.
       * **(B) Director Command**:
         * Starts with "reader" OR
         * Contains "wait", "stop", "again", "redo" (Heuristic mode)
         * → call `handle_director_command(text)`
         * If command was "Review/Rewind", `beat_index` might change. **Continue Loop** (don't advance).
       * **(C) Actor Line**:
         * Default case.
         * append transcript: `{speaker:"ACTOR", text}`
         * `actor_latest_takes[beat.id] = text`
         * `last_talk_turn = "ACTOR"`
         * `beat_index += 1`

4. If `beat_index` reaches end:
   * Stop and wait for lock phrase OR auto status READY_TO_LOCK

---

## Director Commands & Logic

**Context Awareness**:
The system tracks `last_talk_turn`.
If command is `again` / `redo`:
* If `last_talk_turn == "AI"` → Replay AI beat (decrement `beat_index` by 1 if currently at Actor beat).
* If `last_talk_turn == "ACTOR"` → Replay Actor beat (rewind `beat_index` by 1 to let Actor try again, or just wait for Actor input again).

**Supported Commands**:

1. **Replay / Style Change**
   * Trigger: `reader ... again/redo ... [style attributes]` OR `can you do it again ... [style]`
   * Attributes: `tense`, `faster` (pace++), `slower` (pace--), `warmer` (warmth++), `cooler`/`cold` (warmth--).
   * Action: Update `style`, Rewind to start of relevant beat.

2. **Rewrite / Improv (AI)**
   * Trigger: `reader ... change the line ...` or `reader ... try it like ...`
   * Action: Generate variant (LLM or heuristic) -> Set active -> Replay.

3. **Explicit Wording / Parrot (AI)**
   * Trigger: `reader ... say [text]` or `try this: [text]`
   * Action: Create new variant with exact text provided. Set active. Replay.

4. **Director to Actor (Rewind)**
   * Trigger: `can you do it again ...` (detected during Actor phase or immediately after).
   * Action: Log note "Director requested retake". Rewind `beat_index` to Actor beat. The system simply waits for the Actor to speak again.

---

## Locking Behavior

When lock phrase detected:

1. set `status=LOCKING`
2. Build **Locked Script**:
   * **AI Beats**: Use `active_variant` (or canonical).
   * **Actor Beats**: Insert text from `actor_latest_takes[beat.id]`.
     * *Note:* If director proposed a line "how about this line: ...", and Actor spoke it, `actor_latest_takes` captures the Actor's performance of that line.
3. Generate **Notes**:
   * Style settings at lock time.
   * List of manual rewrites/variants used.
   * Transcript summary.
4. Save artifacts.
5. set `status=LOCKED`

---

## Cartesia TTS Integration (MVP)

* Integrate `style.pace` → Cartesia `speed` (if available, else simulate with pauses).
* Integrate `style.tension` → Cartesia `emotion` (if available) or Mapping (e.g. `sonic-english` emotion sliders).

---

## Acceptance Criteria (Spec Stress Test)

1. Director starts scene. AI speaks Line 1.
2. Actor speaks Line 2.
3. Director interrupts: "reader, one more time but slower".
   * System detects "reader", "again", "slower".
   * System rewinds to Line 1 (AI). Updates `pace`.
   * AI speaks Line 1 (Slower).
4. Actor speaks Line 2.
5. AI speaks Line 3?
   * Director interrupts: "can you do it again but faster".
   * System detects command (despite missing "reader" if heuristic works, or user learns to say "reader").
   * Context: Last turn was Actor (Line 2).
   * Action: Rewind to Line 2. System waits.
   * Actor speaks Line 2 (Faster).
6. Director: "reader -- try this -- [New Line C]".
   * System updates Line 3 text.
   * AI speaks Line 3 (New Text).
7. Actor replies (Line 4).
8. Director: "how about this line: [Alt Line 4]".
   * Actor speaks [Alt Line 4].
   * System records this as latest take for Line 4.
9. "Lock this version".
   * Script generated with Line 1 (AI, defaults), Line 2 (Actor, fast), Line 3 (AI, New Text), Line 4 (Actor, Alt Text).

---
