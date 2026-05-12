#!/usr/bin/env python3
"""Fetch a GitHub commit and produce rvoptkb-extract input JSON.

Usage:
    python3 scripts/fetch-github.py <commit-url> [-o OUTPUT_DIR]

Dependencies: Python 3.6+ stdlib only (no pip packages required).
              Optionally uses `gh` CLI if available (for authenticated API access).
"""

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request

# ── Constants ────────────────────────────────────────────────────────────────

COMMIT_URL_RE = re.compile(
    r'^https?://github\.com/([^/]+)/([^/]+)/commit/([0-9a-fA-F]{40})$'
)
"""Regex: https://github.com/{owner}/{repo}/commit/{40-hex-sha} (case-insensitive SHA)"""

USER_AGENT = 'rvoptkb-extract/1.0'
"""User-Agent header for unauthenticated API requests."""

# ── URL Parsing ──────────────────────────────────────────────────────────────


def parse_commit_url(url: str) -> tuple[str, str, str]:
    """Parse a GitHub commit URL into (owner, repo, sha).

    Raises ValueError if the URL format is invalid.
    """
    m = COMMIT_URL_RE.match(url)
    if not m:
        raise ValueError(
            f"Invalid GitHub commit URL: {url}\n"
            f"Expected format: https://github.com/{{owner}}/{{repo}}/commit/{{40-char-SHA}}"
        )
    return m.group(1), m.group(2), m.group(3).lower()


# ── API Fetching ─────────────────────────────────────────────────────────────


def fetch_via_gh(owner: str, repo: str, sha: str) -> dict | None:
    """Try to fetch commit data using the authenticated gh CLI.

    Returns parsed JSON dict on success, or None on failure.
    Security note: owner/repo/sha are validated by COMMIT_URL_RE regex before
    being passed to subprocess, ensuring no shell injection risk.
    """
    try:
        result = subprocess.run(
            ["gh", "api", f"repos/{owner}/{repo}/commits/{sha}",
             "--jq", "{ message: .commit.message, files: [.files[]? | {filename, patch, status}] }"],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            return None
        data = json.loads(result.stdout)
        # Validate response: gh --jq returns null for missing fields on error
        if not data.get("message"):
            return None
        return data
    except (FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError):
        return None


def fetch_via_curl(owner: str, repo: str, sha: str) -> dict:
    """Fallback: fetch commit data using unauthenticated urllib.

    Raises RuntimeError on HTTP errors or network issues.
    """
    url = f"https://api.github.com/repos/{owner}/{repo}/commits/{sha}"
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": USER_AGENT,
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        if e.code == 403:
            reset_time = e.headers.get("X-RateLimit-Reset", "unknown")
            raise RuntimeError(
                f"GitHub API rate limited. Reset time (epoch): {reset_time}.\n"
                f"Run `gh auth login` for authenticated access."
            )
        elif e.code == 404:
            raise RuntimeError(
                f"Commit not found: repos/{owner}/{repo}/commits/{sha}\n"
                f"Verify the URL is correct and the repository is public."
            )
        raise RuntimeError(f"HTTP {e.code}: {e.reason}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"Network error: {e.reason}")

    # Validate API response has expected structure
    if "commit" not in data:
        api_msg = data.get("message", "unknown error")
        raise RuntimeError(
            f"GitHub API returned unexpected response: '{api_msg}'\n"
            f"Check the repository is public and the commit SHA is valid."
        )

    # Extract files info (handle null files from API edge cases)
    files_info = []
    for f in data.get("files") or []:
        files_info.append({
            "filename": f.get("filename", "unknown"),
            "patch": f.get("patch", ""),
            "status": f.get("status", "modified"),
        })

    return {"message": data["commit"]["message"], "files": files_info}


def fetch_commit(owner: str, repo: str, sha: str) -> dict:
    """Fetch commit data, trying gh CLI first, falling back to urllib."""
    data = fetch_via_gh(owner, repo, sha)
    if data is not None:
        return data
    return fetch_via_curl(owner, repo, sha)


# ── Input JSON Generation ────────────────────────────────────────────────────


def build_input_json(
    commit_msg: str,
    files: list[dict],
    owner: str,
    repo: str,
    sha: str,
    output_dir: str,
) -> tuple[str, str]:
    """Build the input JSON and write to disk.

    Returns (input_path, output_path).
    """
    # Extract patch subject (first line)
    lines = commit_msg.split("\n")
    patch_subject = lines[0].strip() if lines else ""

    # Build combined diff from all file patches
    code_diff_parts = []
    for f in files:
        patch = f.get("patch", "")
        if patch:
            # Prepend the diff header for context
            filename = f.get("filename", "unknown")
            code_diff_parts.append(f"diff --git a/{filename} b/{filename}")
            code_diff_parts.append(patch)
    code_diff = "\n".join(code_diff_parts)

    if not code_diff.strip():
        raise ValueError(
            "Empty diff -- this commit has no code changes (merge commit or revert).\n"
            "Only commits with actual code diffs can be analyzed."
        )

    # Generate file paths
    input_filename = f"{repo}_{sha}_input.json"
    output_filename = f"{repo}_{sha}_output.json"
    input_path = os.path.join(output_dir, input_filename)
    output_path = os.path.join(output_dir, output_filename)

    # Build source commit URL
    source_commit = f"https://github.com/{owner}/{repo}/commit/{sha}"

    input_data = {
        "patch_subject": patch_subject,
        "commit_message": commit_msg,
        "code_diff": code_diff,
        "output_path": output_path,
    }

    with open(input_path, "w", encoding="utf-8") as f:
        json.dump(input_data, f, indent=2, ensure_ascii=False)

    return input_path, output_path


# ── CLI Entry Point ──────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="Fetch a GitHub commit and produce rvoptkb-extract input JSON",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  %(prog)s https://github.com/uxlfoundation/oneDNN/commit/bd984d09...\n"
            "  %(prog)s https://github.com/numpy/numpy/commit/bea458cb... -o ./patches/\n"
        ),
    )
    parser.add_argument(
        "commit_url",
        help="GitHub commit URL (full 40-character SHA required)",
    )
    parser.add_argument(
        "-o", "--output-dir",
        default=".",
        help="Output directory (default: current directory)",
    )
    args = parser.parse_args()

    # Phase 1: Parse URL
    try:
        owner, repo, sha = parse_commit_url(args.commit_url)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    # Phase 2: Create output directory
    try:
        os.makedirs(args.output_dir, exist_ok=True)
    except OSError as e:
        print(f"Error: Cannot create output directory: {e}", file=sys.stderr)
        sys.exit(1)

    # Phase 3: Fetch commit data
    print(f"Fetching commit {sha[:10]} from {owner}/{repo}...", file=sys.stderr)
    try:
        data = fetch_commit(owner, repo, sha)
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    # Phase 4: Build and write input JSON
    if not os.access(args.output_dir, os.W_OK):
        print(f"Error: Output directory is not writable: {args.output_dir}", file=sys.stderr)
        sys.exit(1)

    try:
        input_path, output_path = build_input_json(
            data["message"],
            data["files"],
            owner,
            repo,
            sha,
            args.output_dir,
        )
    except (ValueError, OSError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    # Phase 5: Report success
    print(f"\nInput file created: {input_path}")
    print(f"Output will be written to: {output_path}")
    print(f"\nTo extract knowledge, invoke the skill:")
    print(f'  Skill("rvoptkb-extract", "{input_path}")')


if __name__ == "__main__":
    main()