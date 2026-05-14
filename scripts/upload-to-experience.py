#!/usr/bin/env python3
"""Transform rvoptkb-extract output.json → Experience Center RV-OptKB and upload.

Reads one or more output.json files (produced by the rvoptkb-extract skill),
maps fields to the RV-OptKB write API format, and uploads via multipart POST.

Usage:
    # Single file
    python3 scripts/upload-to-experience.py data/oneDNN_bd984d09_output.json

    # Batch (with glob)
    python3 scripts/upload-to-experience.py data/oneDNN_*.json

    # Dry-run (print what would be sent, don't upload)
    python3 scripts/upload-to-experience.py --dry-run data/oneDNN_bd984d09_output.json

    # Custom server
    python3 scripts/upload-to-experience.py --server http://localhost:18000 \\
        --token my-token data/oneDNN_bd984d09_output.json

Field mapping (output.json → API):
    idea                 → title
    thought              → summary
    patch.code_diff      → patch_file (saved as temp .diff file, uploaded as multipart)
    (fixed)              → source_agent = "Agent1-Lite"

Dependencies: Python 3.6+ stdlib only.
"""

import argparse
import json
import os
import sys
import tempfile
import urllib.request
import urllib.error
import mimetypes
import uuid
import re

# ── Defaults ──────────────────────────────────────────────────────────────────

DEFAULT_SERVER = "http://192.168.16.234:18000"
DEFAULT_TOKEN = "phase1-dev-token"
SOURCE_AGENT = "Agent1-Lite"
UPLOAD_ENDPOINT = "/api/v1/experience/optkb"


# ── Field Mapping ─────────────────────────────────────────────────────────────


def map_output_to_rvoptkb(output: dict) -> dict:
    """Transform an output.json dict into RV-OptKB write API fields.

    Returns dict with keys: title, summary, source_agent, patch_content.
    """
    patch = output.get("patch", {})
    idea = output.get("idea", "").strip()
    thought = output.get("thought", "").strip()
    code_diff = patch.get("code_diff", "").strip()

    # title: use idea (general design principle category)
    title = idea

    # summary: use thought (actionable optimization technique)
    summary = thought

    return {
        "title": title,
        "summary": summary,
        "source_agent": SOURCE_AGENT,
        "patch_content": code_diff,
    }


def generate_patch_filename(title: str) -> str:
    """Generate a clean .diff filename from the title/subject.

    Handles: "cpu: rv64: gemm: Implemented variable loop unrolling for GEMM"
        → "cpu_rv64_gemm_implemented_variable_loop_unrolling_for_gemm.diff"

    Falls back to a UUID-based name if the title is empty.
    """
    # Remove special chars, replace whitespace with underscores
    safe = re.sub(r'[^\w\s-]', '', title)
    safe = re.sub(r'[-\s]+', '_', safe)
    safe = safe.strip('_').lower()
    if not safe:
        safe = f"patch_{uuid.uuid4().hex[:12]}"
    return f"{safe}.diff"


# ── API Upload ────────────────────────────────────────────────────────────────


def build_multipart_body(fields: dict, file_field: str, file_path: str) -> tuple[bytes, str]:
    """Build a multipart/form-data request body.

    Args:
        fields: dict of form field name → value (strings only)
        file_field: name of the file field (e.g. "patch_file")
        file_path: path to the file to upload

    Returns:
        (body_bytes, content_type_header_value)
    """
    boundary = f"----WebKitFormBoundary{uuid.uuid4().hex}"

    parts: list[bytes] = []

    # Regular form fields
    for name, value in fields.items():
        part = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{name}"\r\n'
            f"\r\n"
            f"{value}\r\n"
        ).encode("utf-8")
        parts.append(part)

    # File field
    with open(file_path, "rb") as f:
        file_data = f.read()
    filename = os.path.basename(file_path)
    content_type = mimetypes.guess_type(file_path)[0] or "application/octet-stream"
    file_part = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="{file_field}"; filename="{filename}"\r\n'
        f"Content-Type: {content_type}\r\n"
        f"\r\n"
    ).encode("utf-8") + file_data + b"\r\n"

    parts.append(file_part)

    # Closing boundary
    parts.append(f"--{boundary}--\r\n".encode("utf-8"))

    body = b"".join(parts)
    content_type_header = f"multipart/form-data; boundary={boundary}"
    return body, content_type_header


def upload_to_experience(
    mapped: dict,
    server: str,
    token: str,
    dry_run: bool = False,
) -> dict:
    """Upload a single mapped entry to the Experience Center RV-OptKB.

    Args:
        mapped: dict from map_output_to_rvoptkb()
        server: base URL of the experience center
        token: auth token
        dry_run: if True, print what would be sent without uploading

    Returns:
        API response dict (or mock response in dry-run mode)
    """
    title = mapped["title"]
    summary = mapped["summary"]
    source_agent = mapped["source_agent"]
    patch_content = mapped["patch_content"]

    if not title:
        print("  ⚠ Skipping: empty title", file=sys.stderr)
        return {"code": -1, "message": "empty title", "data": {}}

    if not summary:
        print("  ⚠ Skipping: empty summary", file=sys.stderr)
        return {"code": -1, "message": "empty summary", "data": {}}

    if not patch_content:
        print("  ⚠ Skipping: empty patch content", file=sys.stderr)
        return {"code": -1, "message": "empty patch content", "data": {}}

    # Write patch content to a temp file
    patch_filename = generate_patch_filename(title)
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".diff", delete=False, prefix="rvoptkb_"
    )
    tmp.write(patch_content)
    tmp_path = tmp.name
    tmp.close()

    form_fields = {
        "title": title,
        "summary": summary,
        "source_agent": source_agent,
    }

    if dry_run:
        print(f"\n  ══ Dry-Run: Would Upload ══")
        print(f"  URL:    {server}{UPLOAD_ENDPOINT}")
        print(f"  Fields: {json.dumps(form_fields, ensure_ascii=False, indent=2)}")
        print(f"  File:   {tmp_path} → {patch_filename}")
        print(f"  Size:   {os.path.getsize(tmp_path)} bytes")
        os.unlink(tmp_path)
        return {"code": 0, "message": "dry-run", "data": {"card_type": "RV-OptKB"}}

    # Build multipart request
    body, content_type = build_multipart_body(
        fields=form_fields,
        file_field="patch_file",
        file_path=tmp_path,
    )

    url = f"{server}{UPLOAD_ENDPOINT}"
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": content_type,
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            response_data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        response_data = {
            "code": e.code,
            "message": f"HTTP {e.code}: {e.reason}",
            "data": {},
        }
        try:
            detail = json.loads(e.read())
            response_data["detail"] = detail
        except Exception:
            pass
    except urllib.error.URLError as e:
        response_data = {
            "code": -1,
            "message": f"Network error: {e.reason}",
            "data": {},
        }
    finally:
        # Clean up temp file
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)

    return response_data


# ── CLI Entry Point ───────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="Upload rvoptkb-extract output.json to Experience Center RV-OptKB",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  %(prog)s data/oneDNN_bd984d09_output.json\n"
            "  %(prog)s data/oneDNN_*.json\n"
            "  %(prog)s --dry-run data/oneDNN_bd984d09_output.json\n"
            "  %(prog)s --server http://localhost:18000 --token my-token output.json\n"
        ),
    )
    parser.add_argument(
        "input_paths",
        nargs="+",
        help="Path(s) to output.json file(s) (supports glob patterns)",
    )
    parser.add_argument(
        "--server",
        default=DEFAULT_SERVER,
        help=f"Experience Center server URL (default: {DEFAULT_SERVER})",
    )
    parser.add_argument(
        "--token",
        default=DEFAULT_TOKEN,
        help="Auth token (default: phase1-dev-token)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be uploaded without actually sending",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Print detailed progress for each file",
    )

    args = parser.parse_args()

    # Collect all input files (expand globs)
    input_files: list[str] = []
    for pattern in args.input_paths:
        import glob
        expanded = glob.glob(pattern)
        if not expanded:
            # If pattern doesn't expand, try it as a literal path
            if os.path.isfile(pattern):
                input_files.append(pattern)
            else:
                print(f"⚠ Warning: no files match '{pattern}'", file=sys.stderr)
        else:
            # Filter to only *_output.json files
            output_only = [f for f in expanded if f.endswith("_output.json")]
            if not output_only:
                print(f"⚠ Warning: no *_output.json files match '{pattern}'", file=sys.stderr)
            input_files.extend(output_only)

    if not input_files:
        print("Error: no valid output.json files found.", file=sys.stderr)
        sys.exit(1)

    # Deduplicate
    input_files = sorted(set(input_files))

    print(f"╔══ Upload to Experience Center {'═' * 35}")
    print(f"║  Server: {args.server}{UPLOAD_ENDPOINT}")
    print(f"║  Files:  {len(input_files)}")
    print(f"║  Agent:  {SOURCE_AGENT}")
    print(f"║  Mode:   {'DRY-RUN' if args.dry_run else 'LIVE'}")
    print(f"╚{'═' * 55}")

    success_count = 0
    skip_count = 0
    fail_count = 0

    for file_path in input_files:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                output = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            print(f"\n  ✗ {os.path.basename(file_path)}: read error: {e}", file=sys.stderr)
            fail_count += 1
            continue

        # Validate schema
        if not all(k in output for k in ("patch", "thought", "idea")):
            print(f"\n  ⚠ {os.path.basename(file_path)}: missing required fields (patch, thought, idea), skipping", file=sys.stderr)
            skip_count += 1
            continue

        try:
            mapped = map_output_to_rvoptkb(output)
        except Exception as e:
            print(f"\n  ✗ {os.path.basename(file_path)}: mapping error: {e}", file=sys.stderr)
            fail_count += 1
            continue

        if args.verbose:
            print(f"\n  ── {os.path.basename(file_path)} ──")
            print(f"  title:   {mapped['title'][:80]}{'...' if len(mapped['title']) > 80 else ''}")
            print(f"  summary: {mapped['summary'][:80]}{'...' if len(mapped['summary']) > 80 else ''}")
            print(f"  patch:   {len(mapped['patch_content'])} bytes")

        result = upload_to_experience(
            mapped,
            server=args.server,
            token=args.token,
            dry_run=args.dry_run,
        )

        code = result.get("code", -1)
        if code == 0:
            card_id = result.get("data", {}).get("card_id", "N/A")
            if args.verbose or not args.dry_run:
                print(f"  ✓ {os.path.basename(file_path)} → card_id={card_id}", file=sys.stderr)
            success_count += 1
        else:
            msg = result.get("message", "unknown error")
            print(f"  ✗ {os.path.basename(file_path)}: {msg}", file=sys.stderr)
            if "detail" in result:
                print(f"    detail: {result['detail']}", file=sys.stderr)
            fail_count += 1

    # Summary
    print(f"\n╔══ Summary {'═' * 47}")
    print(f"║  Total:  {len(input_files)}")
    print(f"║  OK:     {success_count}")
    print(f"║  Skip:   {skip_count}")
    print(f"║  Fail:   {fail_count}")
    print(f"╚{'═' * 55}")


if __name__ == "__main__":
    main()