"""The preset table's shared-client flag.

A preset marked ``pre_registered`` names a vendor whose server publishes no
dynamic client registration: one client for every install, its secret held in
settings rather than on a connection. Everything else here is registered per
install by DCR, and the flag must not leak onto them.
"""

from __future__ import annotations

from service.mcp.presets import PRESETS, is_shared_client, preset, preset_for_url

HUBSPOT = "https://mcp.hubspot.com"


def test_hubspot_is_a_shared_client():
    assert is_shared_client(HUBSPOT)


def test_every_non_pre_registered_preset_is_registered_dynamically():
    for p in PRESETS:
        if p.pre_registered:
            continue
        assert not is_shared_client(p.url)


def test_an_address_no_preset_claims_is_not_a_shared_client():
    assert not is_shared_client("https://mcp.vendor.test/mcp")


def test_the_hubspot_preset_carries_no_key_and_asks_first():
    found = preset("hubspot")
    assert found is not None
    assert found.pre_registered is True
    assert found.key_url == ""
    assert found.trust_read_only is False
    assert preset_for_url(HUBSPOT) is found