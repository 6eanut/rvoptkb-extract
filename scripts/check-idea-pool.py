#!/usr/bin/env python3
"""CLI helper to query and inspect the rvoptkb-extract idea pool.

Usage:
    python3 scripts/check-idea-pool.py                  # Show summary
    python3 scripts/check-idea-pool.py --pool POOL_PATH  # Use custom pool path
    python3 scripts/check-idea-pool.py --idea idea-0001  # Show specific idea
    python3 scripts/check-idea-pool.py --search "vector" # Search ideas
"""

import argparse
import json
import os
import sys

# ── Default Pool Path ────────────────────────────────────────────────────────

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_POOL_PATH = os.path.join(PROJECT_ROOT, "pool", "idea-pool.json")


# ── Pool Reading ─────────────────────────────────────────────────────────────


def read_pool(pool_path: str) -> dict:
    """Read and validate the idea pool JSON file."""
    if not os.path.exists(pool_path):
        print(f"Error: Pool file not found: {pool_path}", file=sys.stderr)
        sys.exit(1)
    try:
        with open(pool_path, "r", encoding="utf-8") as f:
            pool = json.load(f)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid pool JSON: {e}", file=sys.stderr)
        sys.exit(1)

    if "ideas" not in pool:
        print(f"Error: Pool file missing 'ideas' field", file=sys.stderr)
        sys.exit(1)

    return pool


# ── Display ──────────────────────────────────────────────────────────────────


def show_summary(pool: dict, verbose: bool = False):
    """Display a summary of the idea pool."""
    ideas = pool["ideas"]

    print(f"╔══ Idea Pool Summary {'═' * 40}")
    print(f"║  Version:       {pool.get('version', 'N/A')}")
    print(f"║  Ideas:         {len(ideas)}")
    print(f"╚{'═' * 55}")

    for idea in ideas:
        print(f"\n  [{idea['id']}] {idea.get('title', 'N/A')}")
        print(f"       Extensions:{', '.join(idea.get('riscv_extensions', [])) or '(none)'}")

    if not ideas:
        print("\n  (empty pool)")


def show_idea(pool: dict, idea_id: str):
    """Display a single idea in detail."""
    for idea in pool["ideas"]:
        if idea["id"] == idea_id:
            print(f"ID:         {idea['id']}")
            print(f"Title:      {idea['title']}")
            print(f"Extensions: {', '.join(idea['riscv_extensions']) if idea['riscv_extensions'] else '(none)'}")
            return

    print(f"Idea '{idea_id}' not found in pool.")


def search_pool(pool: dict, query: str):
    """Search ideas by keyword (case-insensitive)."""
    q = query.lower()
    results = []

    for idea in pool["ideas"]:
        if q in idea["title"].lower():
            results.append((idea["id"], idea["title"]))

    if results:
        print(f"Search results for '{query}':\n")
        for idea_id, title in results:
            print(f"  {idea_id}: {title}")
    else:
        print(f"No results found for '{query}'.")


# ── CLI Entry Point ──────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="Query and inspect the rvoptkb-extract idea pool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--pool",
        default=DEFAULT_POOL_PATH,
        help=f"Path to idea pool JSON (default: {DEFAULT_POOL_PATH})",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show detailed view (no-op since description was removed; kept for compatibility)",
    )
    parser.add_argument(
        "--idea",
        metavar="IDEA_ID",
        help="Show details for a specific idea (e.g., idea-0001)",
    )
    parser.add_argument(
        "--search",
        metavar="QUERY",
        help="Search ideas by keyword",
    )

    args = parser.parse_args()
    pool = read_pool(args.pool)

    if args.idea:
        show_idea(pool, args.idea)
    elif args.search:
        search_pool(pool, args.search)
    else:
        show_summary(pool, verbose=args.verbose)


if __name__ == "__main__":
    main()