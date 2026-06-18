"""okf-hook CLI — scan / init / update for the OKF v1 Agentic/Personal Profile.

Designed to be safely re-runnable as a trigger (git hook, shell wrapper, etc.).
See AP-4 of SPEC-v1.md for the Adapter Pattern this implements.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from okf_hook.core import (
    DEFAULT_HOOK_EVENTS,
    OKF_VERSION,
    RepoStatus,
    _INIT_ADAPTERS,
    _starter_adapter_doc,
    _thin_adapter_text,
    build_manifest_doc,
    discover_repos,
    ensure_agentic_ignored,
    install_git_hook,
    regenerate_root_index,
    scan_repo,
)


def _adapter_label(a) -> str:
    if not a.present:
        return "-"
    return "thin" if a.thin else "fat"


def _print_status(status: RepoStatus) -> None:
    if status.conformant_v1:
        verdict = "OK v1"
    elif status.has_bundle:
        verdict = f"bundle (okf_version={status.okf_version or 'none'})"
    else:
        verdict = "no bundle"

    adapters = "  ".join(
        f"{a.name}={_adapter_label(a)}" for a in status.adapters
    )
    ignore = "yes" if status.agentic_ignored else "no"
    print(f"{status.path}")
    print(f"    status: {verdict}    .agentic ignored: {ignore}")
    print(f"    adapters: {adapters}")


def cmd_scan(args: argparse.Namespace) -> int:
    root = Path(args.path).expanduser()
    repos = discover_repos(root)
    print(f"OKF v1 scan — {root} ({len(repos)} repo(s))\n")
    for repo in repos:
        _print_status(scan_repo(repo))
        print()
    return 0


def cmd_init(args: argparse.Namespace) -> int:
    repo = Path(args.repo).expanduser()
    repo.mkdir(parents=True, exist_ok=True)
    okf_dir = repo / ".okf"
    created: list[str] = []
    skipped: list[str] = []

    okf_dir.mkdir(parents=True, exist_ok=True)

    # Manifest / root index.
    index_path = okf_dir / "index.md"
    if index_path.exists():
        skipped.append(".okf/index.md (exists)")
    else:
        doc = build_manifest_doc(repo.name, title=args.title)
        index_path.write_text(doc.serialize(), encoding="utf-8")
        created.append(".okf/index.md")

    # Starter adapter concept doc.
    adapters_dir = okf_dir / "adapters"
    starter = adapters_dir / "claude-code.md"
    if starter.exists():
        skipped.append(".okf/adapters/claude-code.md (exists)")
    else:
        adapters_dir.mkdir(parents=True, exist_ok=True)
        starter.write_text(_starter_adapter_doc(repo.name), encoding="utf-8")
        created.append(".okf/adapters/claude-code.md")

    # Thin tool entrypoints.
    for name, (label, mode) in _INIT_ADAPTERS.items():
        entry = repo / name
        if entry.exists():
            skipped.append(f"{name} (exists)")
        else:
            entry.write_text(_thin_adapter_text(label, mode), encoding="utf-8")
            created.append(name)

    # .gitignore for .agentic/.
    if ensure_agentic_ignored(repo):
        created.append(".gitignore (+.agentic/)")
    else:
        skipped.append(".gitignore (.agentic/ already ignored)")

    # Refresh the root index body so the manifest lists the starter doc.
    regenerate_root_index(okf_dir)

    print(f"init {repo}  (okf_version {OKF_VERSION})")
    for c in created:
        print(f"  created: {c}")
    for s in skipped:
        print(f"  skipped: {s}")
    return 0


def cmd_update(args: argparse.Namespace) -> int:
    repo = Path(args.repo).expanduser()
    okf_dir = repo / ".okf"
    if not okf_dir.is_dir():
        print(
            f"update {repo}: no .okf/ bundle found — run `okf-hook init` first.",
            file=sys.stderr,
        )
        return 1

    actions: list[str] = []
    had_manifest = (okf_dir / "index.md").exists()
    regenerate_root_index(okf_dir)
    actions.append(
        "refreshed .okf/index.md"
        if had_manifest
        else "created .okf/index.md (manifest)"
    )

    if ensure_agentic_ignored(repo):
        actions.append("added .agentic/ to .gitignore")
    else:
        actions.append(".agentic/ already ignored")

    print(f"update {repo}  (okf_version {OKF_VERSION})")
    for a in actions:
        print(f"  {a}")
    return 0


def cmd_install_hook(args: argparse.Namespace) -> int:
    repo = Path(args.repo).expanduser()
    if args.events:
        events = tuple(
            e.strip() for e in args.events.split(",") if e.strip()
        )
    else:
        events = DEFAULT_HOOK_EVENTS
    okf_src = Path(args.okf_src).expanduser() if args.okf_src else None
    try:
        results = install_git_hook(
            repo, events=events, okf_src=okf_src, force=args.force
        )
    except NotADirectoryError as exc:
        print(f"install-hook: {exc}", file=sys.stderr)
        return 1
    print(f"install-hook {repo.resolve()}")
    for event, action in results:
        print(f"  {event}: {action}")
    return 0


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="okf-hook",
        description="First-run/update hook for the OKF v1 Agentic/Personal Profile.",
    )
    sub = p.add_subparsers(dest="command", required=True)

    scan = sub.add_parser(
        "scan", help="Read-only OKF v1 status report for a repo or dir of repos."
    )
    scan.add_argument("path", help="Repo root, or a directory containing repos.")
    scan.set_defaults(func=cmd_scan)

    init = sub.add_parser(
        "init", help="Create a conformant v1 .okf/ bundle if absent (idempotent)."
    )
    init.add_argument("repo", help="Repo root to initialize.")
    init.add_argument(
        "--title", default=None, help="Bundle title (default: derived from dir name)."
    )
    init.set_defaults(func=cmd_init)

    update = sub.add_parser(
        "update", help="Re-sync derived bundle bits (idempotent)."
    )
    update.add_argument("repo", help="Repo root to update.")
    update.set_defaults(func=cmd_update)

    install = sub.add_parser(
        "install-hook",
        help="Install a git hook that runs `update` on the given events "
        "(default: post-merge,post-checkout). Idempotent.",
    )
    install.add_argument("repo", help="Git repo root to install the hook into.")
    install.add_argument(
        "--events",
        default=None,
        help="Comma-separated git events "
        "(post-commit,post-merge,post-checkout,post-rewrite). "
        "Default: post-merge,post-checkout.",
    )
    install.add_argument(
        "--okf-src",
        default=None,
        help="Path to the okf-hook src dir, baked into the hook as the "
        "fallback when `okf-hook` is not on PATH. Default: this package's src.",
    )
    install.add_argument(
        "--force",
        action="store_true",
        help="Reinstall the managed hook block even if already present.",
    )
    install.set_defaults(func=cmd_install_hook)

    return p


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
