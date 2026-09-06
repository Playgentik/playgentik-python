"""Client() construction paths - api_key skips login() entirely (no
network mocking needed for that: there's no request to make), so these
run offline like everything else in this suite.
"""

import pytest

from playgentik.client import Client


def test_client_with_api_key_skips_login_entirely():
    agent = Client("https://x", api_key="pk_live_abc123")

    assert agent.rest.api_key == "pk_live_abc123"
    assert agent.rest.token is None  # login() was never called


def test_client_requires_api_key_or_credentials_when_auto_login():
    with pytest.raises(ValueError):
        Client("https://x")


def test_client_auto_login_false_requires_nothing_up_front():
    agent = Client("https://x", auto_login=False)

    assert agent.rest.token is None
    assert agent.rest.api_key is None


def test_client_login_without_credentials_raises():
    agent = Client("https://x", auto_login=False)

    with pytest.raises(ValueError):
        agent.login()
