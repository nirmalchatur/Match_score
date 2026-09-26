# Skill Gap Analysis

## What it is, and what it deliberately is not

A **projection** of the match result `MatchEngine` already computed. Not a
second matching system, and not a model call.

The existing pipeline is:

```
ResumeProfile (catalog-extracted skills)
        +
JDProfile     (catalog-extracted skills)
        |
   MatchEngine.calculate()      <- already exists, already deterministic
        |
   job.match_result             <- stored on the job
        |
   analyze_skill_gap()          <- this module: reads it, adds wording
```

There is no second extractor, no second vocabulary, and no AI involvement. The
same `skill_catalog` and `SkillNormalizer` that produce the match score produce
the gap, so the two can never disagree. A test asserts the projection is
faithful to the engine's own output.

## The two sub-results, and not mixing them

`MatchEngine.calculate()` returns several blocks and they mean different things:

| Block | Contents | Used for |
|---|---|---|
| `skills.matched` | Normalized catalog vocabulary | **Matched** list |
| `skills.missing` | Normalized catalog vocabulary | **Missing** list |
| `requirements.matched` | Raw JD requirement *lines* | — |
| `requirements.partially_matched` | Raw JD requirement lines | **Partial** list |
| `requirements.unmatched` | Raw JD requirement lines | — |

Mixing these up is the easy mistake: `requirements.unmatched` contains strings
like `"- Kubernetes"`, not `"kubernetes"`. Requirements are not skills, and the
UI should not present them in a skills list. The partial list comes from the
requirement pass because that is the only place the engine records partial
credit.

## Wording

The one thing this module adds is language, and it matters:

> **Not found in current resume** — *not* "you don't know Kubernetes".

A missing skill is an absence of evidence in the uploaded document. It is not
evidence of an absence of ability. A test asserts the forbidden phrasings never
appear.

## Empty states

An unanalysed job is a **different state** from "matched nothing":

```json
{ "has_analysis": false, "summary": "No job analysis available." }
```

Collapsing the two would tell a user they match no requirements when in fact
nothing was ever computed. A test pins this.

## API

`skill_gap` is a read-only field on `JobSerializer`, so it arrives with the job
in the existing `GET /api/jobs/<id>/` and list responses. No extra request, and
no new endpoint to keep in sync.
