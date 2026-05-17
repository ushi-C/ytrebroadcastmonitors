from __future__ import annotations

from ..models.network_state_store import NetworkStateStore

NETWORK_STATE_STORE = NetworkStateStore()


def get_network_status() -> dict:
    return NETWORK_STATE_STORE.get_snapshot()


def report_network_status(youtube_available: bool, reason: str) -> dict:
    return NETWORK_STATE_STORE.report(youtube_available=youtube_available, reason=reason)


def request_network_check() -> dict:
    return NETWORK_STATE_STORE.request_check()


def consume_network_check_request() -> bool:
    return NETWORK_STATE_STORE.consume_check_request()


def can_run_youtube_workflows() -> bool:
    status = NETWORK_STATE_STORE.get_snapshot()
    return bool(status.get("youtube_available"))
