"""verify_batch must return a clean 404 (not a 500) when the chain read fails
because the contract isn't deployed / chain not synced (0-byte read ->
BadFunctionCallOutput)."""
import pytest
from fastapi import HTTPException
from web3.exceptions import BadFunctionCallOutput
import app.routers.batch as bmod


def test_verify_batch_chain_unavailable_returns_404(monkeypatch):
    # Bypass _check_blockchain so we reach the chain-read block.
    monkeypatch.setattr(bmod, "_check_blockchain", lambda: None)

    def _boom(_bytes):
        raise BadFunctionCallOutput("no code at address")
    monkeypatch.setattr(bmod.blockchain_service, "get_batch", _boom, raising=False)

    with pytest.raises(HTTPException) as ei:
        bmod.verify_batch("0x" + "ab" * 32, db=None)  # db never reached (raises before query)
    assert ei.value.status_code == 404
    assert "not found on chain" in str(ei.value.detail).lower()
