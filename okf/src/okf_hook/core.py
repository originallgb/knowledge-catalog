"""Core logic for the OKF v1 first-run/update hook.

Three operations, all safely re-runnable:

* ``scan``   — read-only status report for a repo or a directory of repos.
* ``init``   — create a conformant v1 ``.okf/`` bundle if absent (never clobbers).
* ``update`` — re-sync derived bits (root index, manifest, .gitignore).

This module is standalone: stdlib + PyYAML only. It deliberately does not
import ``enrichment_agent`` so the hook can ship and install independently.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

OKF_VERSION = "1.0"

_FRONTMATTER_DELIM = "---"
_INDEX_FILE = "index.md"
_RESERVED = {"index.md", "log.md"}

# Tool entrypoint files recognised by the Adapter Pattern (AP-4).
TOOL_ENTRYPOINTS = ("CLAUDE.md", "AGENTS.md", "GEMINI.md", ".cursorrules")

# A thin adapter points at .okf/ and stays short. We classify a tool
# entrypoint as "thin" if it references the .okf bundle and is small.
_THIN_MARKER = ".okf"
_THIN_MAX_LINES = 12


# --------------------------------------------------------------------------- #
# Minimal frontmatter document (mirrors enrichment_agent.bundle.document)
# --------------------------------------------------------------------------- #


@dataclass
class Document:
    frontmatter: dict[str, Any] = field(default_factory=dict)
    body: str = ""

    @classmethod
    def parse(cls, text: str) -> "Document":
        lines = text.splitlines()
        if not lines or lines[0].strip() != _FRONTMATTER_DELIM:
            return cls(frontmatter={}, body=text)
        end_idx = None
        for i in range(1, len(lines)):
            if lines[i].strip() == _FRONTMATTER_DELIM:
                end_idx = i
                break
        if end_idx is None:
            # Tolerant: treat the whole thing as body rather than raising.
            return cls(frontmatter={}, body=text)
        fm_text = "\n".join(lines[1:end_idx])
        try:
            fm = yaml.safe_load(fm_text) or {}
        except yaml.YAMLError:
            fm = {}
        if not isinstance(fm, dict):
            fm = {}
        body = "\n".join(lines[end_idx + 1:])
        if body.startswith("\n"):
            body = body[1:]
        return cls(frontmatter=fm, body=body)

    def serialize(self) -> str:
        fm_text = yaml.safe_dump(
            self.frontmatter, sort_keys=False, allow_unicode=True
        ).rstrip()
        body = self.body if self.body.endswith("\n") else self.body + "\n"
        return f"{_FRONTMATTER_DELIM}\n{fm_text}\n{_FRONTMATTER_DELIM}\n\n{body}"


def _load_doc(path: Path) -> Document | None:
    try:
        return Document.parse(path.read_text(encoding="utf-8"))
    except OSError:
        return None


def _title_from_dirname(name: str) -> str:
    return f"{name} — Agentic Bundle"


# --------------------------------------------------------------------------- #
# Status model
# --------------------------------------------------------------------------- #


@dataclass
class AdapterStatus:
    name: str
    present: bool = False
    thin: bool = False  # only meaningful when present


@dataclass
class RepoStatus:
    path: Path
    has_bundle: bool = False
    has_manifest: bool = False  # root .okf/index.md exists
    okf_version: str | None = None
    is_v1: bool = False  # manifest declares okf_version "1.0"
    agentic_ignored: bool = False
    adapters: list[AdapterStatus] = field(default_factory=list)

    @property
    def conformant_v1(self) -> bool:
        return self.has_bundle and self.is_v1


def classify_adapter(path: Path) -> AdapterStatus:
    name = path.name
    if not path.exists():
        return AdapterStatus(name=name, present=False)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return AdapterStatus(name=name, present=True, thin=False)
    nonblank = [ln for ln in text.splitlines() if ln.strip()]
    thin = (_THIN_MARKER in text) and (len(nonblank) <= _THIN_MAX_LINES)
    return AdapterStatus(name=name, present=True, thin=thin)


def _gitignore_has_agentic(repo: Path) -> bool:
    gi = repo / ".gitignore"
    if not gi.exists():
        return False
    try:
        lines = gi.read_text(encoding="utf-8").splitlines()
    except OSError:
        return False
    for raw in lines:
        entry = raw.strip().rstrip("/")
        if entry in (".agentic", "/.agentic"):
            return True
    return False


def scan_repo(repo: Path) -> RepoStatus:
    """Read-only inspection of a single repo."""
    repo = Path(repo)
    status = RepoStatus(path=repo)

    okf_dir = repo / ".okf"
    status.has_bundle = okf_dir.is_dir()

    manifest = okf_dir / _INDEX_FILE
    if manifest.is_file():
        status.has_manifest = True
        doc = _load_doc(manifest)
        if doc is not None:
            ver = doc.frontmatter.get("okf_version")
            if ver is not None:
                status.okf_version = str(ver)
                status.is_v1 = str(ver) == OKF_VERSION

    status.agentic_ignored = _gitignore_has_agentic(repo)
    status.adapters = [classify_adapter(repo / name) for name in TOOL_ENTRYPOINTS]
    return status


def _looks_like_repo(path: Path) -> bool:
    """A directory is treated as a repo target if it is a git repo, already
    has a bundle, or has any tool entrypoint."""
    if (path / ".git").exists():
        return True
    if (path / ".okf").is_dir():
        return True
    return any((path / name).exists() for name in TOOL_ENTRYPOINTS)


def discover_repos(root: Path) -> list[Path]:
    """If ``root`` itself looks like a repo, return ``[root]``; otherwise
    return its immediate child directories that look like repos. Falls back
    to ``[root]`` so ``scan`` always reports something."""
    root = Path(root)
    if _looks_like_repo(root):
        return [root]
    children = [c for c in sorted(root.iterdir()) if c.is_dir()] if root.is_dir() else []
    repos = [c for c in children if _looks_like_repo(c)]
    return repos or [root]


# --------------------------------------------------------------------------- #
# .gitignore management
# --------------------------------------------------------------------------- #


def ensure_agentic_ignored(repo: Path) -> bool:
    """Ensure ``.agentic/`` is git-ignored. Returns True if a change was made."""
    if _gitignore_has_agentic(repo):
        return False
    gi = repo / ".gitignore"
    block = "# OKF v1 — generated agentic runtime state (AP-4)\n.agentic/\n"
    if gi.exists():
        existing = gi.read_text(encoding="utf-8")
        sep = "" if existing.endswith("\n") or not existing else "\n"
        gi.write_text(existing + sep + block, encoding="utf-8")
    else:
        gi.write_text(block, encoding="utf-8")
    return True


# --------------------------------------------------------------------------- #
# Bundle index regeneration (root index per SPEC §6)
# --------------------------------------------------------------------------- #


def _concept_entries(okf_dir: Path) -> list[tuple[str, str, str, str]]:
    """Collect (type, title, relative-link, description) for every concept
    doc in the bundle, links relative to the bundle root."""
    entries: list[tuple[str, str, str, str]] = []
    for md in sorted(okf_dir.rglob("*.md")):
        if md.name in _RESERVED:
            continue
        doc = _load_doc(md)
        if doc is None:
            continue
        fm = doc.frontmatter
        title = str(fm.get("title") or md.stem)
        desc = str(fm.get("description") or "")
        typ = str(fm.get("type") or "")
        link = md.relative_to(okf_dir).as_posix()
        entries.append((typ, title, link, desc))
    return entries


def _render_index_body(title: str, entries: list[tuple[str, str, str, str]]) -> str:
    grouped: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
    for typ, ttl, link, desc in entries:
        grouped[typ or "Other"].append((ttl, link, desc))

    parts = [f"# {title}", ""]
    if not entries:
        parts.append("_No concept documents yet. Add docs under `.okf/`._")
        return "\n".join(parts) + "\n"
    for typ in sorted(grouped):
        parts.append(f"## {typ}")
        parts.append("")
        for ttl, link, desc in sorted(grouped[typ], key=lambda e: e[0].lower()):
            suffix = f" - {desc}" if desc else ""
            parts.append(f"* [{ttl}]({link}){suffix}")
        parts.append("")
    return "\n".join(parts).rstrip() + "\n"


def build_manifest_doc(repo_name: str, title: str | None = None) -> Document:
    return Document(
        frontmatter={
            "okf_version": OKF_VERSION,
            "title": title or _title_from_dirname(repo_name),
            "description": f"OKF v1 knowledge bundle for {repo_name}.",
            "status": "active",
        },
        body="",  # body filled in by regenerate_root_index
    )


def regenerate_root_index(okf_dir: Path) -> None:
    """Rewrite ``.okf/index.md`` preserving its manifest frontmatter while
    refreshing the body listing of concept docs. Creates a manifest if none
    exists. Never touches concept doc bodies."""
    okf_dir = Path(okf_dir)
    index_path = okf_dir / _INDEX_FILE
    repo_name = okf_dir.parent.name

    if index_path.is_file():
        doc = _load_doc(index_path) or Document()
    else:
        doc = build_manifest_doc(repo_name)

    fm = doc.frontmatter
    # Ensure the v1 manifest is present (AP-1) without discarding extra keys.
    fm.setdefault("okf_version", OKF_VERSION)
    fm.setdefault("title", _title_from_dirname(repo_name))
    fm.setdefault("description", f"OKF v1 knowledge bundle for {repo_name}.")

    title = str(fm.get("title"))
    entries = _concept_entries(okf_dir)
    doc.body = _render_index_body(title, entries)
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text(doc.serialize(), encoding="utf-8")


# --------------------------------------------------------------------------- #
# Starter content for init
# --------------------------------------------------------------------------- #


def _starter_adapter_doc(repo_name: str) -> str:
    doc = Document(
        frontmatter={
            "type": "Adapter",
            "title": "Claude Code Adapter",
            "description": f"Operating notes for Claude Code on {repo_name}.",
            "tool": "claude-code",
            "harness": "claude-code",
            "status": "active",
            "tags": ["adapter", "claude-code"],
        },
        body=(
            "- Use the canonical `.okf/` bundle as the single source of repo context.\n"
            "- Keep this and every tool entrypoint a thin adapter (see AP-4).\n"
            "- Ephemeral runtime state goes in `.agentic/` — never commit it.\n"
        ),
    )
    return doc.serialize()


def _thin_adapter_text(tool_label: str, mode_line: str) -> str:
    return (
        f"# {tool_label}\n"
        "\n"
        "This repo uses the OKF Agentic/Personal Profile (v1).\n"
        "\n"
        f"Read `.okf/index.md` first. {mode_line} All repo context, operating\n"
        "policy, and task-specific guidance lives in `.okf/`. Do not rely on\n"
        "this file for anything beyond this pointer.\n"
        "\n"
        "Generated runtime state is in `.agentic/` (git-ignored).\n"
    )


# Default thin adapters created on init. Keyed by entrypoint filename.
_INIT_ADAPTERS = {
    "CLAUDE.md": ("Claude Code Adapter", "Operating mode: Claude-Code-primary."),
    "AGENTS.md": ("Codex Adapter", "Operating mode: Codex-primary."),
}


# --------------------------------------------------------------------------- #
# Git hook installation (trigger wiring)
# --------------------------------------------------------------------------- #

# Git events whose natural meaning is "bundle may now be stale, re-sync it".
HOOK_EVENTS = ("post-commit", "post-merge", "post-checkout", "post-rewrite")
DEFAULT_HOOK_EVENTS = ("post-merge", "post-checkout")

_HOOK_BEGIN = "# >>> okf-hook managed (do not edit between markers) >>>"
_HOOK_END = "# <<< okf-hook managed <<<"


def default_okf_src() -> Path:
    """Absolute path to this package's ``src`` directory, used as the
    python-module fallback when ``okf-hook`` is not on PATH."""
    return Path(__file__).resolve().parents[1]


def _hook_block(repo_toplevel_cmd: str, okf_src: Path) -> str:
    """The managed snippet inserted into a git hook. Prefers an ``okf-hook``
    on PATH; otherwise falls back to invoking the module from ``okf_src``.
    Always exits 0 so a sync failure never blocks git operations."""
    return (
        f"{_HOOK_BEGIN}\n"
        "# Auto-syncs the OKF v1 .okf/ bundle. Installed by `okf-hook install-hook`.\n"
        f'_okf_repo="{repo_toplevel_cmd}"\n'
        '[ -n "$_okf_repo" ] || exit 0\n'
        'if command -v okf-hook >/dev/null 2>&1; then\n'
        '  okf-hook update "$_okf_repo" >/dev/null 2>&1 || true\n'
        "else\n"
        f'  PYTHONPATH="{okf_src}" python3 -m okf_hook update "$_okf_repo" '
        ">/dev/null 2>&1 || true\n"
        "fi\n"
        f"{_HOOK_END}\n"
    )


def _strip_managed_block(text: str) -> str:
    """Remove any previously-installed okf-hook managed block from a hook."""
    if _HOOK_BEGIN not in text:
        return text
    out_lines: list[str] = []
    skipping = False
    for line in text.splitlines():
        if line.strip() == _HOOK_BEGIN:
            skipping = True
            continue
        if line.strip() == _HOOK_END:
            skipping = False
            continue
        if not skipping:
            out_lines.append(line)
    return "\n".join(out_lines)


def install_git_hook(
    repo: Path,
    events: tuple[str, ...] = DEFAULT_HOOK_EVENTS,
    okf_src: Path | None = None,
    force: bool = False,
) -> list[tuple[str, str]]:
    """Install (or refresh) the okf-hook trigger into a repo's git hooks.

    Idempotent: re-running replaces the managed block in place and preserves
    any other hook content. Returns a list of (event, action) results.
    Raises ``NotADirectoryError`` if ``repo`` is not a git working tree.
    """
    repo = Path(repo).expanduser().resolve()
    git_dir = repo / ".git"
    # Support worktrees / submodules where .git is a file pointing elsewhere.
    if git_dir.is_file():
        pointer = git_dir.read_text(encoding="utf-8").strip()
        if pointer.startswith("gitdir:"):
            git_dir = (repo / pointer.split(":", 1)[1].strip()).resolve()
    if not git_dir.is_dir():
        raise NotADirectoryError(f"{repo} is not a git repository (.git not found)")

    hooks_dir = git_dir / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    okf_src = (okf_src or default_okf_src()).resolve()
    block = _hook_block('$(git rev-parse --show-toplevel 2>/dev/null)', okf_src)

    results: list[tuple[str, str]] = []
    for event in events:
        if event not in HOOK_EVENTS:
            results.append((event, "skipped (unsupported event)"))
            continue
        hook_path = hooks_dir / event
        if hook_path.exists():
            existing = hook_path.read_text(encoding="utf-8")
            if _HOOK_BEGIN in existing:
                if not force:
                    # Refresh the managed block in place (keeps it current).
                    new_text = _strip_managed_block(existing).rstrip() + "\n\n" + block
                    hook_path.write_text(new_text, encoding="utf-8")
                    results.append((event, "refreshed"))
                else:
                    new_text = _strip_managed_block(existing).rstrip() + "\n\n" + block
                    hook_path.write_text(new_text, encoding="utf-8")
                    results.append((event, "reinstalled (--force)"))
            else:
                # Foreign hook present — append our block, preserve theirs.
                sep = "" if existing.endswith("\n") else "\n"
                hook_path.write_text(existing + sep + "\n" + block, encoding="utf-8")
                results.append((event, "appended to existing hook"))
        else:
            hook_path.write_text("#!/bin/sh\n" + block, encoding="utf-8")
            results.append((event, "created"))
        hook_path.chmod(0o755)
    return results
