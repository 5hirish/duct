"""How an opening stops a reader and how a post keeps them, on every channel.

The two stanzas every writer and the reviewer share: the carousel draft, the
write phase, the text-post writer and review_post. One copy, so the writer
and the judge hold the post to the same bar, and so a TikTok carousel and a
LinkedIn post open on the same principles, each at its own channel's fold
(platform_guides.PlatformGuide.opening says where that is).

Why it exists (2026-11-27): drafts opened on topic labels and trailing
teasers ("Before you choose a bob or layers…") and scored 36 on hook and 34
on momentum, while the persona panel picked the opening that said the
viewer's own doubt in her words. The old guidance was an emotion template
for TikTok carousels alone, and its examples were the vague kind of teaser
the headline research below finds loses.

Evidence, so the rules are not re-litigated from taste:
- Le Quéré & Matias, Scientific Reports 2025 ("When curiosity gaps
  backfire"): across 8,977 headline A/B tests, more concrete headlines win
  when the baseline is vague, and lose once a headline answers itself. The
  best opening is specific about the situation and holds back the answer.
- Robertson et al., Nature Human Behaviour 2023: in 105,000 Upworthy
  headline tests (370M impressions), each negative word raised clicks and
  positive words lowered them. A real cost or mistake out-pulls good news;
  an invented one is bait.
- Golman & Loewenstein: curiosity is strongest for a question just opened
  and salient. Hence one question per opening, and each unit of the post
  opening the next.
- Platforms (Instagram's ranking notes, YouTube's "viewed vs swiped away",
  LinkedIn and X folds): every feed decides on the first second or line, and
  rewards the post people finish, send and answer.
"""

from __future__ import annotations

# The mechanisms double as `hook_type` values, so the plan's hook stats grade
# them against what the posts earned.
OPENING_MECHANISMS: tuple[tuple[str, str], ...] = (
    ("their_question", "the reader's own doubt, as they would say it: \"Not sure a blunt bob suits hair that kinks when it dries?\""),
    ("counter_intuitive_number", "a figure that contradicts what they assume, then the so-what"),
    ("mistake", "the thing they are doing that costs them: \"Stop asking for 'face-framing'. Ask for this.\""),
    ("result_first", "the after, shown or stated, with how it happened held back"),
    ("contrarian_claim", "what most people default to, and why it is wrong now, with the stakes"),
    ("story_moment", "one scene at its tense instant: \"The stylist held up two photos and asked which one I meant.\""),
    ("self_test", "a check they can run on themselves: \"If your fringe splits by noon, the cut is fighting your crown.\""),
)

OPENING_CRAFT = """\
OPENINGS — the first slide, first second, first line. Most people see
nothing else, so it has one job: make the next second worth it.

An opening that stops someone passes all six:
1. Their question, in their words. It names the reader's situation or doubt
   the way they would say it, not the post's topic. "Not sure whether a blunt
   bob or face-framing layers suit your usual hair?" stops the person
   deciding; "Before you choose a bob or layers…" only announces a subject.
2. Concrete, not complete. Name the specific thing: a number, an object, a
   person, a moment, a place. Hold back the answer. Vague teasers lose ("this
   changed everything", "you won't believe what it said", "it knew things I
   didn't"), and so does an opening that answers itself.
3. A tension: a cost, a mistake, a contradiction, a surprise. A real problem
   pulls harder than good news. Never invent one the post cannot stand on.
4. No warm-up. Cut "So", "Here's", "Let's talk about", "Before you", a
   greeting, a topic label, the brand name, a trailing ellipsis.
5. Read at a glance: at most 12 words on a slide or a video's on-screen text;
   a text post's first line stands alone before the fold.
6. Paid off. The body delivers exactly what the opening promised, and early
   enough. An opening the post does not pay loses the viewer on the first
   slide that does not, and teaches the feed to show it less.

Before keeping one, ask: would a named persona say "that's me" or "that's my
question"? Could it head any other brand's post? (Then it is too generic.)
Does it answer itself? (Then hold the answer back.)

Mechanisms. Pick the one the post is, and record it as `hook_type`. When
you write several openings, use a different mechanism for each, so the
check compares angles, not rewordings:
""" + "\n".join(f"- {key}: {desc}" for key, desc in OPENING_MECHANISMS) + "\n"

MOMENTUM_CRAFT = """\
MOMENTUM: each slide, video beat, paragraph or thread part has one job,
which is to make the next one necessary.
- Promise early. Within the first two units, say what they will get and
  where: the three things, the test, the before and after. A reader with a
  destination keeps going.
- But and therefore, never "and also". Each unit complicates the last
  ("but") or follows from it ("therefore"). Parallel tips are where people
  leave.
- End every unit unresolved. Its last line raises the question the next one
  answers. The exit test: if a reader could stop after this unit satisfied,
  rewrite its last line.
- Re-hook in the middle. By the middle (slide 3 or 4, second 8 to 10, the
  fourth paragraph) put in a new tension or a reveal; that is where finishing
  drops off.
- Pay concretely, before the close. The payoff is the thing worth a
  screenshot: a test, a number, an exact phrase. It is not a summary. It
  comes before the call to action, never after it.
- Cut any unit nobody would miss. A short post that is full beats a long one
  that is padded. No counters ("2/7"), no recap.
"""

__all__ = ["MOMENTUM_CRAFT", "OPENING_CRAFT", "OPENING_MECHANISMS"]
