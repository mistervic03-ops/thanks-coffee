import threading
import time
from contextlib import contextmanager
from functools import wraps


_condition = threading.Condition()
_active_requests = 0


@contextmanager
def track_request():
    begin_request()
    try:
        yield
    finally:
        end_request()


def begin_request():
    global _active_requests
    with _condition:
        _active_requests += 1


def end_request():
    global _active_requests
    with _condition:
        _active_requests = max(_active_requests - 1, 0)
        if _active_requests == 0:
            _condition.notify_all()


def wait_for_requests(timeout=10):
    deadline = time.monotonic() + timeout
    with _condition:
        while _active_requests > 0:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            _condition.wait(remaining)
    return True


def tracked_handler(handler):
    @wraps(handler)
    def wrapper(*args, **kwargs):
        with track_request():
            return handler(*args, **kwargs)

    return wrapper
