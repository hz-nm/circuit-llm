# circuits-llm

Describe a circuit in plain English. Get back a validated schematic and a simulation of it.

> "Design a 5 V regulated supply from 12 V using a zener and an NPN pass transistor, and show me the output under load."

circuits-llm has an LLM write a structured **netlist**, which is then checked:
first by Pydantic, then by an electrical rule checker (floating nodes, missing ground,
shorted sources, unknown parts and so on), and finally by a real simulator (**ngspice**).
Any problems found go back to the model so it can repair the circuit automatically. You
then iterate in chat: "make the gain 20", "add a low-pass filter on the output".
Every change is saved as a version you can compare or restore.

- **Bring your own model.** Anthropic, OpenAI and any OpenAI-compatible server (Ollama, LM Studio, vLLM, NVIDIA NIM, Groq, …), OpenRouter, and Gemini. Configure several models; if one fails, the next one in the chain takes over.
- **Built for modest models.** Prompts, output parsing and repair loops are tuned so that open-weight models such as `gpt-oss-120b` produce working circuits.
- **Real simulation.** Operating point, DC sweep, AC (Bode plots) and transient analysis, using real device models (1N4148, 2N3904, 2N7000, LM358, …).
- **Local first.** Runs on your machine. Your projects and API keys stay in a local SQLite database.

## Quick start

### Download (recommended)

Download the build for your OS from the Releases page, run it, and your browser opens.
Then go to **Settings → Models**, add a model with your API key, and start chatting.

### From source

You'll need Python ≥ 3.12, Node ≥ 20 and [ngspice](https://ngspice.sourceforge.io/)
(on Windows, put the `Spice64` folder in `vendor/ngspice/`; on macOS run `brew install ngspice`; on Debian/Ubuntu run `apt install ngspice`).

```bash
# backend
cd backend
python -m venv .venv && .venv/bin/pip install -e ".[dev]"   # Windows: .venv\Scripts\pip
# frontend (built into the backend package)
cd ../frontend && npm install && npm run build:embed
# run
cd ../backend && .venv/bin/circuits-llm
```

Options: `--port`, `--data-dir`, `--ngspice PATH`, `--no-browser`, and the matching
`CIRCUITS_LLM_*` environment variables.

## Development

```bash
cd backend && .venv/bin/circuits-llm --no-browser     # API on :8765
cd frontend && npm run dev                            # UI on :5173, proxies /api
```

Checks: `ruff check`, `ruff format --check` and `pyright` (strict) for the backend;
`npm run build` for the frontend. Run `pytest` and `npm test`. Tests never call real LLM APIs.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for how it all fits together.
To add a new component kind, start in `backend/src/circuits_llm/domain/catalog.py`.

## License

MIT
