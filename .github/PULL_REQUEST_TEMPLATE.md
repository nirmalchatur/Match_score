<!--
Thanks for the PR. Keep it to one concern; a second fix is a second PR.
See CONTRIBUTING.md and docs/ADDING_A_FEATURE.md if this is your first one.
-->

## What and why

<!-- What does this change, and what problem does it solve? Link the issue. -->

Closes #

## How it was tested

<!-- The tests you added or changed, and anything you checked by hand. -->

- [ ] `make check` passes locally (ruff, Django checks + tests, oxlint, Vitest, build)
- [ ] Added or updated tests for the behaviour this changes
- [ ] Ran `npm run test:e2e` (if routes, guards, or signed-out pages changed)

## Checklist

- [ ] Migrations are included for any model change
- [ ] New queries are scoped to `request.user` (another account's id → 404)
- [ ] No secrets, keys, or personal data in code, fixtures, or logs
- [ ] Docs updated (`docs/API.md`, `.env.example`, an ADR) where relevant
- [ ] No test or security check was weakened to get this to pass, or, if one
      was changed, the reason is explained above

## Screenshots / user-visible change

<!-- For UI changes, before/after screenshots. Delete this section otherwise. -->
