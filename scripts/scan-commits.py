#!/usr/bin/env python3
"""Scan a GitHub repository for RISC-V-related commits.

Produces a JSON array of commit URLs for matching commits.
Output is designed to be fed into fetch-github.py for batch processing.

Usage:
    python3 scripts/scan-commits.py <repo-url> [-o DIR] [--max-pages N] [--since DATE]

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

REPO_URL_RE = re.compile(
    r'^https?://github\.com/([^/]+)/([^/]+?)(?:\.git)?/?$'
)
"""Regex: https://github.com/{owner}/{repo} (optional .git and trailing slash)"""

RISCV_KEYWORDS = frozenset({
    'riscv', 'rv64', 'rv32', 'rvv',
    'risc-v', 'riscv64', 'riscv32',
})
"""Keywords used to identify RISC-V-related commits from commit messages.

NOTE: scan-commits is a broad collector — it captures ALL RISC-V-related
commits. The differentiation between optimization and non-optimization
commits is handled by the skill workflow (SKILL.md) during analysis."""

USER_AGENT = 'rvoptkb-extract/1.0'
"""User-Agent header for unauthenticated API requests."""

PER_PAGE = 100
"""Number of commits per API page (GitHub max)."""


# ── URL Parsing ─────────────────────────────────────────────────────────────


def parse_repo_url(url: str) -> tuple[str, str]:
    """Parse a GitHub repo URL into (owner, repo).

    Raises ValueError if the URL format is invalid.
    """
    m = REPO_URL_RE.match(url)
    if not m:
        raise ValueError(
            f"Invalid GitHub repository URL: {url}\n"
            f"Expected format: https://github.com/{{owner}}/{{repo}}"
        )
    return m.group(1), m.group(2)


# ── RISC-V Detection ────────────────────────────────────────────────────────


def is_riscv_commit(message: str) -> bool:
    """Check if a commit message relates to RISC-V.

    Simple keyword matching on the lowercased commit message.
    Designed to be cheap (no diff fetching needed).

    This is a broad filter — it captures ALL RISC-V-related commits.
    The skill workflow (SKILL.md) further distinguishes optimization
    from non-optimization patches during analysis.
    """
    lower = message.lower()
    return any(kw in lower for kw in RISCV_KEYWORDS)


# ── API Fetching ────────────────────────────────────────────────────────────


def fetch_page_via_gh(owner: str, repo: str, page: int, since: str | None) -> list[dict] | None:
    """Fetch one page of commits using authenticated gh CLI.

    Returns list of commit dicts, or None on failure.
    """
    url_path = f"repos/{owner}/{repo}/commits?per_page={PER_PAGE}&page={page}"
    if since:
        url_path += f"&since={since}T00:00:00Z"
    try:
        result = subprocess.run(
            ["gh", "api", url_path, "--jq", ".[] | {sha: .sha, message: .commit.message}"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            return None
        lines = result.stdout.strip()
        if not lines:
            return []
        # gh --jq outputs one JSON object per line for arrays
        return [json.loads(line) for line in lines.split("\n")]
    except (FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError):
        return None


def fetch_page_via_urllib(owner: str, repo: str, page: int, since: str | None) -> list[dict]:
    """Fallback: fetch one page of commits using unauthenticated urllib.

    Returns list of commit dicts. Raises RuntimeError on HTTP/network errors.
    """
    url = (f"https://api.github.com/repos/{owner}/{repo}/commits"
           f"?per_page={PER_PAGE}&page={page}")
    if since:
        url += f"&since={since}T00:00:00Z"
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
                f"Repository not found: {owner}/{repo}\n"
                f"Verify the URL is correct and the repository is public."
            )
        raise RuntimeError(f"HTTP {e.code}: {e.reason}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"Network error: {e.reason}")

    if not isinstance(data, list):
        api_msg = data.get("message", "unknown error") if isinstance(data, dict) else "unexpected response"
        raise RuntimeError(
            f"GitHub API returned unexpected response: '{api_msg}'\n"
            f"Check the repository URL is valid."
        )

    return [
        {"sha": item["sha"], "message": item["commit"]["message"]}
        for item in data
    ]


def fetch_page(owner: str, repo: str, page: int, since: str | None) -> list[dict]:
    """Fetch one page of commits, trying gh CLI first, falling back to urllib."""
    data = fetch_page_via_gh(owner, repo, page, since)
    if data is not None:
        return data
    return fetch_page_via_urllib(owner, repo, page, since)


# ── Scanning Logic ──────────────────────────────────────────────────────────


def scan_repo(owner: str, repo: str, max_pages: int, since: str | None, verbose: bool) -> list[str]:
    """Scan repository commits and return matching commit URLs.

    Args:
        owner: GitHub repository owner.
        repo: GitHub repository name.
        max_pages: Maximum number of pages to scan (0 = unlimited).
        since: Only scan commits after this date (YYYY-MM-DD).
        verbose: Print progress to stderr.

    Returns:
        List of full GitHub commit URLs for matching commits.
    """
    matched_urls: list[str] = []
    total_scanned = 0
    page = 1

    while True:
        if verbose:
            print(f"  Page {page}...", file=sys.stderr)

        commits = fetch_page(owner, repo, page, since)
        total_scanned += len(commits)

        for c in commits:
            if is_riscv_commit(c["message"]):
                sha = c["sha"]
                url = f"https://github.com/{owner}/{repo}/commit/{sha}"
                matched_urls.append(url)
                if verbose:
                    subject = c["message"].split("\n")[0][:80]
                    print(f"    ✓ {sha[:10]} {subject}", file=sys.stderr)

        # Stop conditions
        if len(commits) < PER_PAGE:
            break  # Last page
        if max_pages > 0 and page >= max_pages:
            break
        page += 1

    if verbose:
        print(f"  ─────────────────────────────────", file=sys.stderr)
        print(f"  Scanned: {total_scanned} commits across {page} page(s)", file=sys.stderr)
        print(f"  Matches: {len(matched_urls)}", file=sys.stderr)

    return matched_urls


# ── CLI Entry Point ─────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="Scan a GitHub repository for RISC-V-related commits",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  %(prog)s https://github.com/uxlfoundation/oneDNN\n"
            "  %(prog)s https://github.com/numpy/numpy --max-pages 5 --since 2024-01-01 -v\n"
        ),
    )
    parser.add_argument(
        "repo_url",
        help="GitHub repository URL (e.g., https://github.com/uxlfoundation/oneDNN)",
    )
    parser.add_argument(
        "-o", "--output-dir",
        default="data",
        help="Output directory (default: data/)",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=3,
        help="Maximum pages to scan, 0 = unlimited (default: 3, each page up to 100 commits)",
    )
    parser.add_argument(
        "--since",
        help="Only scan commits after this date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Print progress information to stderr",
    )
    args = parser.parse_args()

    # Phase 1: Parse URL
    try:
        owner, repo = parse_repo_url(args.repo_url)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    # Phase 2: Create output directory
    try:
        os.makedirs(args.output_dir, exist_ok=True)
    except OSError as e:
        print(f"Error: Cannot create output directory: {e}", file=sys.stderr)
        sys.exit(1)

    # Phase 3: Check writability
    if not os.access(args.output_dir, os.W_OK):
        print(f"Error: Output directory is not writable: {args.output_dir}", file=sys.stderr)
        sys.exit(1)

    # Phase 4: Scan commits
    if args.verbose:
        print(f"Scanning {owner}/{repo}...", file=sys.stderr)

    try:
        matched_urls = scan_repo(owner, repo, args.max_pages, args.since, args.verbose)
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    # Phase 5: Write output
    output_filename = f"scan_{repo}.json"
    output_path = os.path.join(args.output_dir, output_filename)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(matched_urls, f, indent=2)

    print(f"\nOutput: {output_path}")
    print(f"  {len(matched_urls)} commit(s) matched")
    if matched_urls:
        print(f"\nTo batch fetch, run:")
        print(f"  jq -r '.[]' {output_path} | while read url; do")
        print(f"    python3 scripts/fetch-github.py \"$url\" -o data/")
        print(f"  done")


if __name__ == "__main__":
    main()