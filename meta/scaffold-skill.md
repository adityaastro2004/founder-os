# Meta-Prompt — Scaffold a Skill (Level 1)

> **Level 1 — Skills:** crystallize a prompt you keep retyping into a reusable file
> that auto-triggers on keywords. Stop retyping.
>
> Paste the block below into a Claude Code session in this repo, filling the `<…>`.

---

```
You are extending the Founder OS development system. Create a new SKILL.

Skill name: <kebab-case-name, e.g. "perf-profile">
What it does (the repeated task): <describe the prompt you keep retyping>
When it should trigger (keywords/situations): <e.g. "slow endpoint", "profile", "latency">

Follow these rules:
1. Read CLAUDE.md, skills/ (for the existing format), and standards/ first.
2. Create the canonical doc skills/<name>.md with exactly these sections:
   - Goal (one line)
   - Process (numbered, concrete, tuned to THIS stack — FastAPI/Next.js/Postgres/Redis/Clerk)
   - Never (hard constraints)
   - Output (what the skill produces)
3. Create the native adapter .claude/skills/<name>/SKILL.md with YAML frontmatter:
   ---
   name: <name>
   description: <trigger-rich one-liner so Claude Code auto-invokes it — include the keywords>
   ---
   plus a 3–5 line inline summary of the process and the line:
   "Full process: skills/<name>.md."
4. Add the skill to the CLAUDE.md §8 index (skills/ line).
5. Keep it specific to this codebase; reuse existing patterns, don't invent new ones.

Show me the two files and the CLAUDE.md edit, then stop.
```

---

## Notes

- The **canonical** content lives in `skills/<name>.md`; the `.claude/skills/` file
  is a thin auto-trigger adapter that points back to it (single source of truth).
- A good `description:` is what makes auto-trigger work — pack it with the words a
  user would actually say.
- Existing skills to copy the shape from: [debug](../skills/debug.md),
  [refactor](../skills/refactor.md), [analyze](../skills/analyze.md),
  [security_audit](../skills/security_audit.md), [optimize](../skills/optimize.md).
