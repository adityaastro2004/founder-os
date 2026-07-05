# 014 — Vault-read hardening before any hosted/multi-tenant deployment

- **Status:** backlog (from Phase 1 eng-security audit S1, 2026-07-06)
- **Priority:** hard prerequisite for Phase 5 (deployment) if hosting is shared;
  not a blocker for local-first single-user operation (in-trust-boundary).

## Finding (eng-security S1)

`validate_vault_path` (`app/integrations/obsidian/client.py`) is denylist-only
(rejects `/`, home, the repo tree) — `/etc`, `/var`, any process-readable dir
pass. `walk_vault` follows symlinks on READ: a `link.md → /outside/secret.md`
inside a vault gets ingested into state + RAG and is readable back through the
API. Rendered files can be written into any writable dir's `FounderOS/`.
Single-tenant: the founder owns the filesystem — acceptable. Hosted: LFI +
arbitrary-write across tenants.

## Acceptance criteria

1. `vault_path` confined to a configured allowlist base directory
   (e.g. `STATE_VAULT_BASE_DIRS` setting; empty = current local-first behavior,
   documented as single-tenant only).
2. Inbound read path resolves symlinks and rejects files escaping the vault
   root (mirror of the write jail), with unit tests (symlinked file + dir).
3. The single-tenant trust assumption documented next to `validate_vault_path`
   until 1–2 land.
4. eng-security re-audit of the read path.

## Also carried from the same audit (nits, fix opportunistically)

- N3: `%`/`_` LIKE wildcards in entity title search (own-rows only, cosmetic).
