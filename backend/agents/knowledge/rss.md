# RSS and Atom feeds

What a project published, from the feeds it reads: a blog, a Substack, a
changelog page, a YouTube channel's uploads, a public repository's
`releases.atom`. One connector row holds every feed URL; one binding carries
them all.

## Reading it

- **Published is the feed's own date, and feeds disagree about it.** RSS has
  `pubDate`, Atom has `published` and `updated`; Duct takes published, then
  updated. An entry edited last week and first published last year reads as
  last year's.
- **A feed shows its newest entries only**, often 10 or 20. A window further
  back than the feed reaches comes back short, not empty because nothing
  happened. Say so before concluding a quiet month.
- **The summary is the feed's, clipped to a few lines.** It is not the article,
  and some feeds put the whole post in it while others put a sentence. Quote the
  title and link, never the summary as if it were the piece.
- **A YouTube feed is uploads, not views.** It says a video went out; it says
  nothing about how it did.
- **One failing feed does not fail the read.** It is named in `errors`, and the
  others come back.
