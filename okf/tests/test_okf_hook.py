from __future__ import annotations

from pathlib import Path

from okf_hook.cli import cmd_init, cmd_install_hook, cmd_scan, cmd_update
from okf_hook.core import (
    _HOOK_BEGIN,
    _HOOK_END,
    OKF_VERSION,
    Document,
    classify_adapter,
    install_git_hook,
    regenerate_root_index,
    scan_repo,
)


class _Args:
    def __init__(self, **kw):
        self.__dict__.update(kw)


# --------------------------------------------------------------------------- #
# init
# --------------------------------------------------------------------------- #


def test_init_creates_conformant_v1_bundle(tmp_path: Path):
    repo = tmp_path / "my-repo"
    repo.mkdir()

    rc = cmd_init(_Args(repo=str(repo), title=None))
    assert rc == 0

    index = repo / ".okf" / "index.md"
    assert index.exists()
    doc = Document.parse(index.read_text(encoding="utf-8"))
    # AP-1 / AP-5: manifest declares okf_version "1.0".
    assert doc.frontmatter["okf_version"] == OKF_VERSION
    assert "my-repo" in str(doc.frontmatter["title"])

    # Starter adapter concept doc with required `type` (SPEC §4.1).
    starter = repo / ".okf" / "adapters" / "claude-code.md"
    assert starter.exists()
    sdoc = Document.parse(starter.read_text(encoding="utf-8"))
    assert sdoc.frontmatter["type"] == "Adapter"

    # Thin tool entrypoints created.
    assert (repo / "CLAUDE.md").exists()
    assert (repo / "AGENTS.md").exists()

    # .agentic/ is git-ignored (AP-4).
    gi = (repo / ".gitignore").read_text(encoding="utf-8")
    assert ".agentic/" in gi

    # Root index body lists the starter adapter under its type heading.
    body = doc.body  # stale; re-read after regenerate is part of init
    index_text = index.read_text(encoding="utf-8")
    assert "## Adapter" in index_text
    assert "claude-code.md" in index_text

    # The scan classifies it as conformant v1.
    status = scan_repo(repo)
    assert status.conformant_v1
    assert status.is_v1


def test_init_is_idempotent(tmp_path: Path):
    repo = tmp_path / "repo2"
    repo.mkdir()
    cmd_init(_Args(repo=str(repo), title=None))

    # Capture state after first run.
    snapshot = {
        p: p.read_text(encoding="utf-8")
        for p in repo.rglob("*")
        if p.is_file()
    }

    # Second run must not change any file content.
    rc = cmd_init(_Args(repo=str(repo), title=None))
    assert rc == 0

    after = {
        p: p.read_text(encoding="utf-8")
        for p in repo.rglob("*")
        if p.is_file()
    }
    assert snapshot == after


def test_init_does_not_overwrite_existing_okf(tmp_path: Path):
    repo = tmp_path / "repo3"
    okf = repo / ".okf"
    okf.mkdir(parents=True)
    custom = (
        "---\n"
        'okf_version: "1.0"\n'
        "title: Hand authored\n"
        "---\n\n"
        "# Hand authored\n\nKeep me.\n"
    )
    (okf / "index.md").write_text(custom, encoding="utf-8")

    cmd_init(_Args(repo=str(repo), title=None))

    text = (okf / "index.md").read_text(encoding="utf-8")
    assert "Hand authored" in text  # manifest frontmatter preserved


# --------------------------------------------------------------------------- #
# scan
# --------------------------------------------------------------------------- #


def test_scan_classifies_thin_fat_and_missing(tmp_path: Path):
    # Repo A: thin adapter + v1 bundle.
    a = tmp_path / "thin-repo"
    a.mkdir()
    cmd_init(_Args(repo=str(a), title=None))
    sa = scan_repo(a)
    claude_a = next(x for x in sa.adapters if x.name == "CLAUDE.md")
    assert claude_a.present and claude_a.thin
    assert sa.conformant_v1

    # Repo B: fat adapter, no bundle.
    b = tmp_path / "fat-repo"
    b.mkdir()
    fat = "# Project context\n\n" + "\n".join(
        f"- rule {i}: a long line of duplicated operating context" for i in range(40)
    )
    (b / "CLAUDE.md").write_text(fat, encoding="utf-8")
    sb = scan_repo(b)
    claude_b = next(x for x in sb.adapters if x.name == "CLAUDE.md")
    assert claude_b.present and not claude_b.thin
    assert not sb.has_bundle
    assert not sb.conformant_v1

    # Repo C: nothing at all.
    c = tmp_path / "bare-repo"
    c.mkdir()
    sc = scan_repo(c)
    assert not sc.has_bundle
    claude_c = next(x for x in sc.adapters if x.name == "CLAUDE.md")
    assert not claude_c.present


def test_classify_adapter_short_pointer_is_thin(tmp_path: Path):
    p = tmp_path / "CLAUDE.md"
    p.write_text("# Adapter\n\nRead `.okf/index.md` first.\n", encoding="utf-8")
    assert classify_adapter(p).thin


def test_scan_command_exits_zero(tmp_path: Path):
    assert cmd_scan(_Args(path=str(tmp_path))) == 0


# --------------------------------------------------------------------------- #
# update
# --------------------------------------------------------------------------- #


def test_update_refreshes_index_without_touching_concepts(tmp_path: Path):
    repo = tmp_path / "repo4"
    repo.mkdir()
    cmd_init(_Args(repo=str(repo), title=None))

    okf = repo / ".okf"
    # Author a new concept doc by hand.
    runbook = okf / "runbooks" / "onboarding.md"
    runbook.parent.mkdir(parents=True, exist_ok=True)
    runbook_text = (
        "---\n"
        "type: Runbook\n"
        "title: Onboarding\n"
        "description: How to get started.\n"
        "---\n\n"
        "# Onboarding\n\nHuman-authored body that must not change.\n"
    )
    runbook.write_text(runbook_text, encoding="utf-8")

    rc = cmd_update(_Args(repo=str(repo)))
    assert rc == 0

    # Concept body untouched.
    assert runbook.read_text(encoding="utf-8") == runbook_text

    # Root index now lists the new runbook under its type.
    index_text = (okf / "index.md").read_text(encoding="utf-8")
    assert "## Runbook" in index_text
    assert "Onboarding" in index_text
    assert "runbooks/onboarding.md" in index_text

    # Manifest still declares v1.
    doc = Document.parse(index_text)
    assert doc.frontmatter["okf_version"] == OKF_VERSION


def test_update_without_bundle_errors(tmp_path: Path):
    repo = tmp_path / "no-bundle"
    repo.mkdir()
    assert cmd_update(_Args(repo=str(repo))) == 1


def test_regenerate_root_index_preserves_extra_frontmatter(tmp_path: Path):
    okf = tmp_path / "repo5" / ".okf"
    okf.mkdir(parents=True)
    (okf / "index.md").write_text(
        "---\n"
        'okf_version: "1.0"\n'
        "title: Custom Title\n"
        "tags: [keep, these]\n"
        "---\n\n"
        "# old body\n",
        encoding="utf-8",
    )
    regenerate_root_index(okf)
    doc = Document.parse((okf / "index.md").read_text(encoding="utf-8"))
    assert doc.frontmatter["title"] == "Custom Title"
    assert doc.frontmatter["tags"] == ["keep", "these"]
    assert doc.frontmatter["okf_version"] == OKF_VERSION


# --------------------------------------------------------------------------- #
# install-hook
# --------------------------------------------------------------------------- #


def _fake_git_repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    (path / ".git" / "hooks").mkdir(parents=True, exist_ok=True)
    return path


def test_install_hook_creates_executable_hooks(tmp_path: Path):
    repo = _fake_git_repo(tmp_path / "repo")
    results = install_git_hook(repo, events=("post-merge", "post-checkout"))
    assert {e for e, _ in results} == {"post-merge", "post-checkout"}

    for event in ("post-merge", "post-checkout"):
        hook = repo / ".git" / "hooks" / event
        assert hook.exists()
        text = hook.read_text(encoding="utf-8")
        assert text.startswith("#!/bin/sh")
        assert _HOOK_BEGIN in text and _HOOK_END in text
        assert "okf-hook update" in text
        # Executable bit set.
        assert hook.stat().st_mode & 0o111


def test_install_hook_is_idempotent(tmp_path: Path):
    repo = _fake_git_repo(tmp_path / "repo")
    install_git_hook(repo, events=("post-merge",))
    first = (repo / ".git" / "hooks" / "post-merge").read_text(encoding="utf-8")

    install_git_hook(repo, events=("post-merge",))
    second = (repo / ".git" / "hooks" / "post-merge").read_text(encoding="utf-8")

    # Re-running refreshes in place — exactly one managed block, no duplication.
    assert second.count(_HOOK_BEGIN) == 1
    assert second.count(_HOOK_END) == 1
    assert first.count(_HOOK_BEGIN) == 1


def test_install_hook_preserves_foreign_hook_content(tmp_path: Path):
    repo = _fake_git_repo(tmp_path / "repo")
    hook = repo / ".git" / "hooks" / "post-merge"
    hook.write_text("#!/bin/sh\necho existing-tooling\n", encoding="utf-8")

    install_git_hook(repo, events=("post-merge",))
    text = hook.read_text(encoding="utf-8")
    # Pre-existing content kept; our block appended.
    assert "echo existing-tooling" in text
    assert _HOOK_BEGIN in text


def test_install_hook_bakes_okf_src_fallback(tmp_path: Path):
    repo = _fake_git_repo(tmp_path / "repo")
    src = tmp_path / "some" / "src"
    install_git_hook(repo, events=("post-commit",), okf_src=src)
    text = (repo / ".git" / "hooks" / "post-commit").read_text(encoding="utf-8")
    assert str(src.resolve()) in text
    assert "python3 -m okf_hook update" in text


def test_install_hook_rejects_non_git_dir(tmp_path: Path):
    plain = tmp_path / "not-a-repo"
    plain.mkdir()
    try:
        install_git_hook(plain)
        raised = False
    except NotADirectoryError:
        raised = True
    assert raised


def test_cmd_install_hook_unsupported_event_is_skipped(tmp_path: Path):
    repo = _fake_git_repo(tmp_path / "repo")
    rc = cmd_install_hook(
        _Args(repo=str(repo), events="post-merge,bogus-event", okf_src=None, force=False)
    )
    assert rc == 0
    assert (repo / ".git" / "hooks" / "post-merge").exists()
    assert not (repo / ".git" / "hooks" / "bogus-event").exists()
