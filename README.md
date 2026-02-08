# table-read

AI-powered script rehearsal with a LiveKit voice agent and AI director feedback.

## Architecture

```
Next.js (port 3000)              FastAPI (port 8000)              LiveKit Agent
├── /  (create scene)            ├── /api/scenes (CRUD)           └── agent.py dev
├── /scene/[sceneId]             └── runtime engine
│   └── LiveKit room + panels
└── /api/token
    └── JWT + agent dispatch
```

- **Next.js** — React frontend with LiveKit components, Tailwind CSS
- **FastAPI** — scene persistence and runtime engine API
- **LiveKit Agent** — voice rehearsal loop with AI character (Cartesia TTS) and AI director (Claude)

## Project Structure

```
table-read/
├── agent.py                     # LiveKit agent entry point
├── app/
│   ├── main.py                  # FastAPI app factory + CORS
│   ├── routes.py                # API endpoints (scenes CRUD + utterance)
│   ├── models.py                # Pydantic data models
│   ├── config.py                # Settings from environment
│   ├── parser.py                # Script text → Beat list
│   ├── storage.py               # Scene/session JSON persistence
│   ├── tts.py                   # Cartesia TTS client
│   ├── agents/                  # LiveKit agent logic
│   │   ├── character_agent.py   # ScriptedCharacterAgent (beat loop)
│   │   ├── director_observer.py # AI director evaluation (Claude)
│   │   ├── rpc.py               # RPC/byte-stream helpers
│   │   ├── state.py             # Shared session state dataclass
│   │   └── prompts/             # LLM prompt templates
│   │       └── director_evaluation.yaml
│   └── runtime/                 # State machine
│       ├── engine.py            # SceneRuntimeEngine
│       └── commands.py          # Utterance classification + director commands
├── frontend/                    # Next.js app
│   └── src/
│       ├── app/                 # Pages + API routes
│       │   ├── page.tsx         # Create scene form
│       │   ├── scene/[sceneId]/ # Rehearsal room
│       │   └── api/token/       # LiveKit token generation
│       ├── components/          # React UI panels
│       ├── hooks/               # useTableReadStatus (RPC + byte stream)
│       └── lib/                 # Utilities
├── tests/                       # Python tests
└── pyproject.toml
```

## Setup

### 1. Install Python dependencies

```bash
pip install -e .
```

### 2. Install frontend dependencies

```bash
cd frontend && npm install
```

### 3. Configure environment

```bash
cp .env.example .env
# Edit .env with your API keys (Cartesia, LiveKit, Anthropic)

cd frontend
cp .env.local.example .env.local
# Edit .env.local if LiveKit settings differ from defaults
```

### 4. Start LiveKit server

Follow the [LiveKit quickstart](https://docs.livekit.io/home/self-hosting/local/) to run a local LiveKit server on port 7880.

### 5. Run all three processes

```bash
# Terminal 1: FastAPI backend
uvicorn app.main:app --port 8000

# Terminal 2: LiveKit agent
python agent.py dev

# Terminal 3: Next.js frontend
cd frontend && npm run dev
```

Open `http://localhost:3000`.

## Usage

1. Create a scene — fill in title, AI character name, voice ID, and script
2. Click **Connect & Start Rehearsal** — mic is enabled, AI speaks first
3. Speak your lines — the agent advances through beats, transcript updates live
4. AI Director evaluates each delivery — verdict (acting/reading), rating, engagement, notes
5. Say "lock this version" — final script is locked and displayed

## Script Format

```text
JULIET: O Romeo, Romeo! Wherefore art thou Romeo?
ROMEO:
JULIET: What's in a name? That which we call a rose by any other name would smell as sweet.
ROMEO:
```

Set **AI Character Name** to the character spoken by TTS (e.g. `JULIET`). All other character lines become actor turns.

## API

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/scenes` | Create a scene from script text |
| `GET` | `/api/scenes/{id}` | Get scene details |
| `POST` | `/api/scenes/{id}/start` | Start rehearsal |
| `GET` | `/api/scenes/{id}/state` | Get current session state |
| `POST` | `/api/scenes/{id}/utterance` | Submit text utterance (JSON body: `{"text": "..."}`) |

## Tests

```bash
pytest
```

## Key Technologies

- [LiveKit Agents](https://docs.livekit.io/agents/) — real-time voice, RPC, byte streams
- [Cartesia](https://cartesia.ai/) — TTS (Sonic-2) and STT (Ink-Whisper) via LiveKit plugins
- [Anthropic Claude](https://docs.anthropic.com/) — AI director evaluation
- [Next.js](https://nextjs.org/) + [Tailwind CSS](https://tailwindcss.com/) — frontend
- [FastAPI](https://fastapi.tiangolo.com/) — backend API
