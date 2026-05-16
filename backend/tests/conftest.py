"""Shared pytest fixtures."""

import os
import socket
import sys
from pathlib import Path

import pytest
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
load_dotenv(Path(__file__).resolve().parent.parent / ".env")


def _port_reachable(host: str, port: int, timeout: float = 1.0) -> bool:
    s = socket.socket()
    s.settimeout(timeout)
    try:
        s.connect((host, port))
        return True
    except Exception:
        return False
    finally:
        s.close()


@pytest.fixture(scope="session")
def backend_base_url() -> str:
    url = os.getenv("E2E_BASE_URL", "http://localhost:8000")
    return url


@pytest.fixture(scope="session")
def invite_code() -> str:
    code = os.getenv("SUPER_ADMIN_CODE")
    if not code:
        pytest.skip("SUPER_ADMIN_CODE not set in environment")
    return code


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "requires_backend: test needs a live backend + Hardhat RPC; auto-skips if either is unreachable",
    )


@pytest.fixture
def require_running_backend(backend_base_url, request):
    """Skip the test if backend/Hardhat aren't reachable.

    Opt-in via `@pytest.mark.requires_backend`. Pure unit tests that exercise
    hash primitives only (no HTTP, no chain) run without this fixture and stay
    green under plain `pytest`.
    """
    import urllib.parse

    parsed = urllib.parse.urlparse(backend_base_url)
    host = parsed.hostname or "localhost"
    port = parsed.port or 8000
    if not _port_reachable(host, port):
        pytest.skip(f"Backend not reachable at {backend_base_url} — skipping integration tests")

    rpc = os.getenv("BLOCKCHAIN_RPC_URL", "http://127.0.0.1:8545")
    rpc_parsed = urllib.parse.urlparse(rpc)
    if not _port_reachable(rpc_parsed.hostname or "127.0.0.1", rpc_parsed.port or 8545):
        pytest.skip(f"Blockchain RPC not reachable at {rpc} — skipping integration tests")


@pytest.fixture(autouse=True)
def _auto_require_backend_for_marked(request):
    """Auto-applies the backend reachability check to any test marked
    `@pytest.mark.requires_backend`. Lets us keep the integration suite
    behind a single decorator without re-running the port check for plain
    unit tests."""
    if request.node.get_closest_marker("requires_backend"):
        request.getfixturevalue("require_running_backend")
