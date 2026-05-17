"""Sprint 6 unit tests for the RPC retry layer.

Covers:
  - `_retry_rpc` retries on transient errors and eventually succeeds
  - `_retry_rpc` does not retry on `ContractLogicError`
  - `_retry_rpc` gives up after `RPC_RETRY_ATTEMPTS` and re-raises
  - `ReceiptPendingError` exposes the broadcast tx hash

No chain or DB required.
"""

import time
from unittest.mock import MagicMock

import pytest
from web3.exceptions import ContractLogicError, TimeExhausted

from app.services import blockchain as bc_module
from app.services.blockchain import (
    BlockchainService,
    ReceiptPendingError,
    _retry_rpc,
)


@pytest.fixture(autouse=True)
def _tight_retry_cadence(monkeypatch):
    """Keep tests sub-second by collapsing the backoff sleeps."""
    monkeypatch.setattr(bc_module, "RPC_RETRY_INITIAL_DELAY_S", 0)
    monkeypatch.setattr(bc_module, "RPC_RETRY_MAX_DELAY_S", 0)


def test_retry_succeeds_after_transient_failures():
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise ConnectionError("RPC reset")
        return "ok"

    assert _retry_rpc(flaky) == "ok"
    assert calls["n"] == 3


def test_retry_does_not_retry_contract_logic_error():
    calls = {"n": 0}

    def revert():
        calls["n"] += 1
        raise ContractLogicError("execution reverted: bad state")

    with pytest.raises(ContractLogicError):
        _retry_rpc(revert)
    assert calls["n"] == 1


def test_retry_gives_up_after_max_attempts():
    calls = {"n": 0}

    def always_fail():
        calls["n"] += 1
        raise ConnectionError("permanent outage")

    with pytest.raises(ConnectionError):
        _retry_rpc(always_fail)
    assert calls["n"] == bc_module.RPC_RETRY_ATTEMPTS


def test_receipt_pending_error_carries_tx_hash():
    err = ReceiptPendingError("0xabc123")
    assert err.tx_hash == "0xabc123"
    assert "0xabc123" in str(err)


def test_wait_for_receipt_raises_pending_when_ceiling_exceeded(monkeypatch):
    """Drive `_wait_for_receipt` with a fake w3.eth that always TimeExhausts.

    A real BlockchainService init pulls env + ABIs; bypass __init__ entirely
    and inject a hand-rolled w3 mock. We also collapse the poll cadence and
    the ceiling so the test runs instantly.
    """
    monkeypatch.setattr(bc_module, "RECEIPT_POLL_INITIAL_S", 0)
    monkeypatch.setattr(bc_module, "RECEIPT_POLL_MAX_S", 0)
    monkeypatch.setattr(bc_module, "RECEIPT_CEILING_S", 0)

    svc = BlockchainService.__new__(BlockchainService)
    svc.w3 = MagicMock()
    svc.w3.eth.wait_for_transaction_receipt.side_effect = TimeExhausted("nope")

    tx_hash = MagicMock()
    tx_hash.hex.return_value = "0xdeadbeef"

    with pytest.raises(ReceiptPendingError) as exc:
        svc._wait_for_receipt(tx_hash)
    assert exc.value.tx_hash == "0xdeadbeef"
