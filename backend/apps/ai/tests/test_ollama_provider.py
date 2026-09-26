"""
Ollama transport contract.

Ollama is not installed or running in CI, so these tests cannot prove a real
model round-trips. They do prove the parts that are ours: the request we build,
the envelope we read, and the way each HTTP failure mode is translated into the
application's error types. The stub below speaks Ollama's wire format.

What this does NOT cover: that a real local model produces output that passes
:mod:`apps.ai.validators`. That needs a running daemon and is a manual check
(see docs/AI_SETUP.md).
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from django.test import SimpleTestCase, override_settings

from apps.ai.exceptions import (
    AIProviderResponseError,
    AIProviderTimeoutError,
    AIProviderUnavailableError,
)
from apps.ai.providers.base import TailoringRequest
from apps.ai.providers.ollama import OllamaProvider

from .fixtures import valid_payload

#: One slot each for the mode the next request should use.
MODE = {"value": "ok"}


class _Handler(BaseHTTPRequestHandler):
    """Minimal Ollama daemon stand-in."""

    def log_message(self, *args):  # silence test output
        pass

    def _send(self, code, payload):
        body = json.dumps(payload).encode()
        try:
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
            # Expected in the timeout test: the client hangs up mid-response.
            # Without this the stub prints a traceback that looks like a failure.
            self.close_connection = True

    def do_GET(self):
        if self.path == "/api/tags":
            self._send(200, {"models": [{"name": "llama3.1:latest"}]})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        if MODE["value"] == "slow":
            import time
            time.sleep(2.5)
        length = int(self.headers.get("Content-Length", 0))
        request = json.loads(self.rfile.read(length) or b"{}")

        if MODE["value"] == "ok":
            self._send(200, {
                "model": request.get("model"),
                "done": True,
                "message": {"role": "assistant", "content": json.dumps(valid_payload())},
            })
        elif MODE["value"] == "toplevel":
            # Some builds put the text at the top level instead of in "message".
            self._send(200, {"response": json.dumps(valid_payload()), "done": True})
        elif MODE["value"] == "missing-model":
            self._send(404, {"error": "model not found"})
        elif MODE["value"] == "server-error":
            self._send(500, {"error": "boom"})
        elif MODE["value"] == "empty":
            self._send(200, {"message": {"content": ""}, "done": True})
        elif MODE["value"] == "garbage":
            body = b"not json at all"
            try:
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
                self.close_connection = True


class OllamaProviderTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.server = HTTPServer(("127.0.0.1", 0), _Handler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        super().tearDownClass()

    def setUp(self):
        MODE["value"] = "ok"
        self.base = "http://127.0.0.1:%d" % self.port

    def provider(self, **kwargs):
        return OllamaProvider(
            base_url=self.base, model="llama3.1", timeout=10, **kwargs
        )

    def request(self):
        return TailoringRequest(resume={}, job={}, match={})

    # -- happy path --------------------------------------------------------

    def test_returns_message_content(self):
        raw = self.provider().tailor_resume(self.request())
        self.assertIn('"experience"', raw)

    def test_accepts_top_level_response_field(self):
        MODE["value"] = "toplevel"
        raw = self.provider().tailor_resume(self.request())
        self.assertIn('"experience"', raw)

    def test_health_reports_ready_when_model_is_installed(self):
        ok, message = self.provider().health()
        self.assertTrue(ok, message)

    # -- failure modes -----------------------------------------------------

    def test_missing_model_suggests_pull(self):
        MODE["value"] = "missing-model"
        with self.assertRaises(AIProviderUnavailableError) as ctx:
            self.provider().tailor_resume(self.request())
        self.assertIn("ollama pull", ctx.exception.message.lower())

    def test_server_error_is_unavailable_not_a_crash(self):
        MODE["value"] = "server-error"
        with self.assertRaises(AIProviderUnavailableError):
            self.provider().tailor_resume(self.request())

    def test_empty_content_is_a_response_error(self):
        MODE["value"] = "empty"
        with self.assertRaises(AIProviderResponseError):
            self.provider().tailor_resume(self.request())

    def test_non_json_body_is_a_response_error(self):
        MODE["value"] = "garbage"
        with self.assertRaises(AIProviderResponseError):
            self.provider().tailor_resume(self.request())

    def test_unreachable_daemon_is_unavailable(self):
        # A port that was bound and released is guaranteed to refuse connections.
        import socket
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            closed_port = probe.getsockname()[1]
        provider = OllamaProvider(
            base_url="http://127.0.0.1:%d" % closed_port, model="llama3.1", timeout=3
        )
        with self.assertRaises(AIProviderUnavailableError):
            provider.tailor_resume(self.request())

    def test_slow_daemon_is_a_timeout(self):
        MODE["value"] = "slow"
        provider = OllamaProvider(base_url=self.base, model="llama3.1", timeout=1)
        with self.assertRaises(AIProviderTimeoutError):
            provider.tailor_resume(self.request())

    def test_health_is_false_when_daemon_is_down(self):
        import socket
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            closed_port = probe.getsockname()[1]
        provider = OllamaProvider(
            base_url="http://127.0.0.1:%d" % closed_port, model="llama3.1", timeout=3
        )
        ok, message = provider.health()
        self.assertFalse(ok)
        self.assertIn("not reachable", message)

    def test_health_is_false_when_model_is_absent(self):
        provider = OllamaProvider(base_url=self.base, model="not-a-real-model", timeout=5)
        ok, message = provider.health()
        self.assertFalse(ok)
        self.assertIn("not installed", message)

    # -- configuration -----------------------------------------------------

    def test_missing_base_url_is_unavailable(self):
        with override_settings(OLLAMA_BASE_URL=""):
            with self.assertRaises(AIProviderUnavailableError):
                OllamaProvider(model="llama3.1")

    def test_describe_never_leaks_the_url(self):
        described = self.provider().describe()
        self.assertEqual(described["provider"], "ollama")
        self.assertEqual(described["model"], "llama3.1")
        self.assertNotIn("base_url", described)
        self.assertNotIn("http", str(described))

    def test_model_name_is_never_hardcoded(self):
        """The model comes from configuration only."""
        provider = OllamaProvider(base_url=self.base, model="some-other-model", timeout=5)
        self.assertEqual(provider.model, "some-other-model")
