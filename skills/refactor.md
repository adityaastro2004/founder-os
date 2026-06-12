# Skill — Refactor

> Reusable capability. Trigger when restructuring/cleaning code **without changing
> behavior**. Native auto-trigger: `.claude/skills/refactor/`.

## Goal

Improve structure, clarity, or reuse while keeping behavior identical and the
verification green at every step.

## Process

1. **Characterize current behavior** — make sure a test or repeatable manual check
   exists *before* you touch anything ([standards/testing.md](../standards/testing.md)).
   If none exists, add a thin one first.
2. **Define the target** — name the specific smell (duplication, long function,
   leaky abstraction, vendor coupling) and the end shape. Keep scope tight.
3. **Small safe steps** — one behavior-preserving change at a time
   (extract function, rename, dedupe, inline). Re-run the check after each step.
4. **Reuse the codebase's patterns** — consolidate toward existing utilities/hooks
   (`ToolRegistry`, `llm.py`, `lib/` hooks, ORM models), don't invent new abstractions.
5. **Verify equivalence** — same inputs → same outputs; the check stays green.
   Keep the diff minimal and on-topic.

## Never

- Never change behavior and structure in the same step.
- Never refactor without a safety net (test or recorded manual check).
- Never expand scope into unrelated files or reformat untouched code.
- Never break the security model or provider neutrality while "cleaning up".

## Output

What was changed and why, confirmation the behavior check still passes, and a note
on any follow-up the refactor revealed (as a new [tasks/](../tasks/) item if real).
