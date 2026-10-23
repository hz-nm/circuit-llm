"""Command-line entry point: ``circuits-llm`` starts the local server and opens the browser."""

from __future__ import annotations

import argparse
import logging
import socket
import threading
import webbrowser
from pathlib import Path
from typing import Final

import uvicorn

from circuits_llm import __version__
from circuits_llm.api import create_app
from circuits_llm.settings import Settings

_PORT_SEARCH_LIMIT: Final = 20
_BROWSER_DELAY_S: Final = 1.5


def _port_is_free(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        return sock.connect_ex((host, port)) != 0


def _choose_port(host: str, preferred: int) -> int:
    """Use ``preferred`` if free, else the next free port (bounded search), else any free one."""
    if preferred == 0:
        return 0
    for port in range(preferred, preferred + _PORT_SEARCH_LIMIT):
        if _port_is_free(host, port):
            return port
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return int(sock.getsockname()[1])


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="circuits-llm", description=__doc__)
    parser.add_argument("--host", help="interface to bind (default 127.0.0.1)")
    parser.add_argument("--port", type=int, help="port to listen on (default 8765)")
    parser.add_argument("--data-dir", type=Path, help="where projects and settings are stored")
    parser.add_argument("--ngspice", type=Path, help="path to the ngspice executable")
    parser.add_argument("--no-browser", action="store_true", help="don't open a browser window")
    parser.add_argument("--version", action="version", version=f"circuits-llm {__version__}")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    overrides = {
        key: value
        for key, value in {
            "host": args.host,
            "port": args.port,
            "data_dir": args.data_dir,
            "ngspice_path": args.ngspice,
        }.items()
        if value is not None
    }
    if args.no_browser:
        overrides["open_browser"] = False
    settings = Settings.model_validate({**Settings().model_dump(), **overrides})

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    port = _choose_port(settings.host, settings.port)
    url = f"http://{settings.host}:{port}"
    print(f"circuits-llm {__version__} running at {url}  (data: {settings.data_dir})")

    if settings.open_browser:
        threading.Timer(_BROWSER_DELAY_S, webbrowser.open, args=(url,)).start()
    uvicorn.run(create_app(settings), host=settings.host, port=port, log_level="info")


if __name__ == "__main__":
    main()
