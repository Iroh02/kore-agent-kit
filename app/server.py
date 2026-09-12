"""Stdlib HTTP server. No FastAPI, no uvicorn, no pip. Run:  python3 -m app.server"""
import json
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import agent, config, llm, rag

UI = config.ROOT / "ui" / "index.html"


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print(f"  {self.command} {self.path} -> {args[1] if len(args) > 1 else ''}")

    def _send(self, code, body, content_type="application/json"):
        raw = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(raw)

    def do_OPTIONS(self):
        self._send(204, b"", "text/plain")

    def do_GET(self):
        if self.path.split("?")[0] in ("/", "/index.html"):
            if not UI.exists():
                return self._send(404, {"error": "ui/index.html missing"})
            return self._send(200, UI.read_bytes(), "text/html; charset=utf-8")
        if self.path == "/api/health":
            return self._send(200, {**llm.health(), **rag.stats(), "ok": True})
        self._send(404, {"error": "not found"})

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(length) or b"{}")
        except Exception:  # noqa: BLE001
            return self._send(400, {"error": "invalid JSON body"})
        try:
            if self.path == "/api/chat":
                message = (payload.get("message") or "").strip()
                if not message:
                    return self._send(400, {"error": "message is required"})
                return self._send(200, agent.run(message, payload.get("history") or []))
            if self.path == "/api/ingest":
                return self._send(200, rag.build_index())
            self._send(404, {"error": "not found"})
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            self._send(500, {"error": str(e)})


def main():
    info = rag.build_index()
    health = llm.health()
    print("=" * 58)
    print(f"  provider : {health['provider']}  model: {health['model']}")
    if health["provider"] == "mock":
        print("  NOTE: no LLM_API_KEY set. Retrieval is real, answers are canned.")
    print(f"  indexed  : {info['chunks']} chunks from {info['files_indexed']} files")
    print(f"  open     : http://localhost:{config.PORT}")
    print("=" * 58)
    ThreadingHTTPServer(("0.0.0.0", config.PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
