"""Root test configuration; makes the repository root importable to tests.

Windows note: pytest-homeassistant-custom-component blocks socket creation to
keep tests offline. That works on Linux (asyncio's socketpair is an os-level
syscall there), but on Windows the Proactor event loop must create AF_INET
sockets for its self-pipe, so every test would fail in the event_loop fixture
before running a single line. We therefore neutralize the socket block on
Windows only; on Linux/CI the offline guarantee stays fully intact.
"""

import json
import sys
from pathlib import Path
from typing import Any

import pytest

if sys.platform == "win32":
    import pytest_socket

    pytest_socket.disable_socket = lambda *args, **kwargs: None

FIXTURE_DIR = Path(__file__).parent / "tests" / "fixtures"


@pytest.fixture
def load_fixture():
    """Load a recorded API response fixture by file name."""

    def _load(name: str) -> Any:
        return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))

    return _load


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Make the custom component under custom_components/ discoverable."""
    yield
