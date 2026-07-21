from __future__ import annotations

import json
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from phone_use import PhoneUse, PhoneUseAPIError, PhoneUseNetworkError


class APIHandler(BaseHTTPRequestHandler):
    requests: list[tuple[str, str, Any]] = []

    def do_GET(self) -> None:
        self.requests.append(("GET", self.path, None))
        if self.path.endswith("/screenshot") or "/screenshot?" in self.path:
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.end_headers()
            self.wfile.write(b"\x89PNG\r\n\x1a\n")
            return
        self._json(200, {"ok": True, "path": self.path})

    def do_POST(self) -> None:
        payload = self._payload()
        self.requests.append(("POST", self.path, payload))
        if self.path == "/error":
            self._json(409, {"error": {"message": "automation is busy"}})
            return
        delay_s = payload.get("delay_s")
        if (
            isinstance(delay_s, (int, float))
            and not isinstance(delay_s, bool)
        ):
            time.sleep(float(delay_s))
        self._json(200, {"ok": True, "payload": payload})

    def do_DELETE(self) -> None:
        payload = self._payload()
        self.requests.append(("DELETE", self.path, payload))
        self._json(200, {"ok": True, "payload": payload})

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _payload(self) -> Any:
        length = int(self.headers.get("Content-Length", "0"))
        return json.loads(self.rfile.read(length) or b"{}")

    def _json(self, status: int, value: Any) -> None:
        body = json.dumps(value).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class PhoneUseTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), APIHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.client = PhoneUse(
            f"http://127.0.0.1:{cls.server.server_port}",
            device_id="phone one",
            model_name="test-model",
            model_api_key="test-key",
            model_base_url="https://models.example/v1",
            model_family="test-family",
            model_reasoning_enabled=False,
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def setUp(self) -> None:
        APIHandler.requests.clear()

    def test_health_and_devices(self) -> None:
        self.client.health()
        self.assertEqual(APIHandler.requests[-1], ("GET", "/healthz", None))
        self.client.list_devices()
        self.assertEqual(APIHandler.requests[-1], ("GET", "/v1/devices", None))
        self.client.get_device()
        self.assertEqual(
            APIHandler.requests[-1],
            ("GET", "/v1/devices/phone%20one", None),
        )

    def test_screenshot_and_save(self) -> None:
        self.assertTrue(self.client.screenshot(source="snapshot").startswith(b"\x89PNG"))
        self.assertEqual(
            APIHandler.requests[-1],
            ("GET", "/v1/devices/phone%20one/screenshot?source=snapshot", None),
        )
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "screen.png"
            self.assertEqual(self.client.save_screenshot(output), output)
            self.assertTrue(output.read_bytes().startswith(b"\x89PNG"))

    def test_act_query_and_wait(self) -> None:
        self.client.act("Open Settings", timeout_s=20, park_after=None)
        self.assertEqual(
            APIHandler.requests[-1],
            (
                "POST",
                "/v1/devices/phone%20one/act",
                {
                    "instruction": "Open Settings",
                    "timeout_s": 20,
                    "model": {
                        "name": "test-model",
                        "api_key": "test-key",
                        "base_url": "https://models.example/v1",
                        "family": "test-family",
                        "reasoning_enabled": False,
                    },
                },
            ),
        )
        self.client.query_string("Read the title", screenshot_included=True)
        self.assertEqual(APIHandler.requests[-1][1], "/v1/devices/phone%20one/query-string")
        self.assertEqual(APIHandler.requests[-1][2]["model"]["name"], "test-model")
        self.client.wait_for("The Settings screen is visible", timeout_ms=30000)
        self.assertEqual(APIHandler.requests[-1][1], "/v1/devices/phone%20one/wait-for")
        self.assertEqual(APIHandler.requests[-1][2]["model"]["name"], "test-model")

    def test_model_override(self) -> None:
        self.client.act(
            "Open Settings",
            model={"name": "override-model", "reasoning_enabled": True},
        )
        self.assertEqual(
            APIHandler.requests[-1][2]["model"],
            {"name": "override-model", "reasoning_enabled": True},
        )

    def test_coordinate_actions(self) -> None:
        self.client.tap(12.5, 30, park_after=True)
        self.assertNotIn("model", APIHandler.requests[-1][2])
        self.assertEqual(
            APIHandler.requests[-1],
            (
                "POST",
                "/v1/devices/phone%20one/actions/tap",
                {"x": 12.5, "y": 30, "park_after": True},
            ),
        )
        self.client.tap_sequence([(1, 2), (3, 4)])
        self.assertEqual(
            APIHandler.requests[-1][2]["points"],
            [[1, 2], [3, 4]],
        )
        self.client.swipe(10, 100, 10, 20, hold_s=0.2)
        self.assertEqual(APIHandler.requests[-1][2]["hold_s"], 0.2)

    def test_named_action_and_text(self) -> None:
        self.client.named_action("home")
        self.assertEqual(
            APIHandler.requests[-1][2],
            {"name": "home"},
        )
        self.client.type_text("Alice", clear_first=True)
        self.assertEqual(
            APIHandler.requests[-1],
            (
                "POST",
                "/v1/devices/phone%20one/type-text",
                {"text": "Alice", "clear_first": True},
            ),
        )

    def test_task_lifecycle(self) -> None:
        self.client.start_task("ai_act", args={"instruction": "Open Settings"})
        self.assertEqual(
            APIHandler.requests[-1][2],
            {
                "task_type": "ai_act",
                "args": {
                    "instruction": "Open Settings",
                    "model": {
                        "name": "test-model",
                        "api_key": "test-key",
                        "base_url": "https://models.example/v1",
                        "family": "test-family",
                        "reasoning_enabled": False,
                    },
                },
            },
        )
        self.client.get_task("task/1")
        self.assertEqual(
            APIHandler.requests[-1][1],
            "/v1/devices/phone%20one/tasks/task%2F1",
        )
        self.client.list_tasks(status="running", limit=5)
        self.assertEqual(
            APIHandler.requests[-1][1],
            "/v1/devices/phone%20one/tasks?status=running&limit=5",
        )
        self.client.cancel_task("task/1", reason="no longer needed")
        self.assertEqual(
            APIHandler.requests[-1],
            (
                "DELETE",
                "/v1/devices/phone%20one/tasks/task%2F1",
                {"reason": "no longer needed"},
            ),
        )

    def test_validation(self) -> None:
        with self.assertRaises(ValueError):
            self.client.act(" ")
        with self.assertRaises(ValueError):
            self.client.tap_sequence([])
        with self.assertRaises(ValueError):
            self.client.list_tasks(limit=0)
        with self.assertRaises(ValueError):
            PhoneUse(device_id="")
        with self.assertRaises(ValueError):
            PhoneUse(timeout=0)
        with self.assertRaises(ValueError):
            PhoneUse(model_name=" ")
        with self.assertRaises(ValueError):
            self.client.act("task", model="bad")

    def test_api_error(self) -> None:
        with self.assertRaises(PhoneUseAPIError) as raised:
            self.client._request_json("POST", "/error", {})
        self.assertEqual(raised.exception.status_code, 409)
        self.assertEqual(raised.exception.message, "automation is busy")

    def test_network_error(self) -> None:
        client = PhoneUse("http://127.0.0.1:1", timeout=0.1)
        with self.assertRaises(PhoneUseNetworkError):
            client.health()

    def test_timeout_s_extends_socket_timeout(self) -> None:
        # A short constructor timeout should not cut off a request that
        # explicitly asked the server for a longer timeout_s/timeout_ms.
        client = PhoneUse(
            f"http://127.0.0.1:{self.server.server_port}",
            device_id="phone one",
            timeout=0.5,
        )
        result = client.act("Open Settings", timeout_s=3, delay_s=1.2)
        self.assertTrue(result["ok"])

    def test_without_override_short_timeout_still_applies(self) -> None:
        # Without a per-request timeout_s/timeout_ms, the constructor's
        # timeout is still the effective ceiling.
        client = PhoneUse(
            f"http://127.0.0.1:{self.server.server_port}",
            device_id="phone one",
            timeout=0.3,
        )
        with self.assertRaises(PhoneUseNetworkError):
            client.tap(1, 2, delay_s=0.8)

    def test_resolve_timeout(self) -> None:
        client = PhoneUse(
            f"http://127.0.0.1:{self.server.server_port}", timeout=10
        )
        self.assertEqual(client._resolve_timeout({}), 10)
        self.assertEqual(client._resolve_timeout({"timeout_s": 60}), 65)
        self.assertEqual(client._resolve_timeout({"timeout_ms": 30_000}), 35)
        self.assertEqual(client._resolve_timeout({"timeout_s": 1}), 10)


if __name__ == "__main__":
    unittest.main()
