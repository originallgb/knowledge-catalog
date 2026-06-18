# Open Knowledge Format — Agentic/Personal Profile

**Version 1.0 — Addendum to OKF v0.1**

This document is an addendum to [OKF v0.1](SPEC.md). It defines the
**Agentic/Personal Profile** — a set of conventions layered on top of
v0.1 to support personal and multi-harness agentic knowledge management.

A v1 bundle is **byte-compatible** with v0.1: any consumer that
correctly implements v0.1 (§9 conformance) MUST parse a v1 bundle
without modification. Everything introduced here is either a new
optional frontmatter key, a new recommended `type` value, or a
structural convention that does not alter reserved filenames (§3.1) or
required fields (§4.1).

---

## AP-1. Bundle Manifest — Version Declaration

OKF v0.1 §11 permits `okf_version` in the bundle-root `index.md`
frontmatter (the only place frontmatter is allowed in an index file).
A v1 bundle MUST declare:

```yaml
---
okf_version: "1.0"
---
```

in its bundle-root `index.md`. Additional profile-level metadata MAY
appear alongside it:

```yaml
---
okf_version: "1.0"
title: Agentic Ops — iClarity Dev
description: Shared baseline for agentic work across the iclarity-dev workspace.
tags: [agentic-ops, baseline]
timestamp: 2026-06-18T00:00:00Z
---
```

Consumers that do not understand `okf_version: "1.0"` SHOULD attempt
best-effort consumption rather than refusing the bundle (v0.1 §11).

---

## AP-2. Recommended `type` Vocabulary

OKF v0.1 §4.1 requires a `type` field on every concept document and
explicitly leaves the value space open. v1 establishes a **recommended**
vocabulary for agentic/personal use. Consumers MUST NOT reject documents
whose `type` is absent from this list (v0.1 §9).

| Type value   | Meaning                                                     | Grounded in agentic-ops                                      |
|--------------|-------------------------------------------------------------|--------------------------------------------------------------|
| `Adapter`    | Tool-specific operating notes that map shared policy to a single execution surface. | `adapters/codex-primary.md`, `adapters/gemini-cli.md`, `adapters/antigravity-gemini-primary.md` |
| `Schema`     | A structured field definition or data contract.             | `CONTEXT_LOG_SCHEMA.md`                                      |
| `Contract`   | Team-level guardrails, escalation rules, and operating agreements. | `TEAM_CONTRACT.md`                                      |
| `Runbook`    | Step-by-step operational procedure for a human or agent to execute. | `ONBOARDING_RUNBOOK.md`                             |
| `Playbook`   | Higher-level strategy or decision guide, less prescriptive than a Runbook. | `SUBAGENT_MODE.md` (framing for when/how to delegate) |
| `Reference`  | A grounded comparison, matrix, or factual lookup document.  | `TOOL_CAPABILITY_MATRIX.md`                                  |
| `Plan`       | A structured forward-looking task breakdown or roadmap.     | (conventional — not yet materialized in agentic-ops as of v1 draft) |
| `Log`        | A chronological record of decisions, research, or events.   | `RESEARCH_LOG.md`, `STATUS_UPDATE_2026-03-29.md`             |

**Notes:**

- `Plan` is included as a forward-looking type. It was not directly
  observed in a dedicated file in the agentic-ops repo at the time of
  writing but is a natural complement to the other types. This is a
  judgment call; producers MAY omit it from their own vocabulary if
  it does not fit their practice.
- Type names are title-case single words by convention in this profile.
  Multi-word types (e.g. `BigQuery Table` from v0.1 §4.1) remain valid
  in mixed-domain bundles.

---

## AP-3. Optional Frontmatter Keys for the Agentic Profile

These keys extend the base frontmatter schema (§4.1). All are OPTIONAL.
Consumers SHOULD preserve them when round-tripping (per v0.1 §4.1
extension rules).

| Key       | Type   | Meaning                                                                 |
|-----------|--------|-------------------------------------------------------------------------|
| `source`  | string | Origin path or URI of the document (e.g. git repo path, upstream URL). |
| `tool`    | string | Primary tool this document targets (e.g. `codex`, `gemini-cli`, `antigravity`, `claude-code`). |
| `model`   | string | Model name or family relevant to this document (e.g. `gpt-5.4`, `gemini-2.5-pro`). |
| `harness` | string | The harness or agent framework in scope (e.g. `openai-codex`, `gemini-cli`, `claude-code`). |
| `status`  | string | Lifecycle state of the concept. RECOMMENDED values: `draft`, `active`, `deprecated`. |

Example concept using agentic profile keys:

```yaml
---
type: Adapter
title: Codex-Primary Adapter
description: Operating notes for running Codex as coordinator across iclarity-dev repos.
tool: codex
harness: openai-codex
status: active
tags: [codex, adapter, agentic-ops]
timestamp: 2026-06-18T00:00:00Z
---
```

---

## AP-4. The Adapter Pattern — Thin Tool Entrypoints

### Motivation

Agentic tools (Claude Code, Codex, Gemini CLI, Antigravity, Cursor, etc.)
each require an entrypoint file (`CLAUDE.md`, `AGENTS.md`, `GEMINI.md`,
`.cursorrules`, etc.) to bootstrap context. Without discipline, teams
maintain duplicate, diverging context in each of these files.

The Adapter Pattern resolves this by making every tool entrypoint a
**thin adapter** — a minimal file whose only job is to point the tool
at the canonical `.okf/` bundle for that repository.

### The canonical bundle location

Each repository that participates in the v1 profile SHOULD maintain its
agentic knowledge bundle at:

```
<repo-root>/.okf/
```

This directory is a standard OKF bundle (§3). Its root `index.md` MUST
declare `okf_version: "1.0"` (AP-1).

### Generated and ephemeral state

Agentic tools generate runtime state (session logs, browser-state
directories, temp files, evidence outputs). This state MUST live in:

```
<repo-root>/.agentic/
```

`.agentic/` MUST be listed in `.gitignore`. It is never part of the
OKF bundle. This separation keeps the tracked `.okf/` bundle stable and
human-readable while isolating volatile runtime artifacts.

### Thin adapter format

A tool entrypoint SHOULD contain only:

1. A one-line statement of the tool's operating mode.
2. A pointer to the canonical `.okf/` bundle.
3. An instruction to read the bundle's root `index.md` first.

Thin adapters MUST NOT duplicate context that lives in the `.okf/`
bundle. If a piece of knowledge belongs in the bundle, it goes there.

**Example — `CLAUDE.md` (Claude Code adapter):**

```markdown
# Claude Code Adapter

This repo uses the OKF Agentic/Personal Profile (v1).

Read `.okf/index.md` first. All repo context, operating policy,
and task-specific guidance lives in `.okf/`. Do not rely on this
file for anything beyond this pointer.

Generated runtime state is in `.agentic/` (git-ignored).
```

**Example — `AGENTS.md` (Codex/OpenAI adapter):**

```markdown
# Codex Adapter

This repo uses the OKF Agentic/Personal Profile (v1).

Read `.okf/index.md` first. Shared baseline, context-log schema,
and subagent policy are documented there. Operating mode: Codex-primary.

Generated runtime state is in `.agentic/` (git-ignored).
```

Producers MAY add one or two lines of repo-specific notes if the tool
requires them (e.g. sandbox flags, MCP allowlists), but SHOULD keep
adapters under ten lines.

---

## AP-5. Conformance (v1)

A bundle is **conformant with OKF v1** if and only if:

1. It is conformant with OKF v0.1 (§9 of the base spec).
2. Its bundle-root `index.md` frontmatter declares `okf_version: "1.0"`.

All other conventions in this addendum (type vocabulary, optional
frontmatter keys, the Adapter Pattern) are RECOMMENDED. A bundle that
meets conditions 1 and 2 is a valid v1 bundle even if it uses none of
the recommended vocabulary or structural conventions.

Consumers of v1 bundles:

- MUST tolerate unknown `type` values (v0.1 §9).
- MUST tolerate unknown frontmatter keys including all AP-3 keys (v0.1 §4.1).
- MUST NOT require the `.okf/` layout, thin adapters, or `.agentic/`
  separation — these are producer-side conventions.
- SHOULD surface `okf_version` to users or downstream tooling when
  present.

---

## Appendix AP-A — Minimal `.okf/` Bundle Example

### Directory layout

```
<repo-root>/
├── .okf/
│   ├── index.md                  # Bundle root — carries okf_version
│   ├── adapters/
│   │   └── claude-code.md        # type: Adapter
│   ├── contracts/
│   │   └── team.md               # type: Contract
│   └── runbooks/
│       └── onboarding.md         # type: Runbook
├── .agentic/                     # git-ignored runtime state
│   ├── logs/
│   └── tmp/
├── CLAUDE.md                     # Thin adapter — points to .okf/
└── AGENTS.md                     # Thin adapter — points to .okf/
```

### `.okf/index.md`

```markdown
---
okf_version: "1.0"
title: my-repo — Agentic Bundle
description: OKF v1 knowledge bundle for my-repo.
status: active
timestamp: 2026-06-18T00:00:00Z
---

# Agentic Bundle — my-repo

* [Adapters](adapters/) - tool-specific operating notes
* [Contracts](contracts/) - team guardrails and agreements
* [Runbooks](runbooks/) - step-by-step operational procedures
```

### `.okf/adapters/claude-code.md`

```markdown
---
type: Adapter
title: Claude Code Adapter
description: Operating notes for Claude Code on this repo.
tool: claude-code
harness: claude-code
status: active
tags: [adapter, claude-code]
timestamp: 2026-06-18T00:00:00Z
---

- Use Claude Code as coordinator and sole writer for this repo.
- Route read-heavy exploration to subagents; keep writes on the main thread.
- Ephemeral state goes in `.agentic/` — never commit it.
- Log every task with the fields defined in [context-log schema](/contracts/context-log-schema.md).
```

### `CLAUDE.md` (thin adapter at repo root)

```markdown
# Claude Code Adapter

This repo uses the OKF Agentic/Personal Profile (v1).

Read `.okf/index.md` first. All repo context, operating policy,
and task-specific guidance lives in `.okf/`. Do not rely on this
file for anything beyond this pointer.

Generated runtime state is in `.agentic/` (git-ignored).
```
