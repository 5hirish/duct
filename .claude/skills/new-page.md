---
name: new-page
description: Create a new audience-specific landing page following the for-*.html pattern
argument-hint: "<audience-slug> \"<title suffix>\" \"<hero headline>\" \"<hero subtext>\""
---

Creates a new `for-<audience-slug>.html` variant page for a specific audience segment.
Keeps the existing Duct design, CSS, and HTML structure — only copy and audience-specific content change.

## Usage

```
/new-page <audience-slug> "<title suffix>" "<hero headline>" "<hero subtext>"
```

Example:
```
/new-page for-engineering-teams "for Engineering Teams" "Stop losing signal in the noise." "Duct connects Jira, Linear, Sentry, and Datadog into a weekly engineering brief."
```

---

## Before writing: answer these three questions

Do not start writing until you can answer all three. The answers drive every copy decision.

1. **What job does this audience hire Duct to do?** Name the outcome, not the feature. "Stop spending Monday mornings pulling data from five tools" — not "cross-tool data aggregation."
2. **What is the specific, concrete pain?** Describe the situation. "Search Console shows impressions up. GA4 says signups are flat. You don't know which to trust." — not "data silos."
3. **What exact tools do they live in?** Name them. Naming the audience's actual tools in the subheadline is often the single highest-impact copy decision on the page.

---

## Page narrative (keep this sequence)

The page is a single argument. Each section earns the next. Do not reorder.

```
Hero           → Clear claim: this is for you, here's what you get
Tool strip     → Signal: these are tools you already use
Problem        → You understand their exact pain (specific, not generic)
How it works   → The mechanism in 3 sequential steps
Features       → Proof points for the mechanism
Audience       → Name exactly who fits — and who doesn't (with inline CTA)
Stats          → Quantify the proof
Final CTA      → One decision
```

No testimonials section — this is an MVP/early-stage product. The `.quotes` section in the base template should be removed from new pages.

---

## Step 1 — Copy the base template

Copy `for-product-intelligence.html` → `for-<audience-slug>.html` at the repo root.
Remove the entire `<!-- TESTIMONIALS -->` section (`.quotes`) from the copy.

---

## Step 2 — `<head>` metadata

- `<title>` → `Duct <title-suffix> — <7-word value descriptor>`
- Canonical URL → `https://getduct.ai/for-<audience-slug>`
- `og:url` → same as canonical
- `og:title` / `twitter:title` → match `<title>`
- `og:description` (120–140 chars) → answers "what does this help me do?" for this audience; must not be the headline verbatim
- `twitter:description` (120–140 chars) → shorter variant; must differ from `og:description`
- JSON-LD `description` → one-sentence JTBD framing for the audience

---

## Step 3 — Nav subtitle

The small label next to the logo. Change it to the audience label, e.g. `for engineering teams`.

---

## Step 4 — Hero section (highest leverage — spend most time here)

The 8-second test: a stranger should immediately understand "this is for me and here's what I get." Every word that doesn't advance that goal is dead weight.

### Urgency pill

Keep the scarcity signal: `Early access · N spots remaining`

### Headline

**Spec:** 5–10 words, ≤60 characters. Outcome-led, not feature-led.

**Avoid:** powerful, seamless, robust, end-to-end, all-in-one, transformative. These words carry zero signal.

**The best-performing pattern from the existing pages:**
> `Stop [specific painful thing].<br/>Start <em>[desirable outcome].</em>`

Examples from live pages:
- "Stop tab-switching. Start *knowing.*"
- "Stop publishing blind. Start *compounding.*"

Both follow the same structure: name what they're trapped in → name what they want instead. The `<em>` tag goes on the aspirational word, not the pain word.

Other proven patterns:
- `[JTBD] that won't [bad outcome]` — "Product insights that won't take all morning"
- `[Task] shouldn't be harder than [other task]` — "Reading your data shouldn't be harder than collecting it"
- `[Desirable outcome].<br/>No <em>[painful means].</em>` — "Know what's happening. No SQL required."

**StoryBrand frame:** Your customer is the hero facing a problem. Duct is the guide. The headline names what the customer achieves — not what Duct built.

### Subheadline

1–2 sentences. Answers: *how* it works + *who* it's for. Names the audience's specific tools.

Why tool-naming works: it signals "made for me" within 3 words. "Duct connects Mixpanel, Intercom, and Linear" reads differently to a PM than "Duct connects your tools." Be that specific.

Must complement the headline — not restate it.

### CTA button

2–5 words, names the outcome not the action. Never: "Submit", "Learn more", "Sign up".
Good: `Get early access →`, `Reserve your spot →`, `Join waitlist →`

Use the same button copy at both hero and final CTA. Changing it between positions creates confusion about what the main action is.

### Trust signals

Below (not inside) the button, one line of micro-copy kills the top objection.
Format: `Free during beta · No credit card · [one more relevant trust signal]`

### Hero footnote

One line, anchors who this is for and reduces wrong-fit signups.
Format: `Free during beta · No credit card · For [role] at [company size] companies`
Both role and company size should be honest and specific to this audience.

---

## Step 5 — Tool strip

Update the `.marquee` spans with the tools this specific audience actually uses. These are the tools they should recognise from their own stack.

---

## Step 6 — Problem section (second-highest leverage)

**Job:** Make the visitor feel viscerally recognised. "This company gets me" is the conversion trigger — not information, but recognition.

**Source of copy:** Use the audience's own language. Don't paraphrase how they describe the problem — mirror it. If you know how they phrase it (from sales calls, reviews, Reddit), use those words.

### Problem headline

Names the failure mode, not the general topic. Use `<em>` on the key phrase.

**The best-performing pattern from the existing pages:**
> `You're [doing the right thing].<br/>But no one <em>[specific failure].</em>`

Examples from live pages:
- "The answer is in your tools. But no one *connected them.*"
- "You're producing content. But no one *connected it* to growth."

This pattern is powerful because it validates the audience first ("you're doing the right thing") before naming the gap. It doesn't make them feel stupid — it makes them feel let down by their tools.

### Pain bullets

3 bullets. Each is a specific scenario, not a category description.

**What makes a pain bullet work:**
- Name two conflicting signals in the same sentence: "Search Console shows impressions up. GA4 says signups are flat." — the reader feels the specific frustration of not knowing which to trust
- Show the downstream cost: "Ahrefs flagged a keyword opportunity three weeks ago. It's still sitting in a tab." — the cost isn't the tab, it's the compounding loss
- Be honest about wasted time: "You spend Monday mornings pulling rank data, session stats, and content metrics from five different tools just to decide what to work on."

Specificity is a filter — the more precisely you describe the pain, the stronger the ICP response, and wrong-fit visitors self-exit.

### Diagram (`.diag` block)

Shows the chaos-to-clarity transformation. Must use this audience's actual tool stack.

The structure: 4 disconnected tools (each showing one specific signal) → one "After Duct" sentence connecting them all into a single story.

**What makes the "After Duct" sentence work:** It's a narrative — verb-led, connecting cause to effect across all four tools in one sentence. From the live pages:
- "Retention drop → Intercom spike → bug fix timing → churn. One story, automatically connected."
- "Rising keyword → low-KD gap → missing content → conversion drop. One story, automatically connected."

The formula: `[Signal A] → [Signal B] → [Signal C] → [outcome]. One story, automatically connected.`

Keep the macOS window chrome (the three dots) and `dim` class pattern — the visual weight difference between the first tool and the faded ones reinforces the "disconnected" feeling.

---

## Step 7 — How it works

Three steps showing a sequential workflow (not a feature list). The customer experiences them in order: connect → configure → receive.

The three step titles are universal. Update `.step-body` copy when the audience has specific framing concerns:
- Engineering teams: emphasise "read-only — Duct never writes to your repos or opens tickets"
- Growth teams: emphasise what the weekly brief contains and when it arrives

---

## Step 8 — Features

Keep all four feature cards. The features are the same product — only the framing changes per audience.

Frame each feature around the outcome the audience cares about, not the mechanism. The feature label (emoji + category) stays; `feat-title` and `feat-body` change to speak to this audience's specific angle.

---

## Step 9 — Audience section

**Section headline:** Name the exact person, their responsibility, and the resource they're missing.
Pattern: `The [role] who owns [responsibility] without a [resource they lack]`

From live pages: "The PM who owns *growth* without a data team" / "The growth lead who owns *organic* without a dedicated SEO team"

**Supporting copy:** 2–3 sentences that read like you're inside their head. Describe their constraint and the outcome they want — not aspirationally, but descriptively of their actual situation.

**Inline CTA:** Keep the mid-section button `That's me — get early access →`. This is the page's highest-intent click because it comes from a section explicitly about the reader. Don't change the copy unless the action changes.

**Audience fit cards:** 4 cards total.
- Card 1 (primary ICP, `hi` class): `Perfect fit` — the exact person this page is for
- Cards 2–3: `Great fit` — adjacent roles who also benefit
- Card 4 (greyed out, `opacity:.45`, `off` badge class): `Not yet` — explicitly name who this is NOT for

The "Not yet" card is one of the highest-trust signals on the page. It says: we know our limits, we're not selling to everyone. It also improves signup quality.

---

## Step 10 — Stats bar

4 numbers. Keep the format: large number + short label. Keep the `0` stat — a zero is a punchline ("0 SQL queries required", "0 manual data exports needed") and stands out visually among non-zero stats.

Only update if this audience has different proof priorities. Keep 4 stats and the stagger animation.

---

## Step 11 — Final CTA

**Job:** One decision. Reinforce why, reduce the last hesitation. No new information.

- Headline echoes the hero's urgency signal: `Join the first <em>25 teams</em>`
- Supporting copy names the 1:1 onboarding offer — personalise it if the audience has specific needs
- Button copy: identical to the hero CTA (consistency matters)
- Trust note: mirrors the urgency signal + trust signals: `N spots remaining · No spam · Unsubscribe anytime`

---

## Step 12 — Accent colour

Every page gets a colour. It should match the emotional register of the audience's domain — the way orange reads as energy/urgency and green reads as growth/nature for the existing pages.

**Existing pages (for consistency reference):**
- `for-product-intelligence` → orange `#FF5C00` / hover `#e05000` — intensity, speed, analytical fire
- `for-organic-growth` → sage green `#2e9e6b` / hover `#228055` — growth, compounding, nature

**Pre-decided palette for common audience types — pick the best match:**

| Audience type | Colour | Hex | Hover hex | Rationale |
|---|---|---|---|---|
| Engineering / infrastructure | Indigo | `#4F46E5` | `#3730A3` | Precision, reliability, technical depth |
| Sales / revenue | Teal | `#0891B2` | `#0E7490` | Pipeline, momentum, professional energy |
| Founders / operators | Amber | `#D97706` | `#B45309` | Decisiveness, warmth, early-stage grit |
| Data / analytics | Slate blue | `#3B5BDB` | `#2F4AC5` | Structured thinking, intelligence, clarity |
| Marketing / brand | Violet | `#7C3AED` | `#6D28D9` | Creativity, differentiation, attention |
| Customer success / support | Sky | `#0284C7` | `#0369A1` | Trust, calm, reliability |
| Finance / ops | Cool grey-blue | `#475569` | `#334155` | Professionalism, precision, control |

If the audience doesn't fit any row, choose based on tone: warm colours (orange, amber) = urgency/action; cool colours (indigo, slate, teal) = precision/trust; mid colours (green, violet) = growth/creativity.

**How to add it:** Add a `<style>` block at the bottom of `<head>` — copy the pattern from `for-organic-growth.html`. Replace `--green` and `--green-h` with your chosen colour variables. The block overrides CSS variables, not individual selectors.

---

## Step 13 — Sitemap

Add to `sitemap.xml`:
```xml
<url>
  <loc>https://getduct.ai/for-<audience-slug></loc>
  <changefreq>weekly</changefreq>
  <priority>0.9</priority>
</url>
```

---

## Mobile check (do this before calling it done)

Review at 375px width. The hero must be fully legible without horizontal scroll. Check:
- Headline, subhead, and CTA button all visible above the fold — nothing cut off
- All body text is at least 16px (check duct.css doesn't have overrides for small screens)
- CTA button is large enough for a thumb tap — no crowding from adjacent elements
- No images or heavy assets added — the design uses CSS gradients, keep it that way

---

## Checklist

**Copy quality**
- [ ] Headline ≤60 chars, outcome-led, no cliché words
- [ ] Subheadline names this audience's exact tools
- [ ] Problem headline validates the audience ("you're doing the right thing") before naming the gap
- [ ] Each pain bullet names two conflicting signals or a specific downstream cost
- [ ] Diag "After Duct" follows the `[A] → [B] → [C] → [outcome]. One story, automatically connected.` formula
- [ ] "Not yet" audience card names who this is NOT for

**Conversion mechanics**
- [ ] Hero footnote names role and company size honestly
- [ ] Inline audience CTA present: `That's me — get early access →`
- [ ] Hero and final CTA use identical button copy
- [ ] Trust micro-copy below both CTAs

**Structure**
- [ ] Testimonials section removed
- [ ] Correct section order: Hero → Strip → Problem → How → Features → Audience → Stats → CTA → Footer

**Technical**
- [ ] Accent colour chosen from palette and `<style>` block added to `<head>`
- [ ] Canonical URL correct and unique
- [ ] All `og:` and `twitter:` tags written fresh (not copied from base)
- [ ] Nav subtitle updated to new audience label
- [ ] Both form buttons have `data-form-url` and `data-entry-id`
- [ ] Added to `sitemap.xml`
- [ ] No `<!-- TODO -->` or placeholder text
- [ ] Mobile check at 375px passed
