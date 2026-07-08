"""Flatten a ScrapedPost into a compact research dict.

Kept lean so a 20-post search stays token-light, while preserving every field a
research/discovery workflow actually uses — engagement stats, author, sound, and
the media URLs needed to call fetch_tiktok_media next.
"""

from __future__ import annotations

from .schema import ScrapedPost


def post_to_research_dict(post: ScrapedPost) -> dict:
    a = post.author_meta
    m = post.music_meta
    v = post.video_meta
    return {
        "id": post.id,
        "url": post.web_video_url,
        "caption": post.text,
        "created_at": post.create_time_iso.isoformat() if post.create_time_iso else None,
        "is_slideshow": post.is_slideshow,
        "stats": {
            "views": post.play_count,
            "likes": post.digg_count,
            "comments": post.comment_count,
            "shares": post.share_count,
            "saves": post.collect_count,
        },
        "author": (
            {
                "name": a.name,
                "nickname": a.nick_name,
                "fans": a.fans,
                "verified": a.verified,
                "profile_url": a.profile_url,
            }
            if a
            else None
        ),
        "music": (
            {
                "name": m.music_name,
                "author": m.music_author,
                "id": m.music_id,
                "original": m.music_original,
            }
            if m
            else None
        ),
        "duration_s": v.duration if v else 0,
        "hashtags": post.hashtags,
        # Media URLs (not bytes) — pass these to fetch_tiktok_media for visual analysis.
        "cover_url": v.cover_url if v else "",
        "original_cover_url": v.original_cover_url if v else "",
        "slideshow_image_links": post.slideshow_image_links,
        "is_ad": post.is_ad,
        "is_sponsored": post.is_sponsored,
        "language": post.text_language,
    }
