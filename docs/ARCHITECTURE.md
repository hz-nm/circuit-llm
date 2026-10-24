# Architecture

circuits-llm turns a chat conversation into a validated, simulated circuit.

```
chat ─► planner ─► designer LLM ─► lenient parse ─► Circuit (Pydantic) ─► ERC ─► ngspice ─► bench checks + expectations
          │              ▲                                                │         │            │
          │              └──────────── errors: repair prompt (bounded) ◄──┴─────────┴────────────┘
          └─ picks component families + sketches the design   ok ─► Mermaid · schematic · plots · meters
```

1. **Planner** (one short LLM call): chooses the component families the request needs
   (`core` is always included) and writes a short plan. The designer prompt then
   describes only those families, which keeps it focused for weaker models. If the
   plan is unusable, every family is described.
2. **Designer**: returns the circuit JSON; the lenient parser canonicalises it.
3. **ERC**: wiring rules (missing pins, floating nodes, voltage loops, ...).
4. **Simulation**: ngspice must accept and solve the circuit.
5. **Bench checks** (`simulation/ratings.py`): simulated currents, voltages and power
   are compared with datasheet ratings (LED current, transistor current/power/voltage,
   logic and op-amp supply ranges, lamp overload, ...). Errors mean a real part would
   be destroyed or not work, and go back to the model like ERC errors; warnings
   (e.g. a resistor needing a higher power rating) are shown to the user.
6. **Expectations** (`simulation/expectations.py`): the designer states what the
   circuit must do, e.g. `I(D1) > 5m` when `light(LDR1) < 1`, in a tiny grammar
   (`domain/expectations.py`) evaluated in Python on the results. A failed expectation
   goes back to the model, which catches designs that work but do the wrong thing
   (such as a night light that is on in daylight).

The **netlist (`domain.Circuit`) is the single source of truth.** Mermaid, the
schematic and the SPICE deck are all derived from it.

## Layout

```
backend/src/circuits_llm/
  domain/       Pure, no I/O. Circuit models, component catalog, value parsing, ERC, Mermaid.
  llm/          Provider adapters (Anthropic, OpenAI-compatible, OpenRouter, Gemini),
                prompts, lenient output parsing, generate→validate→repair loop, fallback chain.
                contracts.py is the public surface.
  simulation/   Circuit → SPICE, ngspice runner, raw-file parsing, device model library.
                results.py is the public surface.
  storage/      SQLite persistence (projects, messages, circuit versions, model endpoints).
  api/          FastAPI routers. Design turns stream progress as Server-Sent Events.
  web/          Serves the built frontend.
frontend/       React + TypeScript + Vite single-page app.
```

Dependencies point inwards: `api → {llm, simulation, storage} → domain`. Nothing
imports from `api`, and `domain` imports nothing from the application.

## Rules we follow

- **Validate at the boundaries.** LLM output, HTTP input and simulator output are
  parsed into typed models immediately; inside, code trusts its types.
- **Every loop and wait is bounded.** Repair attempts, fallback endpoints,
  history length, component counts, simulation points and subprocess/HTTP
  timeouts all have explicit limits defined as constants.
- **Report all problems at once.** The ERC returns every issue so one repair
  round-trip can fix them all; messages are written for an LLM to act on.
- **Weak models are first-class.** The benchmark model is `gpt-oss-120b`. The
  parser accepts aliases (`"res"`, `"bjt"`, pin `"b"`), engineering strings
  (`"4k7"`, `"100nF"`) and JSON wrapped in prose or code fences, then
  canonicalises them into the strict domain model.
- **Keys stay local.** API keys are stored in the local SQLite database in the
  user's data directory and are never returned in full by the API.

## Testing

`pytest` never calls real LLM APIs: provider tests use `httpx.MockTransport`
and design-loop tests use a fake provider. Simulation tests run the real ngspice
and are skipped when it isn't installed. For a manual end-to-end check against a
real model, put keys in `backend/.env` (gitignored) and run
`python scripts/smoke_live.py "<request>" [openrouter|gemini] [model]`.

## Packaging

`packaging/build.py` builds the frontend into `circuits_llm/web/static`, then
runs PyInstaller in one-folder mode and zips the result into `dist/`. On Windows,
ngspice (`vendor/ngspice/Spice64`) is bundled inside the app. On macOS and Linux
the app uses the system ngspice (`brew install ngspice` / `apt install ngspice`).
`.github/workflows/release.yml` builds all three platforms when a `v*` tag is pushed.

## Component catalog

`domain/catalog.py` defines every supported component kind, its pins (and
accepted aliases), value unit and available models. The prompt, parser, ERC,
SPICE emitter and frontend symbols are all driven from it; adding a component
starts there.
