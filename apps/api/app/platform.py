"""The agent on LangGraph Platform, as the api reaches it (spec 05 AC-05, spec 01 §6.4).

The browser never talks to Platform and never holds its key: `LANGSMITH_API_KEY` is read from the environment here and
sent only in the `x-api-key` header of the api's own requests. A thread belongs to the session whose id is in its
metadata, written server-side when the thread is created; the run's `configurable` is built by the api (`live.py`),
never taken from the request. `stream` yields `(event, data)` pairs already normalized: `progress` items and one final
`turn` (the graph's last `values`), so the caller projects the turn for the customer before anything leaves the api.
"""
from __future__ import annotations

import json
import os
from collections.abc import Iterator
from typing import Any, Optional, Protocol

import httpx


class PlatformError(Exception):
    """Platform is unreachable or answered an error; the api turns it into UNAVAILABLE."""


class Platform(Protocol):
    def create_thread(self, session_id: str) -> str: ...

    def thread_session(self, thread_id: str) -> Optional[str]:
        """The `session_id` in the thread's metadata, None for an unknown thread."""

    def stream(self, thread_id: str, configurable: dict[str, Any], payload: dict[str, Any]
               ) -> Iterator[tuple[str, dict[str, Any]]]: ...

    def state(self, thread_id: str) -> Optional[dict[str, Any]]:
        """The thread's latest graph output (a TurnResult as a dict), None before the first turn."""


class HttpPlatform:
    def __init__(self, url: str, api_key: str, assistant_id: str = "dispute_intake",
                 transport: Optional[httpx.BaseTransport] = None) -> None:
        self.assistant_id = assistant_id
        self._client = httpx.Client(base_url=url.rstrip("/"), headers={"x-api-key": api_key}, timeout=60.0,
                                    transport=transport)

    @classmethod
    def from_env(cls) -> Optional["HttpPlatform"]:
        url, key = os.getenv("LANGGRAPH_API_URL"), os.getenv("LANGSMITH_API_KEY")
        return cls(url, key, os.getenv("LANGGRAPH_ASSISTANT", "dispute_intake")) if url and key else None

    def _call(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        try:
            response = self._client.request(method, path, **kwargs)
        except httpx.HTTPError as error:
            raise PlatformError(type(error).__name__) from None
        if response.status_code == 404:
            return response
        if response.status_code >= 400:
            raise PlatformError(f"platform answered {response.status_code}")
        return response

    def create_thread(self, session_id: str) -> str:
        return self._call("POST", "/threads", json={"metadata": {"session_id": session_id}}).json()["thread_id"]

    def thread_session(self, thread_id: str) -> Optional[str]:
        response = self._call("GET", f"/threads/{thread_id}")
        return None if response.status_code == 404 else (response.json().get("metadata") or {}).get("session_id")

    def stream(self, thread_id: str, configurable: dict[str, Any], payload: dict[str, Any]
               ) -> Iterator[tuple[str, dict[str, Any]]]:
        body = {"assistant_id": self.assistant_id, "input": payload.get("input") or {},
                "config": {"configurable": configurable}, "stream_mode": ["custom", "values"]}
        last: Optional[dict[str, Any]] = None
        try:
            with self._client.stream("POST", f"/threads/{thread_id}/runs/stream", json=body) as response:
                if response.status_code >= 400:
                    raise PlatformError(f"platform answered {response.status_code}")
                event = ""
                for line in response.iter_lines():
                    if line.startswith("event:"):
                        event = line[6:].strip()
                    elif line.startswith("data:") and event in ("custom", "values"):
                        data = json.loads(line[5:])
                        if event == "custom":
                            yield "progress", data
                        else:
                            last = data
        except httpx.HTTPError as error:
            raise PlatformError(type(error).__name__) from None
        if last is not None:
            yield "turn", last

    def state(self, thread_id: str) -> Optional[dict[str, Any]]:
        response = self._call("GET", f"/threads/{thread_id}/state")
        return None if response.status_code == 404 else (response.json().get("values") or None)
