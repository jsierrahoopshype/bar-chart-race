"""Push code changes from this repo's hf_space/ folder to the HuggingFace Space.

The Space repo (remote "hf") holds hf_space/'s *contents* at its root, so
``main:hf_space/bar_race/render.py`` corresponds to ``hf/main:bar_race/render.py``.

Text files are compared with a plain tree-vs-tree diff. Binary assets are Git
LFS pointers on the Space but raw blobs here, so they always look different to
git; they are compared by LFS oid instead, and any genuine binary change stops
the sync (that needs the LFS path, not this script).

Usage::

    python scripts/sync_bar_race_to_space.py [--dry-run]
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile

REMOTE_NAME = "hf"
REMOTE_URL = "https://huggingface.co/spaces/cdechoch/bar-chart-race"
REMOTE_BRANCH = "main"
SUBFOLDER = "hf_space"
LIVE_URL = "https://jsierrahoopshype.github.io/bar-chart-race/"

TEXT_EXTS = {
    ".py", ".md", ".txt", ".html", ".js", ".css", ".json",
    ".yaml", ".yml", ".toml", ".cfg",
}
TEXT_NAMES = {"dockerfile", "requirements.txt"}

BINARY_EXTS = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".ico", ".svg",
    ".ttf", ".otf", ".woff", ".woff2",
    ".mp4", ".mov", ".webm", ".mp3", ".wav",
    ".zip", ".gz", ".tar", ".pdf", ".xlsx", ".npy", ".pkl", ".bin",
}

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_LFS_OID_RE = re.compile(rb"^oid sha256:([0-9a-f]{64})\s*$", re.MULTILINE)


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _use_utf8_stdout() -> None:
    """Let the em dashes survive a Windows console. Harmless elsewhere."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def say(msg: str = "") -> None:
    print(msg, flush=True)


def stop(reason: str) -> None:
    """Print a final STOPPED line and exit non-zero."""
    say()
    say(f"STOPPED - {reason}")
    sys.exit(1)


def git(*args: str, cwd: str | None = None, env: dict | None = None):
    """Run git and return the CompletedProcess with *bytes* stdout."""
    full_env = None
    if env:
        full_env = os.environ.copy()
        full_env.update(env)
    return subprocess.run(
        ["git", *args],
        cwd=cwd or REPO_ROOT,
        env=full_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def git_text(*args: str, **kw) -> str:
    """Run git and return stripped stdout as text (empty string on failure)."""
    p = git(*args, **kw)
    return p.stdout.decode("utf-8", "replace").strip()


def git_or_stop(*args: str, what: str, cwd: str | None = None) -> str:
    """Run git, or stop with the command's own error text."""
    p = git(*args, cwd=cwd)
    if p.returncode != 0:
        err = (p.stderr.decode("utf-8", "replace").strip()
               or p.stdout.decode("utf-8", "replace").strip())
        say()
        say(f"  git {' '.join(args)}")
        for line in err.splitlines():
            say(f"  {line}")
        stop(what)
    return p.stdout.decode("utf-8", "replace").strip()


def classify(path: str) -> str:
    """Return 'text', 'binary', or 'other' for a repo-relative path."""
    name = os.path.basename(path).lower()
    ext = os.path.splitext(name)[1]
    if ext in TEXT_EXTS or name in TEXT_NAMES:
        return "text"
    if ext in BINARY_EXTS:
        return "binary"
    return "other"


def short(rev: str) -> str:
    return git_text("rev-parse", "--short", rev) or rev


# ---------------------------------------------------------------------------
# Steps
# ---------------------------------------------------------------------------

def ensure_remote() -> None:
    say(f"[1/6] Checking git remote '{REMOTE_NAME}'...")
    existing = git_text("remote")
    if REMOTE_NAME in existing.split():
        url = git_text("remote", "get-url", REMOTE_NAME)
        say(f"      remote '{REMOTE_NAME}' -> {url}")
        if url.rstrip("/") != REMOTE_URL.rstrip("/"):
            say(f"      NOTE: expected {REMOTE_URL}")
    else:
        git_or_stop("remote", "add", REMOTE_NAME, REMOTE_URL,
                    what=f"could not add remote '{REMOTE_NAME}'")
        say(f"      added remote '{REMOTE_NAME}' -> {REMOTE_URL}")


def sync_main() -> None:
    say("[2/6] Switching to main and pulling...")
    p = git("checkout", "main")
    if p.returncode != 0:
        err = p.stderr.decode("utf-8", "replace").strip()
        for line in err.splitlines():
            say(f"  {line}")
        stop("could not check out main (commit or stash your changes first)")
    git_or_stop("pull", "origin", "main", what="could not pull origin/main")
    say(f"      main is at {short('main')}")

    say(f"[3/6] Fetching {REMOTE_NAME}...")
    git_or_stop("fetch", REMOTE_NAME,
                what=f"could not fetch from '{REMOTE_NAME}' "
                     f"(is the Space URL right, and are you online?)")
    say(f"      {REMOTE_NAME}/{REMOTE_BRANCH} is at "
        f"{short(f'{REMOTE_NAME}/{REMOTE_BRANCH}')}")


def diff_trees() -> list[tuple[str, str]]:
    """Return [(status, path)] going from hf/main to main:hf_space."""
    out = git_or_stop(
        "diff", "--name-status", "-z",
        f"{REMOTE_NAME}/{REMOTE_BRANCH}", f"main:{SUBFOLDER}",
        what="could not diff the Space against main:" + SUBFOLDER)
    fields = [f for f in out.split("\0") if f]
    entries: list[tuple[str, str]] = []
    i = 0
    while i < len(fields):
        status = fields[i]
        # Rename/copy entries carry a source and a destination path.
        if status[:1] in ("R", "C") and i + 2 < len(fields):
            entries.append((status[:1], fields[i + 2]))
            i += 3
        elif i + 1 < len(fields):
            entries.append((status[:1], fields[i + 1]))
            i += 2
        else:
            break
    return entries


def lfs_oid(path: str) -> str | None:
    """Return the LFS oid recorded for *path* on hf/main, if it is a pointer."""
    p = git("show", f"{REMOTE_NAME}/{REMOTE_BRANCH}:{path}")
    if p.returncode != 0:
        return None
    m = _LFS_OID_RE.search(p.stdout)
    return m.group(1).decode() if m else None


def main_blob(path: str) -> bytes | None:
    """Return the raw bytes of main:hf_space/<path>."""
    p = git("show", f"main:{SUBFOLDER}/{path}")
    return p.stdout if p.returncode == 0 else None


def binary_really_changed(status: str, path: str) -> bool:
    """True if a binary asset genuinely differs from the Space's copy.

    The Space stores LFS pointers, so compare the pointer's sha256 against the
    real blob here rather than trusting the diff.
    """
    if status == "A":
        return True  # new asset, nothing on the Space to compare against
    blob = main_blob(path)
    if blob is None:
        return False
    oid = lfs_oid(path)
    if oid is None:
        # Not a pointer after all — compare the bytes directly.
        p = git("show", f"{REMOTE_NAME}/{REMOTE_BRANCH}:{path}")
        return p.returncode != 0 or p.stdout != blob
    return hashlib.sha256(blob).hexdigest() != oid


def make_worktree() -> str:
    tmp = tempfile.mkdtemp(prefix="hf_space_sync_")
    wt = os.path.join(tmp, "space")
    p = git("worktree", "add", "--detach", wt,
            f"{REMOTE_NAME}/{REMOTE_BRANCH}",
            env={"GIT_LFS_SKIP_SMUDGE": "1"})
    if p.returncode != 0:
        for line in p.stderr.decode("utf-8", "replace").strip().splitlines():
            say(f"  {line}")
        shutil.rmtree(tmp, ignore_errors=True)
        stop("could not create the temporary sync worktree")
    return wt


def drop_worktree(wt: str) -> None:
    git("worktree", "remove", "--force", wt)
    parent = os.path.dirname(wt)
    if os.path.isdir(parent):
        shutil.rmtree(parent, ignore_errors=True)
    git("worktree", "prune")


def push_hints(err: str) -> None:
    low = err.lower()
    if "not authorized" in low or "401" in low or "403" in low:
        say()
        say("  Looks like an auth problem:")
        say("    1. Create a Write token at "
            "https://huggingface.co/settings/tokens")
        say("    2. Run:  echo url=https://huggingface.co| git credential reject")
        say("    3. Run this sync again and paste the token when asked.")
    if "rate limit" in low or "429" in low:
        say()
        say("  Looks like a rate limit: wait 5 minutes, then run this again.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(argv: list[str]) -> int:
    _use_utf8_stdout()
    dry_run = "--dry-run" in argv

    say("Sync hf_space/ -> HuggingFace Space")
    say(f"  repo:  {REPO_ROOT}")
    say(f"  space: {REMOTE_URL}")
    if dry_run:
        say("  MODE:  --dry-run (nothing will be committed or pushed)")
    say()

    ensure_remote()
    sync_main()

    say(f"[4/6] Comparing the Space against main:{SUBFOLDER}...")
    entries = diff_trees()

    text_changes: list[str] = []
    binary_changes: list[str] = []
    deletions: list[str] = []
    others: list[str] = []

    for status, path in entries:
        if status == "D":
            deletions.append(path)
            continue
        kind = classify(path)
        if kind == "text":
            text_changes.append(path)
        elif kind == "binary":
            if binary_really_changed(status, path):
                binary_changes.append(path)
        else:
            others.append(path)

    text_changes.sort()
    binary_changes.sort()

    if deletions:
        say(f"      {len(deletions)} path(s) exist on the Space but not in "
            f"{SUBFOLDER}/ (left alone):")
        for p in sorted(deletions)[:10]:
            say(f"        - {p}")
        if len(deletions) > 10:
            say(f"        ... and {len(deletions) - 10} more")

    if others:
        say(f"      {len(others)} path(s) of unrecognized type, not synced:")
        for p in sorted(others)[:10]:
            say(f"        ? {p}")

    if binary_changes:
        say()
        say(f"      {len(binary_changes)} binary asset(s) really changed:")
        for p in binary_changes:
            say(f"        * {p}")
        say()
        say("Binary assets changed - this needs the LFS sync, ask Claude.")
        return 1

    if not text_changes:
        say()
        say(f"Space is already up to date with main "
            f"(hf/main = {short(f'{REMOTE_NAME}/{REMOTE_BRANCH}')})")
        return 0

    say()
    say(f"      {len(text_changes)} text file(s) to sync:")
    for p in text_changes:
        say(f"        + {p}")

    say()
    say("[5/6] Preparing the sync worktree...")
    wt = make_worktree()
    try:
        for path in text_changes:
            blob = main_blob(path)
            if blob is None:
                stop(f"could not read main:{SUBFOLDER}/{path}")
            dest = os.path.join(wt, *path.split("/"))
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, "wb") as fh:   # exact bytes, no newline translation
                fh.write(blob)
        say(f"      wrote {len(text_changes)} file(s) into the worktree")

        main_hash = short("main")
        names = ", ".join(text_changes)
        if len(names) > 200:
            names = names[:197] + "..."
        message = f"Sync from main {main_hash}: {names}"

        if dry_run:
            say()
            say("[6/6] --dry-run: not committing and not pushing.")
            say(f"      would commit: {message}")
            say()
            say(f"DONE - dry run only, the Space is unchanged "
                f"(still {short(f'{REMOTE_NAME}/{REMOTE_BRANCH}')}).")
            return 0

        say()
        answer = input(
            f"Push these {len(text_changes)} file(s) to the live Space? (y/n): "
        ).strip().lower()
        if answer != "y":
            say()
            say("STOPPED - cancelled, nothing was pushed.")
            return 1

        say()
        say("[6/6] Committing and pushing to the Space...")
        git_or_stop("add", "--", *text_changes, cwd=wt,
                    what="could not stage the files in the worktree")

        p = git("commit", "-m", message, cwd=wt)
        if p.returncode != 0:
            combined = (p.stdout + p.stderr).decode("utf-8", "replace")
            if "nothing to commit" in combined:
                say("      nothing to commit - the Space already matches.")
                return 0
            for line in combined.strip().splitlines():
                say(f"  {line}")
            stop("could not commit in the worktree")
        say(f"      committed: {message}")

        p = git("push", REMOTE_NAME, f"HEAD:{REMOTE_BRANCH}", cwd=wt)
        if p.returncode != 0:
            err = (p.stderr + p.stdout).decode("utf-8", "replace").strip()
            say()
            for line in err.splitlines():
                say(f"  {line}")
            push_hints(err)
            say()
            say("STOPPED - the push was rejected (see the git output above).")
            return 1
        say("      pushed.")
    finally:
        drop_worktree(wt)

    git("fetch", REMOTE_NAME)
    landed = git_text("log", f"{REMOTE_NAME}/{REMOTE_BRANCH}", "--oneline", "-1")
    say()
    say(f"      hf/{REMOTE_BRANCH} is now: {landed}")
    say()
    say(f"DONE - Space updated to {short(f'{REMOTE_NAME}/{REMOTE_BRANCH}')}. "
        f"Wait 1-2 minutes, then open {LIVE_URL} and press Ctrl+Shift+R.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except KeyboardInterrupt:
        say()
        say("STOPPED - interrupted.")
        sys.exit(1)
