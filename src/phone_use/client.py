from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from .exceptions import PhoneUseAPIError, PhoneUseNetworkError

JsonObject = dict[str, Any]

# Extra headroom (seconds) added on top of a request's own timeout_s/timeout_ms
# so the local socket read doesn't get cut off right as the server-side
# deadline elapses, and the server has a chance to respond with its own
# timeout error first.
_TIMEOUT_BUFFER_S = 5.0


class PhoneUse:
    """Synchronous client for the phone automation HTTP API."""

    def __init__(
        self,
        base_url: str | None = None,
        *,
        device_id: str = "default",
        timeout: float = 30.0,
        headers: Mapping[str, str] | None = None,
        model_name: str | None = None,
        model_api_key: str | None = None,
        model_base_url: str | None = None,
        model_family: str | None = None,
        model_reasoning_enabled: bool | None = None,
    ) -> None:
        resolved_url = base_url or os.getenv(
            "PHONE_USE_BASE_URL", "http://127.0.0.1:8787"
        )
        if not resolved_url.strip():
            raise ValueError("base_url cannot be empty")
        if not device_id.strip():
            raise ValueError("device_id cannot be empty")
        if timeout <= 0:
            raise ValueError("timeout must be greater than zero")
        if model_name is not None and not model_name.strip():
            raise ValueError("model_name cannot be empty")

        self.base_url = resolved_url.rstrip("/")
        self.device_id = device_id
        self.timeout = float(timeout)
        self.headers = dict(headers or {})
        self.model = self._compact(
            {
                "name": model_name,
                "api_key": model_api_key,
                "base_url": model_base_url,
                "family": model_family,
                "reasoning_enabled": model_reasoning_enabled,
            }
        )

    def health(self) -> JsonObject:
        """Return API service health information."""
        return self._request_json("GET", "/healthz")

    def list_devices(self) -> JsonObject:
        """List devices exposed by the API."""
        return self._request_json("GET", "/v1/devices")

    def get_device(self) -> JsonObject:
        """Return metadata for the selected device."""
        return self._request_json("GET", self._device_path())

    def screenshot(self, *, source: str | None = None) -> bytes:
        """Return a PNG screenshot for the selected device."""
        query = urlencode({"source": source}) if source is not None else ""
        path = self._device_path("screenshot")
        return self._request("GET", f"{path}?{query}" if query else path)

    def save_screenshot(
        self,
        path: str | os.PathLike[str],
        *,
        source: str | None = None,
    ) -> Path:
        """Capture a screenshot and write it to *path*."""
        output = Path(path)
        output.write_bytes(self.screenshot(source=source))
        return output

    def act(self, instruction: str, **options: Any) -> JsonObject:
        """Execute a natural-language instruction on the selected device."""
        if not instruction.strip():
            raise ValueError("instruction cannot be empty")
        return self._post(
            "act",
            self._with_model({"instruction": instruction}, options),
        )

    def query_string(self, prompt: str, **options: Any) -> JsonObject:
        """Read a string value from the current screen."""
        if not prompt.strip():
            raise ValueError("prompt cannot be empty")
        return self._post(
            "query-string",
            self._with_model({"prompt": prompt}, options),
        )

    def wait_for(self, assertion: str, **options: Any) -> JsonObject:
        """Wait until a screen assertion becomes true."""
        if not assertion.strip():
            raise ValueError("assertion cannot be empty")
        return self._post(
            "wait-for",
            self._with_model({"assertion": assertion}, options),
        )

    def tap(self, x: float, y: float, **options: Any) -> JsonObject:
        """Tap a point in screenshot pixel coordinates."""
        return self._post("actions/tap", {"x": x, "y": y, **options})

    def tap_sequence(
        self,
        points: Sequence[Sequence[float]],
        **options: Any,
    ) -> JsonObject:
        """Tap multiple points in order."""
        normalized = [list(point) for point in points]
        if not normalized or any(len(point) != 2 for point in normalized):
            raise ValueError("points must contain one or more [x, y] pairs")
        return self._post(
            "actions/tap-sequence",
            {"points": normalized, **options},
        )

    def swipe(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        **options: Any,
    ) -> JsonObject:
        """Swipe between two points in screenshot pixel coordinates."""
        return self._post(
            "actions/swipe",
            {"x1": x1, "y1": y1, "x2": x2, "y2": y2, **options},
        )

    def named_action(self, name: str, **options: Any) -> JsonObject:
        """Execute a named system action such as home or back."""
        if not name.strip():
            raise ValueError("name cannot be empty")
        return self._post("actions/named", {"name": name, **options})

    def type_text(self, text: str, **options: Any) -> JsonObject:
        """Type text into the focused input."""
        return self._post("type-text", {"text": text, **options})

    def start_task(
        self,
        task_type: str = "ai_act",
        *,
        args: Mapping[str, Any] | None = None,
        model: Mapping[str, Any] | None = None,
    ) -> JsonObject:
        """Start an asynchronous task."""
        if not task_type.strip():
            raise ValueError("task_type cannot be empty")
        task_args = dict(args or {})
        if task_type == "ai_act":
            task_args = self._with_model(task_args, {"model": model})
        return self._post("tasks", {"task_type": task_type, "args": task_args})

    def get_task(self, task_id: str) -> JsonObject:
        """Return an asynchronous task by ID."""
        return self._request_json("GET", self._task_path(task_id))

    def list_tasks(
        self,
        *,
        status: str | None = None,
        limit: int | None = None,
    ) -> JsonObject:
        """List asynchronous tasks for the selected device."""
        if limit is not None and limit <= 0:
            raise ValueError("limit must be greater than zero")
        query = urlencode(
            {
                key: value
                for key, value in {"status": status, "limit": limit}.items()
                if value is not None
            }
        )
        path = self._device_path("tasks")
        return self._request_json("GET", f"{path}?{query}" if query else path)

    def cancel_task(
        self,
        task_id: str,
        *,
        reason: str | None = None,
        stop_device: bool | None = None,
        timeout_s: float | None = None,
    ) -> JsonObject:
        """Cancel an asynchronous task."""
        payload = self._compact(
            {
                "reason": reason,
                "stop_device": stop_device,
                "timeout_s": timeout_s,
            }
        )
        return self._request_json(
            "DELETE",
            self._task_path(task_id),
            payload,
            timeout=self._resolve_timeout(payload),
        )

    def _post(self, action: str, payload: JsonObject) -> JsonObject:
        compacted = self._compact(payload)
        return self._request_json(
            "POST",
            self._device_path(action),
            compacted,
            timeout=self._resolve_timeout(compacted),
        )

    def _resolve_timeout(self, payload: Mapping[str, Any]) -> float:
        """Pick a socket timeout that can accommodate a request's own
        timeout_s/timeout_ms, so a slower-than-default server-side deadline
        (e.g. ``act(..., timeout_s=60)``) isn't cut short by the client's
        constructor-level ``timeout`` (default 30s).
        """
        candidates = [self.timeout]
        timeout_s = payload.get("timeout_s")
        if isinstance(timeout_s, (int, float)) and not isinstance(timeout_s, bool):
            candidates.append(float(timeout_s) + _TIMEOUT_BUFFER_S)
        timeout_ms = payload.get("timeout_ms")
        if isinstance(timeout_ms, (int, float)) and not isinstance(timeout_ms, bool):
            candidates.append(float(timeout_ms) / 1000.0 + _TIMEOUT_BUFFER_S)
        return max(candidates)

    def _with_model(
        self,
        payload: Mapping[str, Any],
        options: Mapping[str, Any],
    ) -> JsonObject:
        request_options = dict(options)
        override = request_options.pop("model", None)
        if override is not None and not isinstance(override, Mapping):
            raise ValueError("model must be a mapping")
        model = self.model if override is None else self._compact(override)
        result = {**payload, **request_options}
        if model:
            result["model"] = dict(model)
        return result

    def _device_path(self, action: str = "") -> str:
        path = f"/v1/devices/{quote(self.device_id, safe='')}"
        return f"{path}/{action}" if action else path

    def _task_path(self, task_id: str) -> str:
        if not task_id.strip():
            raise ValueError("task_id cannot be empty")
        return self._device_path(f"tasks/{quote(task_id, safe='')}")

    @staticmethod
    def _compact(payload: Mapping[str, Any]) -> JsonObject:
        return {key: value for key, value in payload.items() if value is not None}

    def _request_json(
        self,
        method: str,
        path: str,
        payload: JsonObject | None = None,
        *,
        timeout: float | None = None,
    ) -> JsonObject:
        body = self._request(method, path, payload, timeout=timeout)
        try:
            value = json.loads(body)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise PhoneUseAPIError(200, "response is not valid JSON") from exc
        if not isinstance(value, dict):
            raise PhoneUseAPIError(200, "response JSON must be an object", value)
        return value

    def _request(
        self,
        method: str,
        path: str,
        payload: JsonObject | None = None,
        *,
        timeout: float | None = None,
    ) -> bytes:
        headers = {"Accept": "application/json", **self.headers}
        data = None
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"

        request = Request(
            f"{self.base_url}{path}",
            data=data,
            headers=headers,
            method=method,
        )
        try:
            with urlopen(
                request, timeout=self.timeout if timeout is None else timeout
            ) as response:
                return response.read()
        except HTTPError as exc:
            body = exc.read()
            response, message = self._error_body(body, exc.reason)
            raise PhoneUseAPIError(exc.code, message, response) from exc
        except (URLError, TimeoutError, OSError) as exc:
            reason = getattr(exc, "reason", exc)
            raise PhoneUseNetworkError(
                f"cannot reach automation API at {self.base_url}: {reason}"
            ) from exc

    @staticmethod
    def _error_body(body: bytes, fallback: Any) -> tuple[Any, str]:
        try:
            value = json.loads(body)
        except (UnicodeDecodeError, json.JSONDecodeError):
            text = body.decode("utf-8", errors="replace").strip()
            return text or None, text or str(fallback)

        candidate: Any = value
        if isinstance(value, dict):
            candidate = value.get("detail", value.get("error", value))
        if isinstance(candidate, dict):
            candidate = candidate.get("message", candidate)
        if isinstance(candidate, (dict, list)):
            message = json.dumps(candidate, ensure_ascii=False)
        else:
            message = str(candidate or fallback)
        return value, message
