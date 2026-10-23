"""ngspice runner: locate the binary, run a deck in batch mode, parse the results.

ngspice runs as a plain subprocess (no shell) inside ``asyncio.to_thread`` rather
than an asyncio subprocess, because uvicorn may run a selector event loop on
Windows, which cannot spawn asyncio subprocesses. Every run is bounded: a hard
timeout, a cap on how much output is read back, and a fresh temporary directory.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final, Protocol

from circuits_llm.domain import Circuit, Issue, Severity

from .diagnostics import diagnose, timeout_reason
from .extract import ExtractionError, operating_point, sweep
from .raw import RawParseError, RawPlot, parse_raw
from .results import AnalysisResult, SimulationResult
from .spice import SpiceDeck, SpiceEmissionError, to_spice

ENV_VAR: Final = "CIRCUITS_LLM_NGSPICE"
DEFAULT_TIMEOUT_S: Final = 30.0
MAX_TIMEOUT_S: Final = 600.0
MAX_LOG_TAIL_BYTES: Final = 8_000  # returned to the caller in SimulationResult.log
MAX_LOG_SCAN_BYTES: Final = 256_000  # read from the start of the log for diagnosis
MAX_RAW_BYTES: Final = 128 * 1024 * 1024
DECK_FILE: Final = "circuit.cir"
LOG_FILE: Final = "ngspice.log"

_REPO_ROOT: Final = Path(__file__).resolve().parents[4]
_BUNDLED_PATTERNS: Final = (
    "vendor/ngspice/**/ngspice_con.exe",
    "vendor/ngspice/**/bin/ngspice",
    "bin/ngspice_con.exe",
    "bin/ngspice",
)
_PATH_NAMES: Final = ("ngspice_con", "ngspice")


# --------------------------------------------------------------------------- locating


def _bundle_roots() -> Iterator[Path]:
    yield _REPO_ROOT
    meipass = getattr(sys, "_MEIPASS", None)  # set by a PyInstaller one-file build
    if isinstance(meipass, str):
        yield Path(meipass)
    yield Path(sys.executable).resolve().parent


def _bundled_ngspice() -> Path | None:
    for root in _bundle_roots():
        for pattern in _BUNDLED_PATTERNS:
            matches = sorted(p for p in root.glob(pattern) if p.is_file())
            if matches:
                return matches[0]
    return None


def locate_ngspice(explicit: Path | None = None) -> Path | None:
    """Find the ngspice console executable.

    Order: ``explicit`` -> ``$CIRCUITS_LLM_NGSPICE`` -> a bundled copy (``vendor/ngspice``
    or ``bin/`` next to the repo, PyInstaller bundle or executable) -> ``PATH``.
    Candidates that are not existing files are skipped.
    """
    configured = os.environ.get(ENV_VAR, "").strip()
    for candidate in (explicit, Path(configured) if configured else None):
        if candidate is not None and candidate.is_file():
            return candidate.resolve()
    bundled = _bundled_ngspice()
    if bundled is not None:
        return bundled.resolve()
    for name in _PATH_NAMES:
        found = shutil.which(name)
        if found is not None:
            return Path(found).resolve()
    return None


# --------------------------------------------------------------------------- running


@dataclass(slots=True)
class _RunOutput:
    log_head: str = ""
    log_tail: str = ""
    plots: dict[str, RawPlot | str] = field(default_factory=dict[str, RawPlot | str])
    failure: str | None = None  # whole-run failure (timeout, could not start)


def _read_text(path: Path, start: int, limit: int) -> str:
    with path.open("rb") as handle:
        handle.seek(start)
        return handle.read(limit).decode("utf-8", errors="replace")


def _read_log(path: Path, out: _RunOutput) -> None:
    if not path.is_file():
        return
    size = path.stat().st_size
    out.log_head = _read_text(path, 0, MAX_LOG_SCAN_BYTES)
    out.log_tail = _read_text(path, max(0, size - MAX_LOG_TAIL_BYTES), MAX_LOG_TAIL_BYTES)


def _read_plot(path: Path) -> RawPlot | str:
    """The parsed plot, or a reason string if it is missing or unusable."""
    if not path.is_file():
        return "missing"
    if path.stat().st_size > MAX_RAW_BYTES:
        return f"result file exceeds {MAX_RAW_BYTES // (1024 * 1024)} MB; reduce the point count"
    try:
        return parse_raw(_read_text(path, 0, MAX_RAW_BYTES))
    except RawParseError as exc:
        return f"unreadable result file ({exc})"


def _creation_flags() -> int:
    if sys.platform == "win32":
        return subprocess.CREATE_NO_WINDOW
    return 0


class NgspiceSimulator:
    """Runs circuits through an ngspice console binary in batch mode."""

    def __init__(self, executable: Path, timeout_s: float = DEFAULT_TIMEOUT_S) -> None:
        if not 0 < timeout_s <= MAX_TIMEOUT_S:
            raise ValueError(f"timeout_s must be in (0, {MAX_TIMEOUT_S}]")
        self.executable = executable
        self.timeout_s = timeout_s

    async def simulate(self, circuit: Circuit) -> SimulationResult:
        """Simulate ``circuit``. Never raises for simulator failures; see ``ok``/``error``."""
        started = time.monotonic()
        try:
            deck = to_spice(circuit)
        except SpiceEmissionError as exc:
            return SimulationResult(ok=False, netlist="", error=f"Cannot simulate: {exc}")
        output = await asyncio.to_thread(self._run, deck)
        elapsed_ms = int((time.monotonic() - started) * 1000)
        return _assemble(deck, output, elapsed_ms)

    def _run(self, deck: SpiceDeck) -> _RunOutput:
        out = _RunOutput()
        with tempfile.TemporaryDirectory(prefix="circuits-llm-", ignore_cleanup_errors=True) as tmp:
            workdir = Path(tmp)
            (workdir / DECK_FILE).write_text(deck.text, encoding="ascii")
            log_path = workdir / LOG_FILE
            out.failure = self._execute(workdir, log_path)
            _read_log(log_path, out)
            for planned in deck.analyses:
                out.plots[planned.raw_file] = _read_plot(workdir / planned.raw_file)
        return out

    def _execute(self, workdir: Path, log_path: Path) -> str | None:
        command = [str(self.executable), "-b", DECK_FILE]
        try:
            with log_path.open("wb") as log:
                subprocess.run(  # noqa: S603 - fixed argv, no shell, validated deck
                    command,
                    cwd=workdir,
                    stdin=subprocess.DEVNULL,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    timeout=self.timeout_s,
                    check=False,
                    creationflags=_creation_flags(),
                )
        except subprocess.TimeoutExpired:
            return timeout_reason(self.timeout_s)
        except OSError as exc:
            return f"Could not start ngspice at '{self.executable}': {exc.strerror or exc}"
        return None


# --------------------------------------------------------------------------- results


_ANALYSIS_LABELS: Final = {
    "op": "Operating point",
    "dc": "DC sweep",
    "ac": "AC analysis",
    "tran": "Transient analysis",
}


def _assemble(deck: SpiceDeck, output: _RunOutput, elapsed_ms: int) -> SimulationResult:
    if output.failure is not None:
        return SimulationResult(
            ok=False,
            netlist=deck.text,
            error=output.failure,
            log=output.log_tail,
            duration_ms=elapsed_ms,
        )
    log = output.log_head + output.log_tail
    analyses: list[AnalysisResult] = []
    failed: dict[str, list[str]] = {}  # reason -> labels of the analyses it broke
    for index, planned in enumerate(deck.analyses):
        plot = output.plots.get(planned.raw_file, "missing")
        label = _ANALYSIS_LABELS[planned.analysis.type]
        if isinstance(plot, str):
            reason = diagnose(log, deck.node_names) if plot == "missing" else plot
            failed.setdefault(reason, []).append(label)
            continue
        try:
            analyses.append(
                operating_point(plot, deck) if index == 0 else sweep(plot, planned, deck)
            )
        except ExtractionError as exc:
            reason = f"{exc}. {diagnose(log, deck.node_names)}"
            failed.setdefault(reason, []).append(label)
    errors = [f"{', '.join(labels)} failed: {reason}" for reason, labels in failed.items()]
    return SimulationResult(
        ok=not errors,
        analyses=analyses,
        netlist=deck.text,
        error=" ".join(errors) or None,
        log=output.log_tail,
        duration_ms=elapsed_ms,
    )


# --------------------------------------------------------------------------- ERC hook


class Simulator(Protocol):
    async def simulate(self, circuit: Circuit) -> SimulationResult: ...


async def simulation_issues(simulator: Simulator, circuit: Circuit) -> list[Issue]:
    """Simulate and report a failure as an ERROR issue for the LLM repair loop."""
    result = await simulator.simulate(circuit)
    if result.ok:
        return []
    return [
        Issue(
            severity=Severity.ERROR,
            code="simulation_failed",
            message=result.error or "Simulation failed for an unknown reason.",
        )
    ]
