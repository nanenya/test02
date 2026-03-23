#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# orchestrator/_config_store.py — 에이전트 설정 DB 초기화 + CRUD 함수
"""에이전트 설정 DB 초기화, 시드, CRUD 함수 모음."""

import json
import logging
import re
from datetime import datetime
from .constants import utcnow
from pathlib import Path
from typing import Any, Dict, List, Optional

from .graph_manager import DB_PATH, get_db


# ── 인메모리 프롬프트 캐시 (update/delete 시 무효화) ─────────────
_PROMPT_CACHE: dict[str, str] = {}

# 매크로 변수 패턴 {{var}}
_MACRO_VAR_RE = re.compile(r'\{\{(\w+)\}\}')


def _apply_update(conn, table: str, name: str, now: str, **fields) -> None:
    """동적 UPDATE 쿼리를 빌드하여 실행합니다.

    fields에 포함된 None 값은 무시됩니다.
    """
    clauses = ["updated_at=?"]
    params: List[Any] = [now]
    for col, val in fields.items():
        if val is not None:
            clauses.append(f"{col}=?")
            params.append(val)
    params.append(name)
    conn.execute(f"UPDATE {table} SET {', '.join(clauses)} WHERE name=?", params)


# ── DB 초기화 ─────────────────────────────────────────────────────

def init_db(path: Path = DB_PATH) -> None:
    """에이전트 설정 5개 테이블을 IF NOT EXISTS로 생성."""
    with get_db(path) as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS system_prompts (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT    NOT NULL UNIQUE,
            content     TEXT    NOT NULL,
            description TEXT    NOT NULL DEFAULT '',
            is_default  INTEGER NOT NULL DEFAULT 0,
            created_at  TEXT    NOT NULL,
            updated_at  TEXT    NOT NULL
        );
        """)
        # prompt_type 컬럼 마이그레이션 (이미 존재하면 무시)
        try:
            conn.execute(
                "ALTER TABLE system_prompts ADD COLUMN prompt_type TEXT NOT NULL DEFAULT 'system'"
            )
        except Exception:
            pass
        conn.executescript("""

        CREATE TABLE IF NOT EXISTS skills (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT    NOT NULL UNIQUE,
            source      TEXT    NOT NULL DEFAULT 'local',
            description TEXT    NOT NULL DEFAULT '',
            is_active   INTEGER NOT NULL DEFAULT 1,
            created_at  TEXT    NOT NULL,
            synced_at   TEXT    NOT NULL
        );

        CREATE TABLE IF NOT EXISTS skill_macros (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT    NOT NULL UNIQUE,
            description TEXT    NOT NULL DEFAULT '',
            template    TEXT    NOT NULL,
            variables   TEXT    NOT NULL DEFAULT '[]',
            created_at  TEXT    NOT NULL,
            updated_at  TEXT    NOT NULL
        );

        CREATE TABLE IF NOT EXISTS workflows (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT    NOT NULL UNIQUE,
            description TEXT    NOT NULL DEFAULT '',
            steps       TEXT    NOT NULL DEFAULT '[]',
            created_at  TEXT    NOT NULL,
            updated_at  TEXT    NOT NULL
        );

        CREATE TABLE IF NOT EXISTS personas (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            name              TEXT    NOT NULL UNIQUE,
            display_name      TEXT    NOT NULL DEFAULT '',
            system_prompt     TEXT    NOT NULL,
            system_prompt_ref TEXT    DEFAULT NULL,
            allowed_skills    TEXT    NOT NULL DEFAULT '[]',
            keywords          TEXT    NOT NULL DEFAULT '[]',
            description       TEXT    NOT NULL DEFAULT '',
            is_default        INTEGER NOT NULL DEFAULT 0,
            created_at        TEXT    NOT NULL,
            updated_at        TEXT    NOT NULL
        );
        """)


from ._default_prompts import _DEFAULT_PROMPTS

def _seed_default_prompts(db_path: Path = DB_PATH) -> None:
    """기본 프롬프트 22개를 INSERT OR IGNORE로 삽입합니다 (멱등성 보장)."""
    now = utcnow()
    with get_db(db_path) as conn:
        for name, prompt_type, description, content in _DEFAULT_PROMPTS:
            conn.execute(
                """
                INSERT OR IGNORE INTO system_prompts
                    (name, content, description, is_default, prompt_type, created_at, updated_at)
                VALUES (?, ?, ?, 0, ?, ?, ?)
                """,
                (name, content, description, prompt_type, now, now),
            )



# ── 시스템 프롬프트 CRUD ─────────────────────────────────────────

def create_system_prompt(
    name: str,
    content: str,
    description: str = "",
    is_default: bool = False,
    db_path: Path = DB_PATH,
) -> int:
    """시스템 프롬프트 생성. is_default=True면 기존 기본값 해제 후 설정."""
    now = utcnow()
    with get_db(db_path) as conn:
        if is_default:
            conn.execute("UPDATE system_prompts SET is_default=0 WHERE is_default=1")
        cur = conn.execute(
            """
            INSERT INTO system_prompts (name, content, description, is_default, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (name, content, description, int(is_default), now, now),
        )
        return cur.lastrowid


def get_system_prompt(name: str, db_path: Path = DB_PATH) -> Optional[Dict]:
    with get_db(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM system_prompts WHERE name=?", (name,)
        ).fetchone()
        return dict(row) if row else None


def get_default_system_prompt(db_path: Path = DB_PATH) -> Optional[Dict]:
    with get_db(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM system_prompts WHERE is_default=1 LIMIT 1"
        ).fetchone()
        return dict(row) if row else None


def list_system_prompts(db_path: Path = DB_PATH) -> List[Dict]:
    with get_db(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM system_prompts ORDER BY is_default DESC, name"
        ).fetchall()
        return [dict(r) for r in rows]


def update_system_prompt(
    name: str,
    content: Optional[str] = None,
    description: Optional[str] = None,
    is_default: Optional[bool] = None,
    db_path: Path = DB_PATH,
) -> bool:
    now = utcnow()
    with get_db(db_path) as conn:
        existing = conn.execute(
            "SELECT id FROM system_prompts WHERE name=?", (name,)
        ).fetchone()
        if not existing:
            return False
        if is_default is True:
            conn.execute("UPDATE system_prompts SET is_default=0 WHERE is_default=1")
        try:
            _apply_update(
                conn, "system_prompts", name, now,
                content=content,
                description=description,
                is_default=int(is_default) if is_default is not None else None,
            )
        finally:
            _PROMPT_CACHE.pop(name, None)
        return True


def delete_system_prompt(name: str, db_path: Path = DB_PATH) -> bool:
    with get_db(db_path) as conn:
        cur = conn.execute("DELETE FROM system_prompts WHERE name=?", (name,))
        _PROMPT_CACHE.pop(name, None)
        return cur.rowcount > 0


def migrate_prompts_from_files(
    prompts_dir: str,
    db_path: Path = DB_PATH,
) -> int:
    """system_prompts/*.txt → system_prompts 테이블. INSERT OR IGNORE (멱등). 마이그레이션 수 반환."""
    imported = 0
    prompts_path = Path(prompts_dir)
    if not prompts_path.exists():
        logging.warning(f"프롬프트 디렉토리가 없습니다: {prompts_dir}")
        return 0

    for txt_file in sorted(prompts_path.glob("*.txt")):
        name = txt_file.stem
        try:
            content = txt_file.read_text(encoding="utf-8")
        except Exception as e:
            logging.warning(f"파일 읽기 실패 {txt_file}: {e}")
            continue

        is_default = name == "default"
        now = utcnow()
        with get_db(db_path) as conn:
            existing = conn.execute(
                "SELECT id FROM system_prompts WHERE name=?", (name,)
            ).fetchone()
            if existing:
                continue
            if is_default:
                conn.execute("UPDATE system_prompts SET is_default=0 WHERE is_default=1")
            conn.execute(
                """
                INSERT INTO system_prompts (name, content, description, is_default, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (name, content, f"파일에서 임포트: {txt_file.name}", int(is_default), now, now),
            )
        imported += 1

    return imported


# ── 스킬 CRUD ────────────────────────────────────────────────────

def sync_skills_from_registry(db_path: Path = DB_PATH) -> int:
    """tool_registry의 로컬 모듈을 로드하고 skills 테이블과 동기화. 신규 추가 수 반환."""
    from .tool_registry import _load_local_modules, TOOL_DESCRIPTIONS

    _load_local_modules()

    now = utcnow()
    added = 0
    updated = 0

    for tool_name, description in TOOL_DESCRIPTIONS.items():
        with get_db(db_path) as conn:
            existing = conn.execute(
                "SELECT id FROM skills WHERE name=?", (tool_name,)
            ).fetchone()
            if existing:
                conn.execute(
                    "UPDATE skills SET description=?, synced_at=? WHERE name=?",
                    (description, now, tool_name),
                )
                updated += 1
            else:
                conn.execute(
                    """
                    INSERT INTO skills (name, source, description, is_active, created_at, synced_at)
                    VALUES (?, 'local', ?, 1, ?, ?)
                    """,
                    (tool_name, description, now, now),
                )
                added += 1

    total = len(TOOL_DESCRIPTIONS)
    logging.info(
        f"스킬 동기화 완료: 신규 {added}개 추가, 기존 {updated}개 갱신 "
        f"(전체 {total}개 처리)"
    )
    return added


def list_skills(active_only: bool = True, db_path: Path = DB_PATH) -> List[Dict]:
    with get_db(db_path) as conn:
        if active_only:
            rows = conn.execute(
                "SELECT * FROM skills WHERE is_active=1 ORDER BY name"
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM skills ORDER BY name"
            ).fetchall()
        return [dict(r) for r in rows]


def get_skill(name: str, db_path: Path = DB_PATH) -> Optional[Dict]:
    with get_db(db_path) as conn:
        row = conn.execute("SELECT * FROM skills WHERE name=?", (name,)).fetchone()
        return dict(row) if row else None


def set_skill_active(name: str, active: bool, db_path: Path = DB_PATH) -> bool:
    with get_db(db_path) as conn:
        cur = conn.execute(
            "UPDATE skills SET is_active=? WHERE name=?", (int(active), name)
        )
        return cur.rowcount > 0


# ── 스킬 매크로 CRUD ─────────────────────────────────────────────

def create_macro(
    name: str,
    template: str,
    description: str = "",
    variables: Optional[List[str]] = None,
    db_path: Path = DB_PATH,
) -> int:
    """스킬 매크로 생성. variables 미제공 시 {{var}} 패턴으로 자동 추출."""
    if variables is None:
        variables = _MACRO_VAR_RE.findall(template)
    now = utcnow()
    with get_db(db_path) as conn:
        cur = conn.execute(
            """
            INSERT INTO skill_macros (name, description, template, variables, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (name, description, template, json.dumps(variables, ensure_ascii=False), now, now),
        )
        return cur.lastrowid


def get_macro(name: str, db_path: Path = DB_PATH) -> Optional[Dict]:
    with get_db(db_path) as conn:
        row = conn.execute("SELECT * FROM skill_macros WHERE name=?", (name,)).fetchone()
        if not row:
            return None
        d = dict(row)
        d["variables"] = json.loads(d["variables"])
        return d


def list_macros(db_path: Path = DB_PATH) -> List[Dict]:
    with get_db(db_path) as conn:
        rows = conn.execute("SELECT * FROM skill_macros ORDER BY name").fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["variables"] = json.loads(d["variables"])
            result.append(d)
        return result


def update_macro(
    name: str,
    template: Optional[str] = None,
    description: Optional[str] = None,
    variables: Optional[List[str]] = None,
    db_path: Path = DB_PATH,
) -> bool:
    now = utcnow()
    with get_db(db_path) as conn:
        existing = conn.execute(
            "SELECT id, template FROM skill_macros WHERE name=?", (name,)
        ).fetchone()
        if not existing:
            return False
        if template is not None and variables is None:
            variables = _MACRO_VAR_RE.findall(template)
        _apply_update(
            conn, "skill_macros", name, now,
            template=template,
            description=description,
            variables=json.dumps(variables, ensure_ascii=False) if variables is not None else None,
        )
        return True


def delete_macro(name: str, db_path: Path = DB_PATH) -> bool:
    with get_db(db_path) as conn:
        cur = conn.execute("DELETE FROM skill_macros WHERE name=?", (name,))
        return cur.rowcount > 0


def render_macro(name: str, bindings: Dict[str, str], db_path: Path = DB_PATH) -> str:
    """매크로 템플릿에 변수 바인딩 적용. 누락된 변수는 KeyError 발생."""
    macro = get_macro(name, db_path)
    if not macro:
        raise KeyError(f"매크로 '{name}'을 찾을 수 없습니다.")
    template = macro["template"]
    variables = macro["variables"]
    for var in variables:
        if var not in bindings:
            raise KeyError(f"매크로 '{name}': 변수 '{var}'가 bindings에 없습니다.")
    result = template
    for key, value in bindings.items():
        result = result.replace(f"{{{{{key}}}}}", value)
    return result


# ── 워크플로우 CRUD ──────────────────────────────────────────────

def create_workflow(
    name: str,
    steps: List[Dict],
    description: str = "",
    db_path: Path = DB_PATH,
) -> int:
    now = utcnow()
    with get_db(db_path) as conn:
        cur = conn.execute(
            """
            INSERT INTO workflows (name, description, steps, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (name, description, json.dumps(steps, ensure_ascii=False), now, now),
        )
        return cur.lastrowid


def get_workflow(name: str, db_path: Path = DB_PATH) -> Optional[Dict]:
    with get_db(db_path) as conn:
        row = conn.execute("SELECT * FROM workflows WHERE name=?", (name,)).fetchone()
        if not row:
            return None
        d = dict(row)
        d["steps"] = json.loads(d["steps"])
        return d


def list_workflows(db_path: Path = DB_PATH) -> List[Dict]:
    with get_db(db_path) as conn:
        rows = conn.execute("SELECT * FROM workflows ORDER BY name").fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["steps"] = json.loads(d["steps"])
            result.append(d)
        return result


def update_workflow(
    name: str,
    steps: Optional[List[Dict]] = None,
    description: Optional[str] = None,
    db_path: Path = DB_PATH,
) -> bool:
    now = utcnow()
    with get_db(db_path) as conn:
        existing = conn.execute(
            "SELECT id FROM workflows WHERE name=?", (name,)
        ).fetchone()
        if not existing:
            return False
        _apply_update(
            conn, "workflows", name, now,
            steps=json.dumps(steps, ensure_ascii=False) if steps is not None else None,
            description=description,
        )
        return True


def delete_workflow(name: str, db_path: Path = DB_PATH) -> bool:
    with get_db(db_path) as conn:
        cur = conn.execute("DELETE FROM workflows WHERE name=?", (name,))
        return cur.rowcount > 0


# ── 페르소나 CRUD ────────────────────────────────────────────────

def create_persona(
    name: str,
    system_prompt: str,
    allowed_skills: Optional[List[str]] = None,
    keywords: Optional[List[str]] = None,
    description: str = "",
    display_name: str = "",
    system_prompt_ref: Optional[str] = None,
    is_default: bool = False,
    db_path: Path = DB_PATH,
) -> int:
    now = utcnow()
    if allowed_skills is None:
        allowed_skills = []
    if keywords is None:
        keywords = []
    with get_db(db_path) as conn:
        if is_default:
            conn.execute("UPDATE personas SET is_default=0 WHERE is_default=1")
        cur = conn.execute(
            """
            INSERT INTO personas
                (name, display_name, system_prompt, system_prompt_ref,
                 allowed_skills, keywords, description, is_default, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                name,
                display_name,
                system_prompt,
                system_prompt_ref,
                json.dumps(allowed_skills, ensure_ascii=False),
                json.dumps(keywords, ensure_ascii=False),
                description,
                int(is_default),
                now,
                now,
            ),
        )
        return cur.lastrowid


def _parse_persona_row(row) -> Dict:
    d = dict(row)
    d["allowed_skills"] = json.loads(d["allowed_skills"])
    d["keywords"] = json.loads(d["keywords"])
    return d


def get_persona(name: str, db_path: Path = DB_PATH) -> Optional[Dict]:
    with get_db(db_path) as conn:
        row = conn.execute("SELECT * FROM personas WHERE name=?", (name,)).fetchone()
        return _parse_persona_row(row) if row else None


def list_personas(db_path: Path = DB_PATH) -> List[Dict]:
    with get_db(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM personas ORDER BY is_default DESC, name"
        ).fetchall()
        return [_parse_persona_row(r) for r in rows]


def update_persona(
    name: str,
    system_prompt: Optional[str] = None,
    allowed_skills: Optional[List[str]] = None,
    keywords: Optional[List[str]] = None,
    description: Optional[str] = None,
    display_name: Optional[str] = None,
    system_prompt_ref: Optional[str] = None,
    is_default: Optional[bool] = None,
    db_path: Path = DB_PATH,
) -> bool:
    now = utcnow()
    with get_db(db_path) as conn:
        existing = conn.execute(
            "SELECT id FROM personas WHERE name=?", (name,)
        ).fetchone()
        if not existing:
            return False
        if is_default is True:
            conn.execute("UPDATE personas SET is_default=0 WHERE is_default=1")
        _apply_update(
            conn, "personas", name, now,
            system_prompt=system_prompt,
            allowed_skills=json.dumps(allowed_skills, ensure_ascii=False) if allowed_skills is not None else None,
            keywords=json.dumps(keywords, ensure_ascii=False) if keywords is not None else None,
            description=description,
            display_name=display_name,
            system_prompt_ref=system_prompt_ref,
            is_default=int(is_default) if is_default is not None else None,
        )
        return True


def delete_persona(name: str, db_path: Path = DB_PATH) -> bool:
    with get_db(db_path) as conn:
        cur = conn.execute("DELETE FROM personas WHERE name=?", (name,))
        return cur.rowcount > 0


def get_effective_persona(
    query: str = "",
    explicit_name: Optional[str] = None,
    db_path: Path = DB_PATH,
) -> Optional[Dict]:
    """
    페르소나 자동 감지 알고리즘:
    1. explicit_name 있음 → get_persona(explicit_name). 없으면 WARNING 후 Step 2로
    2. 모든 페르소나 로드 → keywords 있는 것만 스코어링
       score = sum(1 for kw in keywords if kw.lower() in query.lower())
       동점 → keywords 개수 많은 쪽(더 구체적) 우선
    3. best_score >= 1 → 해당 페르소나 반환
    4. 매치 없음 → is_default=1인 페르소나 반환
    5. 기본도 없음 → None 반환
    """
    if explicit_name:
        persona = get_persona(explicit_name, db_path)
        if persona:
            return persona
        logging.warning(f"페르소나 '{explicit_name}'을 찾을 수 없습니다. 자동 감지로 대체합니다.")

    personas = list_personas(db_path)
    query_lower = query.lower()

    best_persona = None
    best_score = 0
    best_kw_count = 0

    for persona in personas:
        keywords = persona.get("keywords", [])
        if not keywords:
            continue
        score = sum(1 for kw in keywords if kw.lower() in query_lower)
        kw_count = len(keywords)
        if score > best_score or (score == best_score and score >= 1 and kw_count > best_kw_count):
            best_score = score
            best_kw_count = kw_count
            best_persona = persona

    if best_score >= 1:
        return best_persona

    # is_default 페르소나 반환
    for persona in personas:
        if persona.get("is_default"):
            return persona

    return None
