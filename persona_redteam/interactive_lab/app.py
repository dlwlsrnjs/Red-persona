from __future__ import annotations

import argparse
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from . import __version__
from .catalog import Catalog, PRICING_ESTIMATE
from .protocols import PROTOCOLS, ManualSession, create_session
from .providers import PROVIDERS, ProviderError, chat_completion


STATIC = Path(__file__).resolve().parent / "static"
MAX_BODY = 2 * 1024 * 1024


class State:
    def __init__(self) -> None:
        self.catalog = Catalog()
        self.sessions: dict[str, ManualSession] = {}
        self.inflight: set[str] = set()
        self.lock = threading.RLock()


STATE: State | None = None


def _bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.casefold() in {"1", "true", "yes", "on"}


class Handler(SimpleHTTPRequestHandler):
    server_version = "REDPersonaLab/" + __version__

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(STATIC), **kwargs)

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; style-src 'self'; script-src 'self'; "
            "img-src 'self' data:; connect-src 'self'",
        )
        super().end_headers()

    def log_message(self, fmt: str, *args: Any) -> None:
        # HTTP paths are logged; request bodies and API keys are never logged.
        super().log_message(fmt, *args)

    @property
    def state(self) -> State:
        assert STATE is not None
        return STATE

    def _json(self, value: Any, status: int = 200) -> None:
        payload = json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _error(self, status: int, message: str) -> None:
        self._json({"error": message, "status": status}, status)

    def _body(self) -> dict[str, Any]:
        raw_length = self.headers.get("Content-Length", "0")
        try:
            length = int(raw_length)
        except ValueError as exc:
            raise ValueError("invalid Content-Length") from exc
        if length <= 0 or length > MAX_BODY:
            raise ValueError("request body must be non-empty and at most 2 MiB")
        raw = self.rfile.read(length)
        try:
            value = json.loads(raw)
        except ValueError as exc:
            raise ValueError("request body must be valid JSON") from exc
        if not isinstance(value, dict):
            raise ValueError("request body must be a JSON object")
        return value

    def _session(self, session_id: str) -> ManualSession:
        try:
            return self.state.sessions[session_id]
        except KeyError as exc:
            raise KeyError(f"unknown session: {session_id}") from exc

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        query = parse_qs(parsed.query)
        try:
            if path == "/api/config":
                self._json({
                    "version": __version__,
                    "protocols": PROTOCOLS,
                    "providers": PROVIDERS,
                    "historical_runs": self.state.catalog.public_runs(),
                    "usage_estimates": self.state.catalog.usage_estimates(),
                    "pricing_estimate": PRICING_ESTIMATE,
                    "security": {
                        "api_keys_stored": False,
                        "api_keys_logged": False,
                        "automatic_dispatch": False,
                        "default_bind": "127.0.0.1",
                    },
                })
                return
            if path == "/api/cases":
                history = _bool(query.get("history", ["1"])[0], True)
                rows = self.state.catalog.list_cases(
                    outcome=query.get("outcome", ["all"])[0],
                    query=query.get("q", [""])[0],
                    history_enabled=history,
                    run_id=query.get("run", [None])[0],
                )
                self._json({"count": len(rows), "cases": rows})
                return
            if path == "/api/cases/random":
                history = _bool(query.get("history", ["1"])[0], True)
                row = self.state.catalog.random_case(
                    outcome=query.get("outcome", ["all"])[0],
                    history_enabled=history,
                    run_id=query.get("run", [None])[0],
                )
                self._json(row)
                return
            if path.startswith("/api/cases/"):
                case_id = unquote(path.split("/", 3)[3])
                history = _bool(query.get("history", ["1"])[0], True)
                self._json(self.state.catalog.get_case(
                    case_id,
                    history_enabled=history,
                    run_id=query.get("run", [None])[0],
                ))
                return
            if path == "/api/personas":
                rows = self.state.catalog.search_persona_pool(
                    query.get("q", [""])[0],
                    int(query.get("limit", ["25"])[0]),
                )
                self._json({"count": len(rows), "personas": rows})
                return
            if path.startswith("/api/session/"):
                session_id = path.split("/")[3]
                with self.state.lock:
                    self._json(self._session(session_id).public())
                return
            super().do_GET()
        except KeyError as exc:
            self._error(HTTPStatus.NOT_FOUND, str(exc))
        except (ValueError, TypeError) as exc:
            self._error(HTTPStatus.BAD_REQUEST, str(exc))
        except Exception as exc:  # fail with a bounded, useful local diagnostic
            self._error(HTTPStatus.INTERNAL_SERVER_ERROR, f"{type(exc).__name__}: {exc}")

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        try:
            body = self._body()
            if path == "/api/session":
                session = create_session(self.state.catalog, body)
                with self.state.lock:
                    self.state.sessions[session.id] = session
                self._json(session.public(), HTTPStatus.CREATED)
                return
            parts = path.split("/")
            if len(parts) == 5 and parts[1:3] == ["api", "session"]:
                session_id, action = parts[3], parts[4]
                if action == "prepare":
                    with self.state.lock:
                        session = self._session(session_id)
                        if body.get("quote_override") and session.pending:
                            session.pending = None
                        step = session.prepare(
                            quote_override=str(body.get("quote_override", ""))
                        )
                        self._json({"session": session.public(), "step": step})
                    return
                if action == "send":
                    if body.get("confirm_send") is not True:
                        raise ValueError("confirm_send=true is required")
                    with self.state.lock:
                        session = self._session(session_id)
                        if session_id in self.state.inflight:
                            raise ValueError("this session already has an in-flight request")
                        pending = session.prepare()
                        messages = [dict(item) for item in pending["messages"]]
                        override = str(body.get("prompt_override", ""))
                        if override.strip():
                            messages[-1]["content"] = override
                        self.state.inflight.add(session_id)
                    # The global lock is released during network I/O so separate
                    # comparison lanes can be dispatched independently.  The key
                    # remains scoped to this call and is never copied into state.
                    try:
                        response = chat_completion(
                            provider=str(body.get("provider", "openai")),
                            api_key=str(body.get("api_key", "")),
                            model=str(body.get("model", "")),
                            messages=messages,
                            temperature=float(body.get("temperature", 0.0)),
                            max_tokens=int(body.get("max_tokens", 1000)),
                        )
                    finally:
                        with self.state.lock:
                            self.state.inflight.discard(session_id)
                    with self.state.lock:
                        session.record_response(response, sent_messages=messages)
                        self._json({"session": session.public(), "response": response})
                    return
            self._error(HTTPStatus.NOT_FOUND, "unknown API route")
        except KeyError as exc:
            self._error(HTTPStatus.NOT_FOUND, str(exc))
        except ProviderError as exc:
            self._error(HTTPStatus.BAD_GATEWAY, str(exc))
        except (ValueError, TypeError) as exc:
            self._error(HTTPStatus.BAD_REQUEST, str(exc))
        except Exception as exc:
            self._error(HTTPStatus.INTERNAL_SERVER_ERROR, f"{type(exc).__name__}: {exc}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Manual RED-Persona step inspector")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7865)
    args = parser.parse_args()
    if args.host not in {"127.0.0.1", "localhost", "::1"}:
        print("WARNING: non-loopback binding exposes the UI and entered prompts to your network.")
    global STATE
    STATE = State()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"RED-Persona Interactive Lab: http://{args.host}:{args.port}")
    print("API keys stay in the browser input and are sent only with an explicit step click.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
