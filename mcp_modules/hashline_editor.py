#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# mcp_modules/hashline_editor.py
"""Hashline 편집 도구 — LLM이 라인 해시로 파일을 안전하게 편집할 수 있게 합니다.

파일 읽기 시 각 라인에 {n}#{hash}| 접두사를 붙이고,
편집 시 해시를 검증하여 스테일 라인 충돌을 방지합니다.

OMO(Oh My OpenCode) 알고리즘 포팅:
  성공률 6.7% → 68.3% 향상 (원본 벤치마크 기준)
"""

import json
import os
import re
import zlib
from pathlib import Path
from typing import Optional

MAX_HASHLINE_FILE_SIZE = 10 * 1024 * 1024  # 10MB
MAX_HASHLINE_EDITS_PER_CALL = 50


def _atomic_write(path: str, lines: list) -> None:
    """원자적 파일 쓰기: 임시 파일 생성 후 os.replace()로 교체."""
    p = Path(path)
    tmp = p.with_suffix(p.suffix + ".hashline_tmp")
    try:
        tmp.write_text("".join(lines), encoding="utf-8")
        os.replace(str(tmp), str(p))
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)

# 64자 알파벳: 0-9, A-Z, a-z, +, /  (crc32 % 4096 → 2글자 base-64 인코딩)
_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz+/"


def _normalize(content: str) -> str:
    """해시 계산을 위해 공백을 정규화합니다 (라인 끝 제거 + 내부 공백 단일화)."""
    content = content.rstrip("\r\n")
    content = re.sub(r"\s+", " ", content).strip()
    return content


def _compute_line_hash(line_num: int, content: str) -> str:
    """라인 번호와 내용으로 2자리 해시를 계산합니다.

    - 알파벳/숫자 포함 라인: seed="" (내용만으로 해시)
    - 순수 기호·공백 라인: seed=str(line_num) (충돌 방지)
    - 인코딩: zlib.crc32 % 4096 → _ALPHABET 2글자
    """
    normalized = _normalize(content)
    seed = "" if re.search(r"[A-Za-z0-9]", normalized) else str(line_num)
    data = (seed + normalized).encode("utf-8")
    crc = zlib.crc32(data) & 0xFFFFFFFF
    idx = crc % 4096
    return _ALPHABET[idx // 64] + _ALPHABET[idx % 64]


def _parse_hash_ref(ref: str) -> tuple:
    """'5#AB' → (5, 'AB') 파싱."""
    parts = ref.split("#", 1)
    if len(parts) != 2:
        raise ValueError(f"유효하지 않은 해시 참조: {ref!r} (형식: N#XX)")
    try:
        line_num = int(parts[0])
    except ValueError:
        raise ValueError(f"유효하지 않은 라인 번호: {parts[0]!r}")
    return line_num, parts[1]


def _validate_hash(line_num: int, expected_hash: str, lines: list) -> Optional[str]:
    """해시를 검증합니다. 불일치 시 오류 메시지(컨텍스트 포함) 반환, 일치 시 None."""
    if line_num < 1 or line_num > len(lines):
        return f"라인 {line_num}이 범위를 벗어남 (파일은 {len(lines)}개 라인)"
    actual_hash = _compute_line_hash(line_num, lines[line_num - 1])
    if actual_hash == expected_hash:
        return None
    # 컨텍스트 ±2 라인
    start = max(1, line_num - 2)
    end = min(len(lines), line_num + 2)
    ctx_lines = []
    for n in range(start, end + 1):
        h = _compute_line_hash(n, lines[n - 1])
        content = lines[n - 1].rstrip("\n")
        marker = " <-- HERE" if n == line_num else ""
        ctx_lines.append(f"  {n}#{h}|{content}{marker}")
    ctx = "\n".join(ctx_lines)
    return (
        f"해시 불일치 at line {line_num}: expected #{expected_hash}, actual #{actual_hash}\n"
        f"컨텍스트:\n{ctx}\n"
        f"올바른 참조: {line_num}#{actual_hash}"
    )


def _sort_edits(edits: list, lines: list) -> list:
    """편집을 역순(높은 라인 번호 먼저)으로 정렬하여 라인 번호 밀림을 방지합니다."""

    def sort_key(edit):
        op = edit.get("op", "replace")
        pos = edit.get("pos")
        if pos:
            line_num, _ = _parse_hash_ref(pos)
            return line_num
        if op == "append":
            return len(lines) + 1  # 파일 끝 이후 → 가장 먼저 적용
        # prepend without pos → 파일 처음 → 가장 나중에 적용
        return 0

    return sorted(edits, key=sort_key, reverse=True)


def read_file_with_hashes(path: str) -> str:
    """파일을 읽고 각 라인에 {n}#{hash}| 접두사를 추가하여 반환합니다.

    LLM은 이 출력을 보고 편집 요청 시 해시를 참조하여 정확한 라인을 지정합니다.
    접두사 형식: '{라인번호}#{해시}|{내용}'
    예: '11#AB|def foo():'
    """
    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    result = []
    for i, line in enumerate(lines, 1):
        h = _compute_line_hash(i, line)
        content = line.rstrip("\n")
        result.append(f"{i}#{h}|{content}")
    return "\n".join(result)


def hashline_edit(path: str, edits: str) -> str:
    """해시 참조로 파일을 안전하게 편집합니다.

    edits: JSON 배열 문자열
      [
        {"op": "replace", "pos": "5#AB", "end": "7#CD", "lines": ["new line"]},
        {"op": "append", "pos": "3#XY", "lines": ["inserted after line 3"]},
        {"op": "append", "lines": ["# EOF"]},
        {"op": "prepend", "lines": ["#!/usr/bin/env python3"]}
      ]

    op 동작:
      replace — pos~end 범위를 lines로 교체 (end 생략 시 단일 라인)
      append  — pos 다음에 삽입 (pos 생략 시 파일 끝)
      prepend — pos 이전에 삽입 (pos 생략 시 파일 처음)

    해시 불일치 시 편집 없이 오류 메시지와 올바른 해시를 반환합니다.
    """
    # 파일 크기 제한
    file_size = os.path.getsize(path)
    if file_size > MAX_HASHLINE_FILE_SIZE:
        return f"ERROR: 파일 크기 초과 ({file_size // 1024 // 1024}MB > 10MB)"

    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    try:
        edit_list = json.loads(edits)
    except json.JSONDecodeError as e:
        raise ValueError(f"유효하지 않은 JSON: {e}")

    if not isinstance(edit_list, list):
        raise ValueError("edits는 JSON 배열이어야 합니다")

    # 편집 수 제한
    if len(edit_list) > MAX_HASHLINE_EDITS_PER_CALL:
        return f"ERROR: 편집 수 초과 ({len(edit_list)} > {MAX_HASHLINE_EDITS_PER_CALL})"

    # ── 전체 해시 검증 먼저 (fail-fast) ───────────────────────────────────────
    errors = []
    for i, edit in enumerate(edit_list):
        for field in ("pos", "end"):
            ref = edit.get(field)
            if ref:
                line_num, expected_hash = _parse_hash_ref(ref)
                err = _validate_hash(line_num, expected_hash, lines)
                if err:
                    errors.append(f"편집 #{i + 1} {field}: {err}")

    if errors:
        return "HASH MISMATCH — 변경사항 없음:\n" + "\n".join(errors)

    # ── 역순 정렬 적용 ────────────────────────────────────────────────────────
    applied = []
    for edit in _sort_edits(edit_list, lines):
        op = edit.get("op", "replace")
        pos = edit.get("pos")
        end = edit.get("end")
        new_lines_raw = edit.get("lines", [])
        # 각 새 라인에 개행 보장
        new_content = [
            (ln if ln.endswith("\n") else ln + "\n") for ln in new_lines_raw
        ]

        if op == "replace":
            if not pos:
                raise ValueError("replace는 'pos' 필드가 필요합니다")
            start_num, _ = _parse_hash_ref(pos)
            end_num = _parse_hash_ref(end)[0] if end else start_num
            if end_num < start_num:
                raise ValueError(f"end({end_num}) < pos({start_num})")
            lines[start_num - 1 : end_num] = new_content
            applied.append(
                f"replace lines {start_num}-{end_num} → {len(new_content)} lines"
            )

        elif op == "append":
            insert_at = _parse_hash_ref(pos)[0] if pos else len(lines)
            lines[insert_at:insert_at] = new_content
            applied.append(f"append {len(new_content)} lines after {pos or 'EOF'}")

        elif op == "prepend":
            insert_at = _parse_hash_ref(pos)[0] - 1 if pos else 0
            lines[insert_at:insert_at] = new_content
            applied.append(f"prepend {len(new_content)} lines before {pos or 'start'}")

        else:
            raise ValueError(f"알 수 없는 op: {op!r}")

    _atomic_write(path, lines)

    return f"적용 완료 {len(applied)}개 편집:\n" + "\n".join(
        f"  - {a}" for a in applied
    )
