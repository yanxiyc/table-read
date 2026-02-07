# table-read

Director-driven voice rehearsal MVP built with FastAPI + Cartesia integrations.

## Run

1. Install dependencies:
```bash
python3 -m pip install fastapi uvicorn jinja2 python-multipart httpx websockets PyJWT
```

2. Configure environment:
```bash
cp .env.example .env
```

Edit `.env` and set:
```bash
CARTESIA_API_KEY=your_key
CARTESIA_AGENT_ID=your_agent_id
```

3. Start server:
```bash
python3 -m uvicorn app.main:app --reload
```

4. Open `http://127.0.0.1:8000/create`.

## Script Format

Use character names directly in script lines:

```text
MOTHER: You’re late.
YOU:
MOTHER: Don’t do this here.
YOU:
```

Set `AI Character Name` to the exact character label that should be spoken by TTS.
All other character lines are treated as human/actor turns.

## API

- `POST /api/scenes`
- `GET /api/scenes/{scene_id}`
- `POST /api/scenes/{scene_id}/start`
- `POST /api/scenes/{scene_id}/end`
- `GET /api/scenes/{scene_id}/state`
- `GET /api/scenes/{scene_id}/agent-session` (Cartesia agent stream URL + token)
- `POST /api/scenes/{scene_id}/utterance`
- `GET /api/scenes/{scene_id}/livekit-token`
- `WS /api/scenes/{scene_id}/stream` (continuous STT stream)
- `GET /api/scenes/{scene_id}/audio/{filename}`

## Tests

```bash
python3 -m pytest -q
```

## TTS Expression Controls

Director style commands update runtime style, and TTS applies:
- `generation_config.speed` from style pace
- `generation_config.emotion` from tension/warmth mapping
- SSML expression tags (`<emotion .../>`, `<speed .../>`) when `CARTESIA_TTS_USE_SSML_EMOTION=true`

## Voice Agent Mode

When `CARTESIA_AGENT_ID` is set, scene start uses Cartesia Voice Agent streaming:
- Browser streams mic waveform directly to `agents/stream/{agent_id}` using short-lived access token
- Agent audio is played directly in browser
- UI stays minimal: script + status, then updated script at end if edits exist
- Scene script is automatically converted to character-labeled text and sent in the agent `start` event as `agent.system_prompt`

Optional: configure LiveKit credentials in `.env` and use
`GET /api/scenes/{scene_id}/livekit-token` for room token issuance.
