# okf-hook

Installable first-run / update hook that brings any repo under the OKF v1
Agentic/Personal Profile (see `../../SPEC-v1.md`). Standalone: stdlib + PyYAML.

## Install

Installed with the package via its console entry point:

```bash
pip install -e .        # from the okf/ project root
okf-hook --help
```

Or run without installing:

```bash
PYTHONPATH=src python -m okf_hook --help
```

## Commands

```bash
okf-hook scan <path>          # read-only status table (repo or dir of repos); always exits 0
okf-hook init <repo>          # create a conformant v1 .okf/ bundle if absent (idempotent)
okf-hook update <repo>        # re-sync root index + manifest + .gitignore (idempotent)
okf-hook install-hook <repo>  # wire `update` into the repo's git hooks (idempotent)
```

`init` creates `<repo>/.okf/index.md` (manifest with `okf_version "1.0"`), a
starter `.okf/adapters/claude-code.md`, thin `CLAUDE.md`/`AGENTS.md` adapters,
and ensures `.agentic/` is git-ignored. It never overwrites existing `.okf`
content. `update` refreshes the derived root index listing without touching
human-authored concept bodies.

## Triggering on git events

`install-hook` wires `update` into a repo's git hooks so the bundle's root
index stays in sync automatically. It is idempotent — it manages a marked
block and re-running refreshes that block in place, preserving any other
hook content.

```bash
okf-hook install-hook <repo>                          # post-merge + post-checkout (default)
okf-hook install-hook <repo> --events post-commit     # pick events
okf-hook install-hook <repo> --okf-src /path/to/okf/src   # bake fallback path
```

Supported events: `post-commit`, `post-merge`, `post-checkout`,
`post-rewrite`. The installed hook prefers an `okf-hook` on `PATH` and falls
back to `python3 -m okf_hook` using `--okf-src` (defaults to this package's
`src`). It always exits 0, so a sync failure never blocks a git operation.
Hooks live under `.git/hooks/` and are not tracked by git.

Default events (`post-merge`/`post-checkout`) re-sync after you pull or switch
branches without dirtying the tree on every commit. Use `post-commit` if you
want the index refreshed as you author concept docs locally.
