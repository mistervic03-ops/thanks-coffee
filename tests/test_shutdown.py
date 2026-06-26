import os
import signal
import unittest
from unittest.mock import patch


os.environ.setdefault("SLACK_BOT_TOKEN", "xoxb-test")
os.environ.setdefault("SLACK_APP_TOKEN", "xapp-test")
os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost/db")
os.environ.setdefault("FEED_CHANNEL_ID", "C123")

import app as app_module  # noqa: E402


class FakeLogger:
    def __init__(self):
        self.info_events = []
        self.error_events = []

    def info(self, message, extra=None):
        self.info_events.append(extra["event"])

    def error(self, message, extra=None):
        self.error_events.append(extra["event"])


class FakeSocketModeHandler:
    def __init__(self, raise_keyboard_interrupt=False):
        self.closed = False
        self.raise_keyboard_interrupt = raise_keyboard_interrupt

    def close(self):
        self.closed = True

    def start(self):
        if self.raise_keyboard_interrupt:
            raise KeyboardInterrupt()


class FakeScheduler:
    def __init__(self):
        self.shutdown_calls = []

    def shutdown(self, **kwargs):
        self.shutdown_calls.append(kwargs)


class ShutdownTest(unittest.TestCase):
    def setUp(self):
        app_module.socket_mode_handler = None
        app_module.scheduler_instance = None
        app_module._shutdown_started = False

    def tearDown(self):
        app_module.socket_mode_handler = None
        app_module.scheduler_instance = None
        app_module._shutdown_started = False

    def test_signal_handlers_are_registered(self):
        with patch.object(app_module.signal, "signal") as signal_fn:
            app_module.register_signal_handlers()

        signal_fn.assert_any_call(signal.SIGTERM, app_module.shutdown)
        signal_fn.assert_any_call(signal.SIGINT, app_module.shutdown)
        self.assertEqual(signal_fn.call_count, 2)

    def test_shutdown_closes_socket_scheduler_db_and_logs_shutdown(self):
        fake_logger = FakeLogger()
        socket_handler = FakeSocketModeHandler()
        scheduler = FakeScheduler()
        app_module.socket_mode_handler = socket_handler
        app_module.scheduler_instance = scheduler

        with patch.object(app_module, "logger", fake_logger), \
            patch.object(app_module, "wait_for_requests", return_value=True) as wait_for_requests, \
            patch.object(app_module, "close_connection") as close_connection:
            with self.assertRaises(SystemExit) as ctx:
                app_module.shutdown(signal.SIGTERM, None)

        self.assertEqual(ctx.exception.code, 0)
        self.assertTrue(socket_handler.closed)
        wait_for_requests.assert_called_once_with(timeout=10)
        self.assertEqual(scheduler.shutdown_calls, [{"wait": True, "timeout": 10}])
        close_connection.assert_called_once()
        self.assertIn("app_shutdown_started", fake_logger.info_events)
        self.assertIn("app_shutdown", fake_logger.info_events)

    def test_keyboard_interrupt_uses_same_shutdown_flow(self):
        fake_logger = FakeLogger()
        socket_handler = FakeSocketModeHandler(raise_keyboard_interrupt=True)

        with patch.object(app_module, "configure_logging"), \
            patch.object(app_module, "register_signal_handlers"), \
            patch.object(app_module, "create_bolt_app", return_value=object()), \
            patch.object(app_module, "init_db"), \
            patch.object(app_module, "retry_failed_feeds"), \
            patch.object(app_module, "SocketModeHandler", return_value=socket_handler), \
            patch.object(app_module, "SCHEDULER_ENABLED", False), \
            patch.object(app_module, "HEALTH_CHECK_ENABLED", False), \
            patch.object(app_module, "logger", fake_logger), \
            patch.object(app_module, "wait_for_requests", return_value=True), \
            patch.object(app_module, "close_connection"):
            with self.assertRaises(SystemExit) as ctx:
                app_module.run_app()

        self.assertEqual(ctx.exception.code, 0)
        self.assertTrue(socket_handler.closed)
        self.assertIn("app_shutdown_started", fake_logger.info_events)
        self.assertIn("app_shutdown", fake_logger.info_events)


if __name__ == "__main__":
    unittest.main()
