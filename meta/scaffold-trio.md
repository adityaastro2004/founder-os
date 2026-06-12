# Meta-Prompt — Scaffold a Sub-Agent Trio (Level 2)

> **Level 2 — Sub-agents:** split one task into a Planner / Executor / QA trio with
> strict handoff contracts. Stop being the QA.
>
> The repo already ships the general five-agent chain (planner → architect →
> builder → reviewer → tester). Use this when a **specific recurring task type**
> deserves its own purpose-built trio (e.g. "add a new API endpoint", "add a new
> product agent", "write a migration"). Paste the block below, filling the `<…>`.

---

```
You are extending the Founder OS development system. Create a SUB-AGENT TRIO for a
recurring task type.

Task type: <e.g. "add a new approval-gated tool to the agent system">
Why a dedicated trio: <what's special/repeated about this task>

Produce THREE engineering agents — Planner, Executor, QA — specialized for this task:

For each, create:
A) Canonical doc agents/<tasktype>-<role>.md with sections:
   Role · Inputs · Outputs · Process · Never · Success criteria
   — all concrete to THIS stack and this task type, reusing existing patterns.
B) Native adapter .claude/agents/eng-<tasktype>-<role>.md with frontmatter:
   ---
   name: eng-<tasktype>-<role>
   description: <when to invoke this agent>
   tools: <minimal set — QA/reviewer read-biased; executor gets edit tools>
   model: inherit
   ---
   body: short role summary + "Read agents/<tasktype>-<role>.md and CLAUDE.md, then
   execute your stage; honor the Never list."

Define the HANDOFF CONTRACT explicitly (what each role consumes and produces, and
the artifact they pass — default to a tasks/ file). The QA role must:
- verify against acceptance criteria with shown output,
- never mark unverified work done,
- enforce the security model (auth, approval gate, secrets).

Also create workflows/<tasktype>.md wiring the three with gates between them, and
add it to the CLAUDE.md §8 index.

Show me all files, then stop.
```

---

## Notes

- Keep the trio **minimal and contract-driven**: each role has one job and a clear
  input/output. The whole point is that you stop hand-holding the handoffs.
- Prefix native agents with `eng-` to keep them distinct from product runtime
  agents (see [CLAUDE.md §2](../CLAUDE.md)).
- Reuse the general agents ([planner](../agents/planner.md) …
  [qa](../agents/qa.md)) as the template for tone and structure.
- Next level up: wire the trio to a trigger with [scaffold-orchestration](scaffold-orchestration.md).
