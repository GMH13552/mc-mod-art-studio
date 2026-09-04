#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
validate_raw_answers_v3.py — Narrow validation of v3 generated raw answers.

Only ``generated_assets_v3/*/raw_answer.txt`` is traversed. Each file is split
into faces (multi-face answers use ``=== face: <id> ===`` markers; single-face
answers are treated as one unnamed block), then every face is independently
parsed with the existing ``text_to_texture.parse_text_to_grid`` parser. The
result is written to ``validate_raw_answers_v3.txt``.

Exit codes
----------
0: every expected raw_answer.txt (and every face inside it) parsed successfully
   -> prints ``VALIDATE: 3/3 raw answers PASS``
1: any file/face failed to parse, could not be read, or the expected 3-file
   contract is not met -> prints failures and ``VALIDATE: ... FAIL``.
"""

from __future__ import annotations

import sys
from pathlib import Path

from package_asset import _clean_face_text, split_face_blocks
from text_to_texture import parse_text_to_grid

_ROOT = Path(__file__).resolve().parent
# 核心仓库没有 generated_assets_v3/ 时，回退校验 examples/*/raw_answer.txt。
if (_ROOT / "generated_assets_v3").exists():
    EXPECTED_COUNT = 3
    ASSETS_DIR = _ROOT / "generated_assets_v3"
elif (_ROOT / "examples").exists():
    EXPECTED_COUNT = 2
    ASSETS_DIR = _ROOT / "examples"
else:
    EXPECTED_COUNT = 0
    ASSETS_DIR = _ROOT / "generated_assets_v3"
REPORT_PATH = _ROOT / "validate_raw_answers_v3.txt"


def main() -> int:
    files = sorted(ASSETS_DIR.glob("*/raw_answer.txt"))
    report_lines: list[str] = []
    failures: list[str] = []
    passed_files = 0

    def emit(line: str) -> None:
        print(line)
        report_lines.append(line)

    for fn in files:
        try:
            text = fn.read_text(encoding="utf-8")
            blocks = split_face_blocks(text)
            if not blocks:
                raise ValueError("no face blocks found")
            file_ok = True
            faces_in_file = 0
            for block_id, block_text in blocks:
                faces_in_file += 1
                try:
                    cleaned = _clean_face_text(block_text)
                    w, h, _rows = parse_text_to_grid(cleaned)
                    label = block_id or "single"
                    emit("PASS %s [%s] (%dx%d)" % (fn, label, w, h))
                except Exception as exc:  # noqa: BLE001 - report every face failure
                    file_ok = False
                    label = block_id or "?"
                    failure = "%s [%s]: %s" % (fn, label, exc)
                    failures.append(failure)
                    emit("FAIL %s: %s" % (fn, failure))
            if file_ok:
                passed_files += 1
                emit("FILE_PASS %s (%d face(s))" % (fn, faces_in_file))
            else:
                emit("FILE_FAIL %s (%d face(s))" % (fn, faces_in_file))
        except Exception as exc:  # noqa: BLE001 - report read/split failure
            failures.append("%s: %s" % (fn, exc))
            emit("FAIL %s: %s" % (fn, exc))

    if len(files) != EXPECTED_COUNT:
        failure = (
            "expected %d raw_answer.txt files under %s, found %d"
            % (EXPECTED_COUNT, ASSETS_DIR, len(files))
        )
        failures.append(failure)
        emit("FAIL %s" % failure)

    if failures:
        emit("FAILURES:")
        for failure in failures:
            emit("  - %s" % failure)
        emit("VALIDATE: %d/%d raw answers FAIL" % (passed_files, len(files)))
        REPORT_PATH.write_text("\n".join(report_lines) + "\n", encoding="utf-8")
        return 1

    emit("VALIDATE: %d/%d raw answers PASS" % (passed_files, EXPECTED_COUNT))
    REPORT_PATH.write_text("\n".join(report_lines) + "\n", encoding="utf-8")
    print("report: %s" % REPORT_PATH.resolve())
    return 0


if __name__ == "__main__":
    sys.exit(main())
