# table-read

AI-powered script rehearsal with a LiveKit voice agent and AI director feedback.

## Architecture

```
Next.js (port 3000)              LiveKit Agents
├── /  (create scene)            ├── agent.py dev (character)
├── /scene/[sceneId]             └── director_agent.py dev (director)
│   └── LiveKit room + panels
└── /api/
    ├── scenes (CRUD)            data/scenes/ (shared JSON)
    └── token (JWT + dispatch)       ↕
                                 agent reads/writes
```

- **Next.js** — frontend + API routes (scene CRUD, LiveKit token)
- **LiveKit Agents** — character agent + director agent (Claude evaluation)
- **Notion** — source of truth for scene definitions (title, characters, beats)
- **Local fallback** — `data/scenes/` directory with JSON files (used when Notion is unavailable)

## Project Structure

```
table-read/
├── agent.py                     # Character agent entry point
├── director_agent.py            # Director agent entry point
├── app/                         # Python modules (used by agent)
│   ├── models.py                # Pydantic data models
│   ├── config.py                # Settings from environment
│   ├── parser.py                # Script text → Beat list
│   ├── storage.py               # Scene/session persistence (Notion + file fallback)
│   ├── notion_client.py         # Notion REST API wrapper (httpx)
│   ├── style_utils.py           # Shared emotion/clamp helpers
│   ├── agents/                  # LiveKit agent logic
│   │   ├── character_agent.py   # ScriptedCharacterAgent (beat loop)
│   │   ├── director_agent.py    # Director agent logic (Claude)
│   │   ├── rpc.py               # RPC/byte-stream helpers
│   │   ├── state.py             # Shared session state dataclass
│   │   └── prompts/             # LLM prompt templates
│   │       └── director_evaluation.yaml
│   └── runtime/
│       └── commands.py          # Utterance classification + director commands
├── frontend/                    # Next.js app
│   └── src/
│       ├── app/                 # Pages + API routes
│       │   ├── page.tsx         # Create scene form
│       │   ├── scene/[sceneId]/ # Rehearsal room
│       │   └── api/
│       │       ├── scenes/      # Scene CRUD API routes
│       │       └── token/       # LiveKit token generation
│       ├── components/          # React UI panels
│       ├── hooks/               # useTableReadStatus (RPC + byte stream)
│       └── lib/
│           ├── scenes.ts        # Scene types, parser, storage
│           ├── notion.ts        # Notion client (@notionhq/client)
│           └── utils.ts         # Tailwind utilities
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
# Edit .env with your API keys (LiveKit, Anthropic, Notion)

cd frontend
cp .env.local.example .env.local
# Edit .env.local with LiveKit + Notion credentials
```

### 3b. Set up Notion (optional but recommended)

1. Create a [Notion Integration](https://www.notion.so/my-integrations) with read/write content capabilities
2. Copy the **Internal Integration Secret** → `NOTION_TOKEN`
3. Create a database in Notion with these properties:
   - **Name** (title), **Scene ID** (text), **AI Character** (text), **Actor Label** (text), **Voice ID** (text), **Status** (select: IDLE, RUNNING, READY_TO_LOCK, LOCKED)
4. Share the database with your integration (⋯ → Connections → add your integration)
5. Copy the database ID from the URL → `NOTION_DATABASE_ID`
6. Add both to `.env` and `frontend/.env.local`

### 4. Start LiveKit server

Follow the [LiveKit quickstart](https://docs.livekit.io/home/self-hosting/local/) to run a local LiveKit server on port 7880.

### 5. Run all three processes

```bash
# Terminal 1: Character agent
python agent.py dev
# Terminal 2: Director agent
python director_agent.py dev

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

## Tests

```bash
pytest
```

## Key Technologies

- [LiveKit Agents](https://docs.livekit.io/agents/) — real-time voice, RPC, byte streams
- [Cartesia](https://cartesia.ai/) — TTS (Sonic-3) and STT (Ink-Whisper) via LiveKit plugins
- [Anthropic Claude](https://docs.anthropic.com/) — AI director evaluation
- [Notion API](https://developers.notion.com/) — scene persistence and real-time script editing
- [Next.js](https://nextjs.org/) + [Tailwind CSS](https://tailwindcss.com/) — frontend + API
