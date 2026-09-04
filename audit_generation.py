#!/usr/bin/env python3
"""Audit generated Minecraft asset artifacts.

For each resource directory under --dir:
  * verify prompt.txt, raw_answer.txt, subagent_id.txt, raw_answer.sha256,
    and hashes.json exist
  * recompute raw_answer SHA-256 and compare with the stored .sha256
  * compute prompt.txt SHA-256
  * compare hashes.json against the freshly computed prompt/answer hashes
    and the recorded subagent_id
  * reject raw_answer.txt containing file paths, absolute paths, or known
    internal tool/artifact names, except the intentional ``FILE: <asset path>``
    lines used by the package_asset multi-face format.
  * refresh generation_log.json and write generation-audit.txt

Exit code 0 only when every resource passes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REQUIRED_FILES = (
    "prompt.txt",
    "raw_answer.txt",
    "subagent_id.txt",
    "raw_answer.sha256",
    "hashes.json",
)

HASHES_KEYS = ("prompt_sha256", "answer_sha256", "subagent_id")

# Exact substrings (case-insensitive) that must not appear in raw_answer.txt.
FORBIDDEN_TOKENS = (
    # Workspace/tool names identified by the mc2-audit review and the brief.
    "style_review",
    "build_style_cards",
    "extract_asset_library",
    "minecraft_texture_tool",
    "mc_asset_library",
    "build_entity_regions",
    "manifest",
    "readme",
    "texture_to_text",
    "verify_from_jar",
    # Absolute path prefixes.
    "/mnt/",
    "c:\\",
    # Previously covered pipeline/tool names.
    "asset_to_text",
    "text_to_texture",
    "build_style_prompt",
    "render_prompt_pack",
    "audit_generation",
    "generation_log.json",
    "generation-audit.txt",
    "generated_assets",
    "prompt.txt",
    "raw_answer.txt",
    "subagent_id.txt",
)

# Path-like patterns; these are intentionally specific to avoid flagging URLs
# or ordinary text. A raw answer that leaks a path is a FAIL.
# Leading/trailing delimiter sets include backtick (Markdown inline code) and
# angle brackets as well as the usual whitespace/quote/bracket delimiters.
# Each pattern uses a capturing group for the actual path (no leading
# delimiter), so check_forbidden() can report the path itself.
WINDOWS_ABS_PATH = re.compile(
    r"(?i)(?:^|[\s(,\"'>\[`<])([A-Za-z]:[\\/](?:[A-Za-z0-9_.~-]+[\\/])*[A-Za-z0-9_.~-]+)"
    r"(?=$|[\s),.;:!?\]\"'<>`])"
)
UNC_PATH = re.compile(
    r"(?i)(?:^|[\s(,\"'>\[`<])(\\\\[A-Za-z0-9_.~-]+(?:\\[A-Za-z0-9_.~-]+)+)"
    r"(?=$|[\s),.;:!?\]\"'<>`])"
)
POSIX_ABS_PATH = re.compile(
    r"(?i)(?:^|[\s(,\"'>\[`<])(/(?:[A-Za-z0-9_.~-]+/)*[A-Za-z0-9_.~-]+)"
    r"(?=$|[\s),.;:!?\]\"'<>`])"
)
RELATIVE_PATH = re.compile(
    r"(?i)(?:^|[\s(,\"'>\[`<])((?:\.{1,2}[\\/])?[A-Za-z0-9_.~-]+(?:[\\/][A-Za-z0-9_.~-]+)+)"
    r"(?=$|[\s),.;:!?\]\"'<>`])"
)
PATH_PATTERNS = (
    (WINDOWS_ABS_PATH, "windows-abs"),
    (UNC_PATH, "unc"),
    (POSIX_ABS_PATH, "posix-abs"),
    (RELATIVE_PATH, "relative"),
)

# package_asset multi-face output uses lines such as:
#   FILE: assets/mcmod/textures/block/example.png
# Those path values are intentional metadata, not path leaks.  The whitelist
# below is intentionally narrow: only asset-style paths may be skipped by the
# forbidden-content scan; any other FILE value causes the resource to FAIL.
FILE_LINE_RE = re.compile(r"^\s*FILE\s*:\s*(.*)$", re.IGNORECASE)

# Allowed leading path prefixes for a FILE: metadata value.
FILE_ALLOWED_PREFIXES = ("assets/", "textures/", "models/", "blockstates/")

# Substrings that never belong in a FILE: metadata path.  The case-insensitive
# ones are checked against the lower-cased path in file_path_issues().
FILE_BAD_SUBSTRINGS = ("..", "/mnt/", "c:", "\\")


def sha256_file(path: Path) -> str:
    """Return lowercase hex SHA-256 of a file."""
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def text_sha256(path: Path) -> str:
    """SHA-256 of the raw bytes of a text file (UTF-8)."""
    return sha256_file(path)


def parse_sha256_file(path: Path) -> str:
    """Extract the first 64 hex chars from a .sha256 file like 'hash  file'."""
    data = path.read_text(encoding="utf-8", errors="replace").strip()
    if not data:
        return ""
    m = re.search(r"([0-9a-fA-F]{64})", data)
    return m.group(1).lower() if m else ""


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def load_json_object(path: Path) -> tuple[dict[str, Any] | None, str]:
    """Load a JSON object from a file. Returns (data, '' ) or (None, error)."""
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception as exc:  # noqa: BLE001 - report any JSON parse failure
        return None, f"invalid JSON: {exc}"
    if not isinstance(data, dict):
        return None, f"not a JSON object: {type(data).__name__}"
    return data, ""


def _is_single_char_relative_path(path: str) -> bool:
    """Skip trivial slash-separated single-letter text like 'W/H'."""
    parts = [p for p in re.split(r"[\\/]+", path) if p]
    return bool(parts) and all(len(part) == 1 for part in parts)


def file_path_issues(path: str) -> list[str]:
    """Return reasons why a ``FILE:`` metadata path is not whitelisted."""
    if not path:
        return ["empty FILE metadata path"]

    issues: list[str] = []
    if not path.startswith(FILE_ALLOWED_PREFIXES):
        issues.append(
            "does not start with assets/, textures/, models/, or blockstates/"
        )

    lower = path.lower()
    for bad in FILE_BAD_SUBSTRINGS:
        if bad in lower:
            issues.append(f"contains {bad!r}")
    for token in FORBIDDEN_TOKENS:
        if token in lower:
            issues.append(f"contains forbidden token {token!r}")
    return issues


def collect_file_path_issues(answer: str) -> list[str]:
    """Return invalid ``FILE:`` metadata path findings in ``answer``."""
    issues: list[str] = []
    for line in answer.splitlines():
        match = FILE_LINE_RE.match(line)
        if not match:
            continue
        parts = match.group(1).split(None, 1)
        file_token = parts[0] if parts else ""
        file_issues = file_path_issues(file_token)
        if file_issues:
            issues.append(
                f"invalid FILE path {file_token!r}: {', '.join(file_issues)}"
            )
    return issues


def strip_file_path_prefixes(answer: str) -> str:
    """Remove the path token immediately following a ``FILE:`` marker.

    ``package_asset`` multi-face answers use ``FILE: <asset_path>`` lines as
    intentional metadata. The path after ``FILE:`` is therefore not treated as
    a leak. Anything else on the same line is preserved so that additional
    tool names or paths are still detected.  Invalid FILE values are reported
    separately by :func:`collect_file_path_issues`; this helper only prepares
    the rest of the answer for the normal leaked-path/tool-name scan.
    """
    cleaned_lines: list[str] = []
    for line in answer.splitlines():
        match = FILE_LINE_RE.match(line)
        if match:
            remainder = match.group(1)
            # A FILE: line normally contains exactly one path token. Skip only
            # that first token; keep the rest of the line for normal checks.
            parts = remainder.split(None, 1)
            if parts:
                remainder = parts[1] if len(parts) > 1 else ""
            cleaned_lines.append(remainder)
        else:
            cleaned_lines.append(line)
    return "\n".join(cleaned_lines)


def check_forbidden(answer: str) -> list[str]:
    """Return list of forbidden tokens/path patterns found in the answer."""
    found: list[str] = list(collect_file_path_issues(answer))
    answer = strip_file_path_prefixes(answer)
    lower = answer.lower()
    for token in FORBIDDEN_TOKENS:
        if token in lower:
            found.append(token)
    for pattern, label in PATH_PATTERNS:
        for match in pattern.finditer(answer):
            path_text = match.group(1) if match.lastindex else match.group(0)
            if label == "relative" and _is_single_char_relative_path(path_text):
                continue
            found.append(f"path-like:{label}:{path_text}")
            break
    return found


def audit_resource(root: Path, name: str) -> tuple[dict[str, Any], bool, list[str]]:
    """Audit one resource directory. Returns (log_entry, passed, messages)."""
    rdir = root / name
    messages: list[str] = []
    passed = True

    def fail(msg: str) -> None:
        nonlocal passed
        passed = False
        messages.append(f"  FAIL {msg}")

    def ok(msg: str) -> None:
        messages.append(f"  PASS {msg}")

    missing = [f for f in REQUIRED_FILES if not (rdir / f).is_file()]
    if missing:
        fail(f"missing required files: {', '.join(missing)}")
    else:
        ok("required files present: prompt.txt, raw_answer.txt, subagent_id.txt, raw_answer.sha256, hashes.json")

    # Build log entry with safe fallbacks.
    entry: dict[str, Any] = {
        "name": name,
        "subagent_id": "",
        "prompt_path": "prompt.txt",
        "prompt_sha256": "",
        "answer_path": "raw_answer.txt",
        "answer_sha256": "",
        "model": "unknown/default DSH subagent",
        "provider": "environment subagent",
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }

    prompt_path = rdir / "prompt.txt"
    answer_path = rdir / "raw_answer.txt"
    sha_path = rdir / "raw_answer.sha256"
    subagent_path = rdir / "subagent_id.txt"
    hashes_path = rdir / "hashes.json"

    if prompt_path.is_file():
        entry["prompt_sha256"] = text_sha256(prompt_path)
        ok(f"prompt sha256={entry['prompt_sha256']}")
    else:
        fail("prompt.txt missing; cannot compute prompt sha256")

    if answer_path.is_file():
        actual = text_sha256(answer_path)
        entry["answer_sha256"] = actual
        if sha_path.is_file():
            expected_raw = sha_path.read_text(encoding="utf-8", errors="replace").strip()
            expected = parse_sha256_file(sha_path)
            if expected and actual == expected:
                ok(f"raw_answer sha256 matches: {actual}")
            elif not expected:
                fail(f"raw_answer.sha256 has no valid hex digest: {expected_raw!r}")
            else:
                fail(f"raw_answer sha256 mismatch: actual={actual} expected={expected}")
        else:
            fail("raw_answer.sha256 missing; cannot verify digest")

        forbidden = check_forbidden(read_text(answer_path))
        if forbidden:
            fail(f"raw_answer contains forbidden content: {', '.join(forbidden)}")
        else:
            ok("raw_answer contains no forbidden paths/tool names")
    else:
        fail("raw_answer.txt missing; cannot compute sha256 or forbidden-content check")

    if subagent_path.is_file():
        subagent_id = read_text(subagent_path).strip()
        entry["subagent_id"] = subagent_id
        if subagent_id:
            ok(f"subagent_id present: {subagent_id}")
        else:
            fail("subagent_id.txt is empty")
    else:
        fail("subagent_id.txt missing; cannot record subagent id")

    # Optional: require a UUID-looking subagent id. This is a sanity check,
    # not mandated by the brief, but subagent ids in the workspace are UUIDs.
    if entry["subagent_id"]:
        uuid_re = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
        if not uuid_re.match(entry["subagent_id"]):
            fail(f"subagent_id is not a UUID: {entry['subagent_id']!r}")

    # hashes.json: existence is required by the brief; contents must be
    # computed from the current files, otherwise the audit cannot prove the
    # artifact is self-consistent.
    if hashes_path.is_file():
        hashes_json, hashes_error = load_json_object(hashes_path)
        if hashes_error:
            fail(f"hashes.json {hashes_error}")
        else:
            ok("hashes.json present")
            for key in HASHES_KEYS:
                if key not in hashes_json:
                    fail(f"hashes.json missing key: {key}")
            for key, expected in (
                ("prompt_sha256", entry["prompt_sha256"]),
                ("answer_sha256", entry["answer_sha256"]),
            ):
                if key not in hashes_json:
                    continue
                if not isinstance(hashes_json[key], str):
                    fail(f"hashes.json {key} is not a string")
                elif hashes_json[key].lower() != expected.lower():
                    fail(
                        f"hashes.json {key} mismatch: "
                        f"record={hashes_json[key]!r} actual={expected!r}"
                    )
                else:
                    ok(f"hashes.json {key} matches: {expected}")
            if "subagent_id" in hashes_json:
                if not isinstance(hashes_json["subagent_id"], str):
                    fail("hashes.json subagent_id is not a string")
                elif hashes_json["subagent_id"] != entry["subagent_id"]:
                    fail(
                        f"hashes.json subagent_id mismatch: "
                        f"record={hashes_json['subagent_id']!r} actual={entry['subagent_id']!r}"
                    )
                else:
                    ok(f"hashes.json subagent_id matches: {entry['subagent_id']}")
    else:
        fail("hashes.json missing")

    messages.append(f"Result: {'PASS' if passed else 'FAIL'}")
    return entry, passed, messages


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit generated_assets resource directories.")
    parser.add_argument("--dir", required=True, help="Root directory containing resource directories.")
    args = parser.parse_args()

    root = Path(args.dir).resolve()
    if not root.is_dir():
        print(f"ERROR: {root} is not a directory", file=sys.stderr)
        return 2

    # Treat every immediate subdirectory as one generated resource. This keeps
    # the audit complete while ignoring regular files such as the log/audit.
    resources = sorted([p.name for p in root.iterdir() if p.is_dir()])
    if not resources:
        print(f"ERROR: no resource directories found under {root}", file=sys.stderr)
        return 2

    entries: list[dict[str, Any]] = []
    audit_lines: list[str] = []
    failures = 0

    audit_lines.append(f"Audit root: {root}")
    audit_lines.append(f"Timestamp: {datetime.now(timezone.utc).isoformat(timespec='seconds')}")
    audit_lines.append("")

    for name in resources:
        entry, passed, messages = audit_resource(root, name)
        entries.append(entry)
        if not passed:
            failures += 1
        audit_lines.append(f"Resource: {name}")
        audit_lines.extend(messages)
        audit_lines.append("")

    log_path = root / "generation_log.json"
    log_payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "resource_count": len(entries),
        "resources": entries,
    }
    log_path.write_text(json.dumps(log_payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    passed_count = len(resources) - failures
    audit_lines.append(f"Summary: {passed_count}/{len(resources)} resources PASS, {failures} FAIL")
    audit_lines.append(f"OVERALL: {'PASS' if failures == 0 else 'FAIL'}")

    audit_path = root / "generation-audit.txt"
    audit_path.write_text("\n".join(audit_lines) + "\n", encoding="utf-8")
    print("\n".join(audit_lines))

    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
