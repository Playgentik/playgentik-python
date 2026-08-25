"""Shared test doubles: a fake `requests.Session` so tests never touch the
network. `RestClient`/`McpSession` both accept an injected `session=`, so
these are dropped straight in."""

from __future__ import annotations

import json as _json


class FakeResponse:
    def __init__(self, status_code=200, json_body=None, text=""):
        self.status_code = status_code
        self._json_body = json_body
        self.text = text if text else (_json.dumps(json_body) if json_body is not None else "")

    def json(self):
        if self._json_body is None:
            raise ValueError("no json body")
        return self._json_body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeSession:
    """Queue up responses (or a handler function) and record every call."""

    def __init__(self, responses=None, handler=None):
        self.headers = {}
        self._responses = list(responses or [])
        self._handler = handler
        self.calls = []

    def post(self, url, json=None, headers=None, timeout=None):
        self.calls.append({"method": "POST", "url": url, "json": json, "headers": headers})
        if self._handler:
            return self._handler("POST", url, json)
        return self._responses.pop(0)

    def get(self, url, headers=None, timeout=None):
        self.calls.append({"method": "GET", "url": url, "headers": headers})
        if self._handler:
            return self._handler("GET", url, None)
        return self._responses.pop(0)

    def close(self):
        pass
