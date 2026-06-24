"""ScrapedPost parsing regression tests.

The clockworks/tiktok-scraper actor returns `hashtags` as a list of OBJECTS
({id, name, title, cover}) for some posts and as bare strings for others. The
schema types the field as list[str]; without coercion the object form raised a
ValidationError, get_dataset_posts silently dropped the only item, and the clone
flow surfaced a misleading "Couldn't fetch this TikTok reference — check the URL"
even though the scrape had SUCCEEDED. These tests lock in the normalization.
"""

from service.apify.schema import ScrapedPost


def _raw(**overrides):
    base = {
        "id": "7612070011565296927",
        "text": "being an alt baddie with bangs",
        "webVideoUrl": "https://www.tiktok.com/@wtvrkaylei/video/7612070011565296927",
        "isSlideshow": False,
        "diggCount": 10,
    }
    base.update(overrides)
    return base


def test_hashtags_as_objects_are_coerced_to_names():
    """The actor's object form must parse, not drop the post."""
    raw = _raw(hashtags=[
        {"name": ""},  # blank — dropped
        {"id": "362147", "name": "alternativegirl", "title": "", "cover": ""},
        {"id": "5342", "name": "bangs"},
    ])
    post = ScrapedPost.model_validate(raw)
    assert post.id == "7612070011565296927"
    assert post.hashtags == ["alternativegirl", "bangs"]


def test_hashtags_as_strings_still_work():
    """The bare-string form (older actor output) is unchanged."""
    post = ScrapedPost.model_validate(_raw(hashtags=["bangs", " grunge ", ""]))
    assert post.hashtags == ["bangs", "grunge"]


def test_hashtags_missing_defaults_empty():
    post = ScrapedPost.model_validate(_raw())
    assert post.hashtags == []


def test_hashtags_garbage_entries_dropped():
    post = ScrapedPost.model_validate(_raw(hashtags=[None, 123, {"no_name": "x"}, "ok"]))
    assert post.hashtags == ["ok"]
