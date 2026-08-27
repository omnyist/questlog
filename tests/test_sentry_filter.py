from __future__ import annotations

from config.settings import _sentry_before_send


def _event_with_frames(*filenames):
    return {
        "exception": {
            "values": [{"stacktrace": {"frames": [{"filename": f} for f in filenames]}}]
        }
    }


class TestSentryBeforeSend:
    def test_drops_disallowed_host(self):
        assert _sentry_before_send({"logger": "django.security.DisallowedHost"}, {}) is None

    def test_drops_interactive_shell_traceback(self):
        event = _event_with_frames("apps/library/models.py", "<stdin>")
        assert _sentry_before_send(event, {}) is None

    def test_drops_python_dash_c_one_liner(self):
        # `docker exec ... python -c "..."` names its program "<string>" and it
        # is the outermost frame. QUESTLOG-5 was a typo in exactly this shape.
        event = _event_with_frames("<string>")
        assert _sentry_before_send(event, {}) is None

    def test_drops_console_frame(self):
        event = _event_with_frames("manage.py", "<console>")
        assert _sentry_before_send(event, {}) is None

    def test_keeps_library_exec_frame_deep_in_a_real_stack(self):
        # Libraries build classes with exec() and leave "<string>" behind.
        # Matching that anywhere would bin genuine production errors, so
        # "<string>" only counts as the outermost frame.
        event = _event_with_frames("apps/library/api.py", "<string>", "pydantic/main.py")
        assert _sentry_before_send(event, {}) is event

    def test_keeps_real_server_traceback(self):
        event = _event_with_frames("apps/profiles/warframe/tasks.py", "httpx/_client.py")
        assert _sentry_before_send(event, {}) is event

    def test_keeps_event_without_exception(self):
        event = {"message": "something logged"}
        assert _sentry_before_send(event, {}) is event

    def test_redacts_url_secret_in_exception_message(self):
        event = {
            "exception": {
                "values": [
                    {
                        "value": (
                            "HTTPStatusError: 502 for url "
                            "'https://api.steampowered.com/x?key=SECRET123&steamids=42'"
                        ),
                        "stacktrace": {"frames": [{"filename": "apps/integrations/steam.py"}]},
                    }
                ]
            }
        }
        out = _sentry_before_send(event, {})
        value = out["exception"]["values"][0]["value"]
        assert "SECRET123" not in value
        assert "key=[Filtered]" in value
        assert "steamids=42" in value  # non-secret params preserved
