"""Minimal Ollama client (standard library only).

The agent works without an LLM. When Ollama is reachable it is used for two
narrow jobs: turning a free-text request into a schema-constrained intent,
and writing a short plain-language explanation of numbers that the
deterministic tools already computed.
"""
import json
import urllib.error
import urllib.request

from .config import OLLAMA_MODEL, OLLAMA_URL


class LLMError(Exception):
    pass


class OllamaClient:
    def __init__(self, base_url: str = OLLAMA_URL, model: str = OLLAMA_MODEL, timeout: float = 120):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    def available(self) -> bool:
        try:
            with urllib.request.urlopen(self.base_url + "/api/tags", timeout=3) as r:
                tags = json.loads(r.read().decode())
            return any(m.get("name", "").startswith(self.model) for m in tags.get("models", []))
        except (urllib.error.URLError, OSError, ValueError):
            return False

    def _chat(self, messages: list, fmt=None) -> str:
        body = {"model": self.model, "messages": messages, "stream": False,
                "options": {"temperature": 0, "seed": 7}}
        if fmt is not None:
            body["format"] = fmt
        req = urllib.request.Request(self.base_url + "/api/chat", data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return json.loads(r.read().decode())["message"]["content"]
        except (urllib.error.URLError, OSError, ValueError, KeyError) as exc:
            raise LLMError(str(exc)) from exc

    def chat_json(self, system: str, user: str, schema: dict) -> dict:
        raw = self._chat([{"role": "system", "content": system}, {"role": "user", "content": user}], fmt=schema)
        try:
            return json.loads(raw)
        except ValueError as exc:
            raise LLMError(f"model returned invalid JSON: {raw[:200]}") from exc

    def chat_text(self, system: str, user: str) -> str:
        return self._chat([{"role": "system", "content": system}, {"role": "user", "content": user}]).strip()
