"""What a tool result looks like once the recorder has written it.

`agent_events` is the one table every reload and every session bundle reads
back, so what goes in is what every later reader pays for.
"""

from __future__ import annotations

from agents.content.persistence import _IMAGE_BYTES_PLACEHOLDER, _MAX_TOOL_PAYLOAD, _jsonable


def test_an_images_bytes_never_enter_the_transcript():
    """A generate_image result carries a 150–400 KB base64 picture, under the
    payload cap, so it used to be written whole; the model saw it once and
    the file is at the asset_url."""
    picture = "A" * 200_000
    result = {
        "asset_url": "/media/x.jpg",
        "content": [
            {"type": "text", "text": "Made it."},
            {"type": "image", "base64": picture, "mime_type": "image/jpeg"},
        ],
        "nested": {"blocks": [{"type": "image", "data": picture, "mime_type": "image/png"}]},
    }

    stored = _jsonable(result)

    for block in (stored["content"][1], stored["nested"]["blocks"][0]):
        assert picture not in block.values()
        assert _IMAGE_BYTES_PLACEHOLDER in block.values()
        assert block["base64_chars"] == 200_000
        assert block["mime_type"] in ("image/jpeg", "image/png")
    assert stored["content"][0] == {"type": "text", "text": "Made it."}
    assert stored["asset_url"] == "/media/x.jpg"
    assert "_truncated" not in stored


def test_a_text_payload_past_the_cap_is_still_a_preview():
    stored = _jsonable({"text": "x" * (_MAX_TOOL_PAYLOAD + 1)})
    assert stored["_truncated"] is True
