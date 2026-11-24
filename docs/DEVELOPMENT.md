# Developing circuits-llm

How to run circuits-llm from source, make changes and check them. For how the pieces fit
together, read [ARCHITECTURE.md](ARCHITECTURE.md).

## Prerequisites

| Tool | Version | Notes |
| --- | --- | --- |
| Python | 3.12+ | backend |
| Node.js | 20+ | frontend |
| ngspice | recent | the circuit simulator, see below |
| git | any | |

### Installing ngspice

- **Windows:** download the `ngspice-*_64.7z` build from
  [ngspice.sourceforge.io](https://ngspice.sourceforge.io/download.html) and extract it so
  that `vendor/ngspice/Spice64/bin/ngspice_con.exe` exists in the repo. `vendor/` is not
  committed.
- **macOS:** `brew install ngspice`
- **Debian/Ubuntu:** `sudo apt install ngspice`

The app looks for ngspice in this order: the `--ngspice PATH` option, the
`CIRCUITS_LLM_NGSPICE` (or `CIRCUITS_LLM_NGSPICE_PATH`) environment variable,
`vendor/ngspice/`, then your `PATH`. Simulation tests are skipped if ngspice is not found.

## First-time setup

Paths below use the macOS/Linux layout (`.venv/bin/...`). On Windows use
`.venv\Scripts\...` instead, e.g. `.venv\Scripts\python`.

```bash
git clone https://github.com/hz-nm/circuit-llm.git
cd circuit-llm

# backend
cd backend
python -m venv .venv
.venv/bin/pip install -e ".[dev]"

# frontend
cd ../frontend
npm install
```

## Running in development

Use two terminals:

```bash
# 1. API server on http://127.0.0.1:8765 (restart it after backend changes)
cd backend
.venv/bin/python -m circuits_llm --no-browser

# 2. UI with hot reload on http://localhost:5173 (it proxies /api to port 8765)
cd frontend
npm run dev
```

Open http://localhost:5173, go to **Settings → Models** and add a model with your API key
(the keys are stored in your local SQLite database, not in the repo). Free models on
OpenRouter, such as `openai/gpt-oss-120b:free`, are enough to develop with.

`npm run dev:mock` runs the UI against canned circuits, with no backend and no LLM. Use it
for UI work.

### Running the app the way users get it

The backend serves a built copy of the UI from `backend/src/circuits_llm/web/static`.
To refresh that copy and run everything from one process on port 8765:

```bash
cd frontend && npm run build:embed
cd ../backend && .venv/bin/python -m circuits_llm
```

### Useful options

| Option | Environment variable | Default |
| --- | --- | --- |
| `--port` | `CIRCUITS_LLM_PORT` | `8765` |
| `--data-dir` | `CIRCUITS_LLM_DATA_DIR` | your OS user-data folder |
| `--ngspice PATH` | `CIRCUITS_LLM_NGSPICE_PATH` | auto-detected |
| `--no-browser` | `CIRCUITS_LLM_OPEN_BROWSER=false` | opens a browser |
| | `CIRCUITS_LLM_SIMULATION_TIMEOUT_S` | `30` |
| | `CIRCUITS_LLM_PLAN_BEFORE_DESIGN` | `true` |

Point `--data-dir` at a scratch folder to keep test projects separate from your real ones.

## Checks before you push

CI (GitHub Actions, on Linux) runs these on every push and pull request; `npm run lint` runs only locally, so run it too:

```bash
cd backend
.venv/bin/ruff check src tests scripts
.venv/bin/ruff format --check src tests scripts     # or `ruff format` to fix
.venv/bin/pyright                                    # strict mode
.venv/bin/python -m pytest

cd ../frontend
npm run lint
npm run build      # includes the TypeScript type check
npm test
```

**The tests never call a real LLM.** They use fake providers, so they are free and
deterministic. Please keep it that way: a test that needs a model answer should feed a
recorded answer to `FakeProvider`.

Keep tests lean. Prefer one test that checks real behaviour, such as a simulated circuit
meeting its numbers, over many tiny ones.

## Trying real models (optional)

`backend/scripts/smoke_live.py` runs one request through the full design loop against a
real provider and prints the result. It costs tokens, so run it by hand:

```bash
# backend/.env (gitignored, never commit it)
OPENROUTER_API_KEY=sk-or-...
GEMINI_API_KEY=...

cd backend
.venv/bin/python scripts/smoke_live.py "Blink an LED with a 555 at 2 Hz" openrouter
```

## When you change the API

The frontend's TypeScript types are generated from the backend's OpenAPI schema. After
changing a Pydantic model or route, regenerate them:

```bash
cd backend && .venv/bin/python scripts/export_openapi.py   # writes frontend/openapi.json
cd ../frontend && npm run gen:api                          # writes src/api/schema.d.ts
```

Commit both generated files.

## Adding a component kind

The catalog is the single source of truth, so the type checkers point you to most of the
places to touch. Using the 555 timer as the example:

1. **Catalog:** add the kind, pins, aliases and models in
   `backend/src/circuits_llm/domain/catalog.py`. The description is what the LLM reads,
   so state the rules a beginner would get wrong.
2. **Simulation model:** write the `.subckt` in `simulation/library.py` and emit it in
   `simulation/spice.py`. Check the numbers against the datasheet or a textbook formula
   in a quick ngspice run before going further.
3. **Bench checks** (optional): add rating checks in `simulation/ratings.py`, such as a
   supply range or output-current limit.
4. **Prompts:** if the part needs wiring know-how, add a family note, a skeleton line or
   a worked example in `llm/prompts.py`. Every example is simulated by a test and must
   meet its own expectations.
5. **Frontend:** add a symbol in `frontend/src/features/schematic/symbols.tsx`. The
   `Record<ComponentKind, ...>` type makes the compiler insist, once you have regenerated
   the API types.
6. **Test:** add one integration test in `backend/tests/test_simulation_ngspice.py` that
   simulates a small circuit using the part and checks its key number.

## Building the desktop bundle

```bash
cd backend && .venv/bin/pip install -e ".[package]"
cd .. && backend/.venv/bin/python packaging/build.py   # writes dist/circuits-llm-<platform>.zip
```

Releases are built by `.github/workflows/release.yml` when a `v*` tag is pushed. It creates
a draft release to review and publish.

## Troubleshooting

- **"ngspice was not found":** see [Installing ngspice](#installing-ngspice), or pass
  `--ngspice` with the full path to `ngspice_con` (Windows) or `ngspice`.
- **Port 8765 is in use:** an earlier server is still running. Stop it, or start this one
  with `--port 8766` and change the proxy target in `frontend/vite.config.ts`.
- **The UI shows old behaviour on port 8765:** the embedded copy is stale. Run
  `npm run build:embed` again, or develop on port 5173.
- **Type errors in `schema.d.ts` after pulling:** regenerate the API types (see above).
