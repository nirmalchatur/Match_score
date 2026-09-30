# ADR-002: Keep the AI provider abstraction, with the deterministic engine as the source of truth

## Context

Rooting a product on one vendor's API is a single point of failure that also
removes the ability to run locally: a developer on a laptop cannot call a hosted
model without a key, and CI must not call one at all. TailorUp already had an
`AIProvider` interface with Ollama, Gemini, Groq and a deterministic test double
behind a factory, and the brief for this phase explicitly protected it.

What had to be settled is what the AI layer is *allowed* to decide. A model is
good at rewriting a bullet; it is not the thing that should decide whether a
candidate has a skill, or what their match score is. Those are the two questions
a user is entitled to have answered consistently.

## Decision

Keep the provider abstraction exactly as it is, and keep the deterministic layer
authoritative.

```text
Request
  → application service                       (ownership, provider + key resolution)
  → ResumeTailor                              (orchestration: prompt, parse, validate)
  → factory.get_ai_provider(name)             (the only module that knows the set)
  → OllamaProvider / GeminiProvider / GroqProvider / FakeAIProvider
  → raw text
  → schemas.parse_*                           (shape: forgiving)
  → validators.validate                       (truth: strict)
  → AIRun + ActivityEvent                     (audit)
  → artifact
```

The division of responsibility, stated so it can be checked:

| Question | Owner |
| --- | --- |
| What is the match score? | `MatchEngine` (deterministic, weighted, inspectable) |
| Does the candidate have a skill? | `SkillNormalizer` + the parsed `ResumeProfile` |
| Which requirements are unmet? | `JDProfile` + `MatchEngine` |
| How should this experience be phrased? | The AI provider |
| Is the phrasing factually supported? | `validators` (deterministic, no model) |

A provider implementation must never contain TailorUp business rules: it receives
a `TailoringRequest` and returns text. `apps/ai/providers/*` may not import
`apps.jobs` or `apps.resumes` at all, and no module under `apps/ai` may read or
write `match_score`, `match_result` or `decision`. Both are asserted in
`apps/common/tests/test_architecture.py`.

## Alternatives considered

- **Let the model score the match and use it as the number.** Rejected. A score
  that moves between two runs of the same data, or between two providers, cannot
  be explained, compared or tested. It would also make the product's central
  claim -- "every number traces to evidence" -- false.
- **Two scores: deterministic and AI.** Rejected as confusing. Two numbers for
  the same question invites the user to believe the larger one, and the AI score
  has nothing better to offer.
- **Use function/tool calling or a hosted structured-output mode per provider.**
  Rejected for now. It would put provider-specific output handling into the
  orchestration path, which is exactly the coupling the abstraction exists to
  prevent. Defensive parsing plus deterministic validation covers the local
  model's real failure modes.
- **Schema validation through a third-party library (pydantic, jsonschema).**
  Rejected. The contract is small, the parsing is deliberately forgiving about
  format, and the strictness that matters (fabrication) is a *truth* check no
  schema library performs.
- **A second, "smart" model for validation.** Rejected. Validating a model with a
  model makes the verdict non-reproducible, which is the property being relied on.

## Consequences

- Adding a provider is a class plus one factory entry. No change to
  `tailor.py`, the validators, the views or the audit path.
- The AI layer can only *help*; it cannot change a score, so an AI outage leaves
  analysis, ranking, skill gap and the tracker fully functional. A tailoring is
  the only feature that degrades.
- The provider boundary is also a cost and privacy boundary: a deployment can run
  entirely locally on Ollama, and a user can bring their own key for a hosted
  provider. That choice already exists and is unchanged.
- The deterministic layer carries more of the product's weight, so it needs the
  larger share of tests. It has them, and the architecture test asserts the score
  is reproducible from stored data.
