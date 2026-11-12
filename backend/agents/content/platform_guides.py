"""What each publishing channel wants, as the content agent and the app read it.

One table, by platform: the formats the channel takes, the limits the post has
to fit, what its feed rewards, what it punishes, and a posting cadence. The
agent gets the guides for the channels a project posts on in its opening turn
(prompts._brand_stanza → render_channel_guides), so a plan for Instagram and a
plan for a blog are planned to different rules without a prompt per channel;
the Accounts tab shows the same lines beside each channel so the person sees
what the agent was told.

Numbers are the platforms' own where they publish one (caption and title
limits, slide and length caps) and the state of the published guidance where
they do not (hashtag counts, ranking signals), checked on CHECKED. A trend is
a two-week thing and lives in the research pass; a rule here changes a few
times a year, which is why it is a table and not a search.

A project's own words about a channel (its handle, bio, notes, the media it
wants there) ride beside the guide: agents/content/channel_config.py.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from agents.content.channels import Platform

CHECKED = "2026-11"

# The kinds of media a post can be, as the person picks them per channel and
# as a plan day's post_type names them. "article" is the long-form text a blog
# takes; everything else is a social post.
MEDIA_KINDS: tuple[str, ...] = ("video", "slideshow", "image", "text", "article")


@dataclass(frozen=True)
class PlatformGuide:
    platform: str
    formats: tuple[str, ...]          # what to make, with the sizes that matter
    limits: tuple[str, ...]           # what a post has to fit, or it does not publish
    wins: tuple[str, ...]             # what the feed rewards, in order
    avoid: tuple[str, ...]            # what it punishes or quietly drops
    cadence: str                      # a sustainable posting rhythm
    media: tuple[str, ...] = field(default=("video", "slideshow", "image", "text"))


GUIDES: dict[str, PlatformGuide] = {
    Platform.TIKTOK: PlatformGuide(
        platform=Platform.TIKTOK,
        formats=(
            "Video 9:16, 15 s to 10 min uploads; 21 to 60 s finishes most often",
            "Photo carousel (photo mode), up to 35 photos, with a sound",
            "On-screen text for the sound-off viewer",
        ),
        limits=("Caption 4,000 characters; the first 50 carry the search weight", "3 to 5 hashtags", "Links in the caption are not clickable"),
        wins=(
            "Completion and rewatches first, then shares and saves",
            "A hook in the first second and a payoff that makes the loop",
            "Captions written as the search phrase a viewer would type; creators can set a video's search keywords",
            "A trending sound only when it fits the post",
        ),
        avoid=("Watermarked reposts from other apps", "Twenty hashtags", "Undisclosed AI-made footage: it is labelled and viewers can turn it down"),
        cadence="Daily if the quality holds, three to five a week at least",
        media=("video", "slideshow", "image"),
    ),
    Platform.INSTAGRAM: PlatformGuide(
        platform=Platform.INSTAGRAM,
        formats=(
            "Reels 9:16 up to 3 min; 15 to 90 s is the working range",
            "Carousel 4:5, up to 20 slides; slide 2 is shown to people who scrolled past slide 1",
            "Single image 4:5; Stories 9:16 for the daily touch",
        ),
        limits=("Caption 2,200 characters, folded after about 125", "At most 5 hashtags", "No clickable link in a caption: bio or sticker"),
        wins=(
            "Sends per reach, then watch time and saves",
            "Carousels with a sound also surface in Reels",
            "Keywords in the caption and on-screen text: Instagram search reads them",
            "Alt text on every image",
        ),
        avoid=("Undisclosed AI-generated content: reach drops", "Hashtags as the first line", "Engagement bait"),
        cadence="Three to five posts a week, a Story most days",
        media=("video", "slideshow", "image"),
    ),
    Platform.YOUTUBE: PlatformGuide(
        platform=Platform.YOUTUBE,
        formats=(
            "Shorts 9:16 up to 3 min; 15 to 50 s is the sweet spot",
            "Long-form 16:9 with chapters when the topic needs more than a minute",
        ),
        limits=(
            "Title 100 characters, about 60 visible",
            "Description 5,000 characters; the first three hashtags show above the title",
            "More than 60 hashtags and none count",
        ),
        wins=(
            "Shorts: viewed vs swiped away, then rewatches and a loop that ends where it began",
            "Long-form: click-through and retention; the title carries the keyword",
            "Captions on, because many Shorts play muted",
        ),
        avoid=(
            "Mass-produced or repetitive uploads: YouTube calls it inauthentic content and demonetises it",
            "Realistic altered or synthetic footage without the AI disclosure",
            "A Short that restates a long video's title and nothing else",
        ),
        cadence="Two or three Shorts a week; one long-form a week or fortnight",
        media=("video",),
    ),
    Platform.FACEBOOK: PlatformGuide(
        platform=Platform.FACEBOOK,
        formats=(
            "Reels (every video posts as one); keep it under 90 s",
            "Photo and carousel posts",
            "Text posts that ask something; link posts sparingly",
        ),
        limits=("63,206 characters; about three lines show before 'See more'", "Hashtags optional, at most 2 or 3"),
        wins=(
            "Watch time and shares, then comments worth reading",
            "Native video over links to video",
            "A question in the first line",
        ),
        avoid=("A link in the post body: reach is cut, so it goes in the first comment", "Engagement bait ('tag a friend who…')", "Posting more than once a day"),
        cadence="Three to five posts a week",
        media=("video", "slideshow", "image", "text"),
    ),
    Platform.TWITTER: PlatformGuide(
        platform=Platform.TWITTER,
        formats=(
            "A post of 280 characters (Premium can write longer, but the feed shows the first lines)",
            "A thread: a hook post and five to eight that pay it off",
            "Native video up to 2 min 20 s on a free account; images 16:9 or 4:5",
        ),
        limits=("280 characters per post, every link counts as 23", "0 or 1 hashtag"),
        wins=(
            "Replies weigh far more than likes, so write the post that gets answered",
            "Native media and text; an outbound link belongs in the first reply",
            "The first line is the whole post for most readers",
        ),
        avoid=("A link in the post itself: reach drops hard on a free account", "Hashtag strings", "Reposting the LinkedIn version unchanged"),
        cadence="One to three a day, replies included",
        media=("text", "image", "video"),
    ),
    Platform.LINKEDIN: PlatformGuide(
        platform=Platform.LINKEDIN,
        formats=(
            "Text post; the first 210 characters are what shows before 'see more'",
            "Document carousel (a PDF of 8 to 12 pages) for a how-to",
            "Vertical video of 1 to 2 min; polls; a newsletter for the long form",
        ),
        limits=("3,000 characters", "0 to 3 hashtags", "No outbound link in the post body"),
        wins=(
            "Comments and dwell time, especially in the first hour",
            "A specific story or a number in the first two lines",
            "Replying to every comment the same day",
        ),
        avoid=("Template-shaped AI prose: it is down-ranked", "A link in the post: put it in a comment", "Tagging people who will not reply"),
        cadence="Three to five posts a week, weekday mornings",
        media=("text", "slideshow", "image", "video"),
    ),
    Platform.BLOG: PlatformGuide(
        platform=Platform.BLOG,
        formats=(
            "An article of 800 to 1,500 words, as long as the answer needs and no longer",
            "One H1, an H2 per question the reader has, 40 to 60 words of direct answer under each",
            "A short FAQ at the end, and a figure or table where a comparison is made",
        ),
        limits=(
            "Title under 60 characters with the keyword in it",
            "Meta description 120 to 155 characters",
            "One topic per article; a second topic is a second article",
        ),
        wins=(
            "The answer in the first paragraph: search and AI answers both quote it",
            "Named sources, dates and numbers, which is what gets cited",
            "Internal links to the two posts a reader would want next",
            "An author, a date, and an update when the facts change",
        ),
        avoid=("Thin generated prose padded to a word count", "Keyword-stuffed headings", "Publishing without a canonical URL"),
        cadence="One or two a week, and a refresh of an old post a month",
        media=("article",),
    ),
    Platform.WORDPRESS: PlatformGuide(
        platform=Platform.WORDPRESS,
        formats=(
            "An article of 800 to 1,500 words in blocks: heading, paragraph, list, image, table",
            "One H1 (the title), an H2 per question, 40 to 60 words of answer under each",
            "A featured image at 1200 by 675 with alt text",
        ),
        limits=(
            "Title under 60 characters; slug three to five words",
            "Excerpt and meta description 120 to 155 characters",
            "One category, three to five tags",
        ),
        wins=(
            "The answer in the first paragraph; FAQ and Article schema from the SEO plugin",
            "Internal links to related posts and a clear next step",
            "Scheduled publishing at a steady hour",
        ),
        avoid=("Thin generated prose", "Uncategorised posts and empty alt text", "A second H1 inside the body"),
        cadence="One or two a week",
        media=("article",),
    ),
}


def guide_for(platform: str | None) -> PlatformGuide | None:
    return GUIDES.get(str(platform or "").strip().lower())


def guide_payload(platform: str) -> dict | None:
    """The guide as the app shows it beside a channel; None for one without."""
    g = guide_for(platform)
    if g is None:
        return None
    return {**asdict(g), "checked": CHECKED}


def _profile_lines(profile: dict | None) -> list[str]:
    """What the project said about its own presence on the channel."""
    if not profile:
        return []
    out: list[str] = []
    handle = str(profile.get("username") or "").strip()
    name = str(profile.get("display_name") or "").strip()
    if handle or name:
        out.append(f"  account: {'@' + handle.lstrip('@') if handle else ''}{' ' + name if name else ''}".rstrip())
    if bio := str(profile.get("bio") or "").strip():
        out.append(f"  bio: {bio}")
    if notes := str(profile.get("notes") or "").strip():
        out.append(f"  notes from the person: {notes}")
    media = profile.get("target_media")
    if isinstance(media, list) and media:
        out.append(f"  post only: {', '.join(str(m) for m in media)}")
    return out


def render_channel_guides(channels: list[str], profiles: dict[str, dict] | None = None) -> str:
    """The ``<channel_guides>`` block for the opening turn: one entry per
    channel the project posts on, the guide first and the project's own words
    about its account there under it. Empty when no channel has a guide."""
    entries: list[str] = []
    for cid in channels or []:
        g = guide_for(cid)
        if g is None:
            continue
        from agents.content.channels import rules_for
        label = rules_for(cid).label
        lines = [f"- {label} ({cid})"]
        lines.append("  make: " + "; ".join(g.formats))
        lines.append("  fit: " + "; ".join(g.limits))
        lines.append("  wins: " + "; ".join(g.wins))
        lines.append("  avoid: " + "; ".join(g.avoid))
        lines.append(f"  cadence: {g.cadence}")
        lines += _profile_lines((profiles or {}).get(cid))
        entries.append("\n".join(lines))
    if not entries:
        return ""
    return (
        f"<channel_guides checked=\"{CHECKED}\">\n"
        "What each channel this brand posts on takes and rewards. Plan and write\n"
        "to these; a day on two channels fits the stricter one. 'post only' is the\n"
        "person's own limit on what goes to that channel.\n"
        + "\n".join(entries)
        + "\n</channel_guides>"
    )
