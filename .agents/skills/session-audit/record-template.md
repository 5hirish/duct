# Session audit: <agent> <short id>

**Author:** <who ran the skill, harness and model> · **Date:** YYYY-MM-DD ·
**Session:** `<conversation id>` · **Project:** <anonymised> ·
**Repo at audit:** `<sha>` · **Prompt check:** <matches | changed | unknown> ·
**Rubric:** v1.1 · **Blind:** yes | no (why)

## Request

- Asked: …
- Meant: …
- A great answer needs: (checklist, written before either answer was read)
- Data available: (tool files by name and window; duplicates, failures, gaps)

## Independent attempt

See `attempt.md`. Harness/model, time spent, what was missing.

## Side by side

Before any score. A reader must be able to see the gap, then read the
grades as its explanation.

**Chat reply**, both in full:

> Duct: …

> Attempt: …

**Brief, first screen** (the title through the first table or first
finding, whichever comes first), both verbatim:

> Duct: …

> Attempt: …

**Counted evidence** (numbers, not opinions; the replay is a third column
when one was run):

| Measure | Duct | Attempt | Replay |
|---|---:|---:|---:|
| Words | | | |
| Table rows | | | |
| Figures cited (numbers, %, money; dates excluded) | | | |
| Totals or a revenue line present | | | |
| Findings argued from the data | | | |
| Actions, and how many carry an expected effect | | | |
| "Could not check" bullets, and how many are template | | | |
| Audit-speak the person should never see (tool file names, memory ids, verifier wording) | | | |

## Grades

| Dimension | Duct | Attempt | Evidence |
|---|---|---|---|
| Run · Tool choice | | | |
| Run · Data reach | | | |
| Run · Turn economy | | | |
| Run · Questions | | | |
| Run · Failure handling | | | |
| Run · Cost and time | | | |
| Reply · Resolution | | | |
| Reply · Accuracy | | | |
| Reply · Reasoning | | | |
| Reply · Intelligence | | | |
| Reply · Style | | | |
| Reply · Honesty | | | |
| Artifact · Structure | | | |
| Artifact · Information | | | |
| Artifact · Accuracy | | | |
| Artifact · Analytical thinking | | | |
| Artifact · Critical thinking | | | |
| Artifact · Comprehension | | | |
| Artifact · Actionability | | | |
| Artifact · Style | | | |

Memories written: … · Change sets: …

## Comparison and diagnosis

| Dimension | Gap | Cause class | Points at | Note |
|---|---|---|---|---|

What Duct did better, and why it must be kept: …

## Proposals

### P-<short id>-1 · <class> · <one line>

- Evidence: `[seq]`, anonymised.
- Change: (prompt wording verbatim, or the code change)
- Expected effect: <dimension> from N to M.
- Verify by: re-audit a fresh <agent> session after it ships.
- Status: proposed | filed #N | made in this session

## Ledger rows added

(copy of the rows appended to `ledger.md`)
