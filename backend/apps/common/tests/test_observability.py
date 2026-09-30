"""
Structured operation logging.

Two properties are load-bearing and both are asserted here rather than trusted
to review:

* a credential cannot reach a log line, whatever name it is passed under;
* a logging call cannot break the operation it is describing.

The format is asserted too, but only loosely -- field *order* and the presence
of the operation/outcome pair. A test that pinned the whole line would fail
every time a useful field was added, which is the wrong thing to discourage.
"""

import logging

from django.test import SimpleTestCase

from apps.common.observability import (
    OperationTimer,
    is_sensitive_name,
    is_sensitive_value,
    log_operation,
    redact_fields,
    render_operation,
)

#: Values shaped like the credential prefixes the redactor looks for. Kept
#: deliberately short: `.github/scripts/scan_source_secrets.py` fails the build on
#: anything resembling a real key in the tree, and widening that scan to allow a
#: longer fixture would be a worse trade than using a shorter one here.
SECRET_VALUES = [
    "AIza1234",  # Google AI Studio
    "gsk_1234",  # Groq / OpenAI, underscore form
    "sk-1234",  # OpenAI / Anthropic, dash form
    "xoxb-1234",  # Slack
    "eyJhbGciOi.payload.signature",  # a JWT
]


class RedactionTests(SimpleTestCase):
    """A credential is refused by name *and* by shape."""

    def test_sensitive_names_are_redacted(self):
        for name in (
            "api_key",
            "apiKey",
            "GEMINI_API_KEY",
            "token",
            "password",
            "secret",
            "credential",
            "authorization",
            "cookie",
            "session_key",
            "prompt",
        ):
            with self.subTest(field=name):
                self.assertTrue(is_sensitive_name(name))
                self.assertEqual(
                    redact_fields({name: "anything"})[name],
                    "[redacted]",
                )

    def test_secret_shaped_values_are_redacted_under_any_name(self):
        for value in SECRET_VALUES:
            with self.subTest(value=value[:8]):
                self.assertTrue(is_sensitive_value(value))
                self.assertEqual(
                    redact_fields({"note": value})["note"],
                    "[redacted]",
                )

    def test_ordinary_fields_survive(self):
        safe = redact_fields(
            {
                "provider": "ollama",
                "model": "llama3.1",
                "validation": "valid",
                "duration_ms": 1200,
                "cached": False,
                "not_set": None,
            }
        )

        self.assertEqual(safe["provider"], "ollama")
        self.assertEqual(safe["model"], "llama3.1")
        self.assertEqual(safe["duration_ms"], "1200")
        self.assertEqual(safe["cached"], "false")
        self.assertEqual(safe["not_set"], "")

    def test_a_resume_body_is_summarised_not_copied(self):
        """A container reports its size: a resume has no business in a log."""
        safe = redact_fields({"resume": {"skills": ["python", "django"]}})
        self.assertNotIn("python", safe["resume"])
        self.assertLessEqual(len(safe["resume"]), 160)

    def test_redaction_does_not_mutate_the_caller(self):
        fields = {"api_key": "gsk_secret_value"}
        redact_fields(fields)
        self.assertEqual(fields["api_key"], "gsk_secret_value")


class RenderTests(SimpleTestCase):
    """The line is stable, ordered and single-line."""

    def test_order_is_operation_outcome_duration_then_sorted_fields(self):
        line = render_operation(
            "resume_tailoring",
            outcome="ok",
            duration_ms=812,
            user=7,
            provider="ollama",
        )

        self.assertEqual(
            line,
            "operation=resume_tailoring outcome=ok duration_ms=812 "
            "provider=ollama user=7",
        )

    def test_the_line_is_never_multi_line(self):
        line = render_operation("resume_tailoring", note="one\ntwo\r\nthree")
        self.assertNotIn("\n", line)
        self.assertIn("note=one two three", line)

    def test_no_secret_appears_in_a_rendered_line(self):
        line = render_operation(
            "resume_tailoring",
            api_key=SECRET_VALUES[0],
            note=SECRET_VALUES[1],
        )

        for value in SECRET_VALUES[:2]:
            self.assertNotIn(value, line)


class LogOperationTests(SimpleTestCase):
    """Emission goes through the logging tree, and cannot raise."""

    def test_a_line_reaches_the_operations_logger(self):
        with self.assertLogs("tailorup.operations", level="INFO") as captured:
            log_operation("resume_tailoring", provider="ollama", user=3)

        self.assertEqual(len(captured.records), 1)
        message = captured.records[0].getMessage()
        self.assertIn("operation=resume_tailoring", message)
        self.assertIn("provider=ollama", message)

    def test_a_broken_log_sink_does_not_break_the_caller(self):
        """
        The whole point of the guard inside ``log_operation``: it is called on
        the success path of real work, so a broken handler must cost a log line
        and not the result.
        """

        class Exploding(logging.Handler):
            def emit(self, record):
                raise RuntimeError("log sink is down")

        logger = logging.getLogger("tailorup.operations")
        handler = Exploding()
        logger.addHandler(handler)
        self.addCleanup(logger.removeHandler, handler)

        # No assertRaises: the call completing *is* the assertion.
        log_operation("resume_tailoring", user=1)


class OperationTimerTests(SimpleTestCase):
    """Success and failure both produce a duration."""

    def test_success_logs_ok_and_a_duration(self):
        with self.assertLogs("tailorup.operations", level="INFO") as captured:
            with OperationTimer("resume_tailoring", user=1) as timer:
                timer.add(provider="ollama")

        message = captured.records[0].getMessage()
        self.assertIn("outcome=ok", message)
        self.assertIn("duration_ms=", message)
        self.assertIn("provider=ollama", message)
        self.assertIsNotNone(timer.duration_ms)

    def test_failure_is_logged_at_warning_and_the_exception_propagates(self):
        with self.assertLogs("tailorup.operations", level="WARNING") as captured:
            with self.assertRaises(ValueError):
                with OperationTimer("resume_tailoring", user=1):
                    raise ValueError("provider said something private")

        message = captured.records[0].getMessage()
        self.assertIn("outcome=error", message)
        self.assertIn("error=ValueError", message)
        # The message is not ours to log: it can carry a base URL or a body.
        self.assertNotIn("private", message)
