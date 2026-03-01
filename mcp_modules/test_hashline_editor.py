#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# mcp_modules/test_hashline_editor.py
"""Hashline 편집 도구 단위 테스트."""

import json
import os
import re
import tempfile

import pytest

from mcp_modules.hashline_editor import (
    _compute_line_hash,
    hashline_edit,
    read_file_with_hashes,
)


# ── 헬퍼 ──────────────────────────────────────────────────────────────────────


def _make_temp_file(content: str) -> str:
    """내용을 담은 임시 파일을 생성하고 경로를 반환합니다."""
    fd, path = tempfile.mkstemp(suffix=".txt")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(content)
    return path


def _hash(line_num: int, content: str) -> str:
    return _compute_line_hash(line_num, content)


# ── read_file_with_hashes ──────────────────────────────────────────────────────


def test_read_file_with_hashes_format():
    path = _make_temp_file("hello\nworld\n")
    try:
        result = read_file_with_hashes(path)
        output_lines = result.split("\n")
        assert len(output_lines) == 2
        pattern = re.compile(r"^\d+#[0-9A-Za-z+/]{2}\|")
        for line in output_lines:
            assert pattern.match(line), f"접두사 형식 불일치: {line!r}"
    finally:
        os.unlink(path)


def test_hash_deterministic():
    h1 = _compute_line_hash(1, "def foo():")
    h2 = _compute_line_hash(1, "def foo():")
    assert h1 == h2


def test_hash_whitespace_insensitive():
    h1 = _compute_line_hash(3, "  foo  ")
    h2 = _compute_line_hash(3, "foo")
    assert h1 == h2


# ── hashline_edit: replace ─────────────────────────────────────────────────────


def test_replace_single_line():
    path = _make_temp_file("line1\nline2\nline3\n")
    try:
        h = _hash(2, "line2\n")
        edits = json.dumps([{"op": "replace", "pos": f"2#{h}", "lines": ["LINE2"]}])
        result = hashline_edit(path, edits)
        assert "HASH MISMATCH" not in result
        with open(path) as f:
            updated = [l.rstrip("\n") for l in f.readlines()]
        assert updated == ["line1", "LINE2", "line3"]
    finally:
        os.unlink(path)


def test_replace_range():
    path = _make_temp_file("a\nb\nc\nd\n")
    try:
        h2 = _hash(2, "b\n")
        h3 = _hash(3, "c\n")
        edits = json.dumps(
            [{"op": "replace", "pos": f"2#{h2}", "end": f"3#{h3}", "lines": ["X", "Y", "Z"]}]
        )
        result = hashline_edit(path, edits)
        assert "HASH MISMATCH" not in result
        with open(path) as f:
            updated = [l.rstrip("\n") for l in f.readlines()]
        assert updated == ["a", "X", "Y", "Z", "d"]
    finally:
        os.unlink(path)


# ── hashline_edit: append / prepend ───────────────────────────────────────────


def test_append_to_end():
    path = _make_temp_file("a\nb\n")
    try:
        edits = json.dumps([{"op": "append", "lines": ["# EOF"]}])
        hashline_edit(path, edits)
        with open(path) as f:
            updated = [l.rstrip("\n") for l in f.readlines()]
        assert updated[-1] == "# EOF"
        assert updated[:2] == ["a", "b"]
    finally:
        os.unlink(path)


def test_prepend_to_start():
    path = _make_temp_file("a\nb\n")
    try:
        edits = json.dumps([{"op": "prepend", "lines": ["# header"]}])
        hashline_edit(path, edits)
        with open(path) as f:
            updated = [l.rstrip("\n") for l in f.readlines()]
        assert updated[0] == "# header"
        assert updated[1] == "a"
    finally:
        os.unlink(path)


def test_append_after_line():
    path = _make_temp_file("a\nb\nc\n")
    try:
        h1 = _hash(1, "a\n")
        edits = json.dumps([{"op": "append", "pos": f"1#{h1}", "lines": ["inserted"]}])
        hashline_edit(path, edits)
        with open(path) as f:
            updated = [l.rstrip("\n") for l in f.readlines()]
        assert updated == ["a", "inserted", "b", "c"]
    finally:
        os.unlink(path)


# ── hashline_edit: 해시 불일치 ────────────────────────────────────────────────


def test_hash_mismatch_returns_error():
    path = _make_temp_file("hello\nworld\n")
    try:
        edits = json.dumps([{"op": "replace", "pos": "1#ZZ", "lines": ["new"]}])
        result = hashline_edit(path, edits)
        assert "HASH MISMATCH" in result
        # 파일이 변경되지 않았는지 확인
        with open(path) as f:
            assert f.read() == "hello\nworld\n"
    finally:
        os.unlink(path)


def test_mismatch_shows_correct_hash():
    path = _make_temp_file("hello\nworld\n")
    try:
        correct_hash = _hash(1, "hello\n")
        edits = json.dumps([{"op": "replace", "pos": "1#ZZ", "lines": ["new"]}])
        result = hashline_edit(path, edits)
        assert correct_hash in result
    finally:
        os.unlink(path)


# ── hashline_edit: 복수 편집 ──────────────────────────────────────────────────


def test_multiple_edits_applied():
    path = _make_temp_file("a\nb\nc\n")
    try:
        h1 = _hash(1, "a\n")
        h3 = _hash(3, "c\n")
        edits = json.dumps(
            [
                {"op": "replace", "pos": f"1#{h1}", "lines": ["A"]},
                {"op": "replace", "pos": f"3#{h3}", "lines": ["C"]},
            ]
        )
        result = hashline_edit(path, edits)
        assert "HASH MISMATCH" not in result
        with open(path) as f:
            updated = [l.rstrip("\n") for l in f.readlines()]
        assert updated == ["A", "b", "C"]
    finally:
        os.unlink(path)


# ── 에러 처리 ─────────────────────────────────────────────────────────────────


def test_nonexistent_file_raises():
    with pytest.raises(FileNotFoundError):
        read_file_with_hashes("/nonexistent/path/file_xyz_does_not_exist.txt")


def test_invalid_json_raises():
    path = _make_temp_file("hello\n")
    try:
        with pytest.raises(ValueError):
            hashline_edit(path, "not-valid-json{{{")
    finally:
        os.unlink(path)
