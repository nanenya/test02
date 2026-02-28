#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
claude_tools CLI 진입점

사용법:
    python -m claude_tools scan              # 프로젝트 스캔 (스냅샷 생성)
    python -m claude_tools changes           # 변경 사항 감지
    python -m claude_tools update            # 분석 보고서 자동 갱신
    python -m claude_tools full              # 전체 실행 (scan → changes → update → validate)
    python -m claude_tools summary           # 스냅샷 요약만 출력
    python -m claude_tools validate          # PROJECT_ANALYSIS.md 섹션 2/6/7 자동 검증
    python -m claude_tools migrate           # MD 데이터 → DB 마이그레이션 (1회성)
    python -m claude_tools tracker <table>   # DB 조회
      table 목록:
        requirements  — 완료된 요구사항 (0.1)
        inprogress    — 진행 중인 요구사항 (0.2)
        pending       — 미구현/예정 요구사항 (0.3)
        changes       — 변경 이력 (0.4)
        deleted       — 삭제된 파일 이력 (5.1)
        tests         — 테스트 현황 (6)
        issues        — 알려진 이슈 (10)
        sync          — 이슈→요구사항 동기화 실행 (auto_create + auto_resolve)
        sync --dry-run  — 변경 없이 동기화 미리보기
        bugs          — 미수정 버그 목록 + 에러 상세 (개발 참조용)
        issue <id>    — 단일 이슈 전체 상세 (traceback, context 포함)
    python -m claude_tools req move <번호> <상태>  # 요구사항 상태 변경
      상태: pending | inprogress | done
      ※ inprogress로 이동 시 연결 이슈 상세 자동 표시
"""

import os
import sys
import json


def main():
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1]

    if command == "scan":
        from .project_scanner import save_snapshot, load_snapshot
        output = save_snapshot(project_root)
        print(f"스냅샷 저장 완료: {output}")
        snapshot = load_snapshot(project_root)
        s = snapshot["summary"]
        print(f"  Python: {s['total_py_files']}개 | YAML: {s['total_yaml_files']}개 | "
              f"함수: {s['total_functions']}개 | 클래스: {s['total_classes']}개 | "
              f"라인: {s['total_lines']}줄")

    elif command == "changes":
        from .change_tracker import save_changes, print_changes_summary
        output_path, changes = save_changes(project_root)
        print_changes_summary(changes)

    elif command == "update":
        from .project_scanner import save_snapshot
        save_snapshot(project_root)
        from .report_updater import update_report
        result = update_report(project_root)
        print(f"보고서 갱신 완료: {result}")

    elif command == "full":
        print("=== 1/3 프로젝트 스캔 ===")
        from .project_scanner import save_snapshot, load_snapshot
        save_snapshot(project_root)
        snapshot = load_snapshot(project_root)
        s = snapshot["summary"]
        print(f"  Python: {s['total_py_files']}개 | 함수: {s['total_functions']}개 | "
              f"라인: {s['total_lines']}줄")

        print("\n=== 2/3 변경 감지 ===")
        from .change_tracker import save_changes, print_changes_summary
        _, changes = save_changes(project_root)
        print_changes_summary(changes)

        print("\n=== 3/3 보고서 갱신 ===")
        from .report_updater import update_report
        result = update_report(project_root)
        print(f"  완료: {result}")

        print("\n=== 4/4 검증 ===")
        from .report_validator import validate_all
        validate_all(project_root)

        print("\n=== 5/5 이슈 동기화 ===")
        from .project_tracker import sync_issues, init_tables
        init_tables()
        result = sync_issues()
        if result["created"]:
            print(f"  신규 PENDING 요구사항 {len(result['created'])}개 생성:")
            for r in result["created"]:
                print(f"    #{r['number']} {r['title'][:60]} (이슈 {r['issue_count']}건)")
        else:
            print("  새로운 이슈 기반 요구사항 없음")
        if result["resolved"]:
            print(f"  이슈 {result['resolved']}개 자동 resolved")

    elif command == "summary":
        from .project_scanner import load_snapshot
        snapshot = load_snapshot(project_root)
        if snapshot is None:
            print("스냅샷이 없습니다. 먼저 `python -m claude_tools scan`을 실행하세요.")
            sys.exit(1)

        print(f"=== 프로젝트 요약 (스캔: {snapshot['scan_time'][:19]}) ===")
        s = snapshot["summary"]
        print(f"  Python 파일: {s['total_py_files']}개")
        print(f"  YAML 파일: {s['total_yaml_files']}개")
        print(f"  기타 파일: {s['total_other_files']}개")
        print(f"  총 함수: {s['total_functions']}개")
        print(f"  총 클래스: {s['total_classes']}개")
        print(f"  총 코드 라인: {s['total_lines']}줄")
        print()

        # 파일별 간략 목록
        for filepath in sorted(snapshot["files"]):
            info = snapshot["files"][filepath]
            funcs = len(info.get("functions", []))
            classes = len(info.get("classes", []))
            lines = info.get("total_lines", "?")
            tags = []
            if funcs:
                tags.append(f"fn:{funcs}")
            if classes:
                tags.append(f"cls:{classes}")
            tags.append(f"{lines}L")
            print(f"  {filepath:50s} {' | '.join(tags)}")

    elif command == "validate":
        from .report_validator import validate_all
        validate_all(project_root)

    elif command == "migrate":
        from .project_tracker import migrate_from_md, init_tables
        force = "--force" in sys.argv
        print("=== DB 마이그레이션 (PROJECT_ANALYSIS.md → SQLite) ===")
        init_tables()
        migrate_from_md(force=force)

    elif command == "tracker":
        if len(sys.argv) < 3:
            print("사용법: python -m claude_tools tracker <table>")
            print("  table: requirements | inprogress | pending | changes | deleted | tests | issues")
            sys.exit(1)
        _run_tracker(sys.argv[2])

    elif command == "req":
        # python -m claude_tools req move <번호> <상태>
        if len(sys.argv) < 5 or sys.argv[2] != "move":
            print("사용법: python -m claude_tools req move <번호> <상태>")
            print("  상태: pending | inprogress | done")
            sys.exit(1)
        _run_req_move(sys.argv[3], sys.argv[4])

    else:
        print(f"알 수 없는 명령: {command}")
        print(__doc__)
        sys.exit(1)


def _print_requirements(rows: list, label: str) -> None:
    """요구사항 행 목록을 출력합니다."""
    if not rows:
        print(f"=== {label} (0개) ===")
        print("  (없음)")
        return
    print(f"=== {label} ({len(rows)}개) ===")
    for r in rows:
        date_str = f"  완료: {r['completed_at']}" if r['completed_at'] else ""
        print(f"  #{r['number']:>3} [{r['status']}] {r['title']}")
        if r['applied_files']:
            print(f"         파일: {r['applied_files']}")
        if r['note']:
            print(f"         비고: {r['note']}")
        if date_str:
            print(date_str)


def _run_tracker(table: str) -> None:
    from .project_tracker import (
        list_requirements, list_changes, list_deleted_files,
        list_test_status, init_tables,
    )

    init_tables()

    if table == "requirements":
        rows = list_requirements(status="DONE")
        _print_requirements(rows, "완료된 요구사항 (0.1)")

    elif table == "inprogress":
        rows = list_requirements(status="IN_PROGRESS")
        _print_requirements(rows, "진행 중인 요구사항 (0.2)")

    elif table == "pending":
        rows = list_requirements(status="PENDING")
        _print_requirements(rows, "미구현/예정 요구사항 (0.3)")

    elif table == "changes":
        rows = list_changes(limit=50)
        print(f"=== 변경 이력 ({len(rows)}개) ===")
        for r in rows:
            print(f"  [{r['date']}] {r['description'][:80]}...")
            print(f"           파일: {r['changed_files'][:80]}")

    elif table == "deleted":
        rows = list_deleted_files()
        print(f"=== 삭제된 파일 이력 ({len(rows)}개) ===")
        for r in rows:
            print(f"  {r['module_name']:40s} [{r['level']}] {r['note']}")

    elif table == "tests":
        rows = list_test_status()
        print(f"=== 테스트 현황 ({len(rows)}개) ===")
        for r in rows:
            count_str = f"{r['test_count']}개" if r['test_count'] else "-"
            print(f"  {r['test_file']:45s} → {r['target_module']:30s} ({count_str})")
            if r['note']:
                print(f"    {r['note']}")

    elif table == "issues":
        import sqlite3
        from .project_tracker import get_db_path
        db_path = get_db_path()
        try:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT id, title, severity, status, created_at FROM issues ORDER BY id"
            ).fetchall()
            conn.close()
            print(f"=== 알려진 이슈 ({len(rows)}개) ===")
            for r in rows:
                print(f"  #{r['id']:>3} [{r['status']}|{r['severity']}] {r['title']}")
                print(f"         생성: {r['created_at']}")
        except Exception as e:
            print(f"이슈 조회 실패: {e}")

    elif table == "sync":
        from .project_tracker import sync_issues
        dry_run = "--dry-run" in sys.argv
        label = "[DRY-RUN] " if dry_run else ""
        print(f"=== {label}이슈 → 요구사항 동기화 ===")
        result = sync_issues(dry_run=dry_run)
        created = result["created"]
        if created:
            verb = "생성 예정" if dry_run else "생성됨"
            print(f"  신규 PENDING 요구사항 {len(created)}개 {verb}:")
            for r in created:
                print(f"    #{r['number']} [{r['issue_count']}건] {r['title']}")
                print(f"           {r['note']}")
        else:
            print("  새로운 이슈 기반 요구사항 없음 (모두 이미 처리됨)")
        if not dry_run and result["resolved"]:
            print(f"  이슈 {result['resolved']}개 자동 resolved")

    elif table == "bugs":
        from .project_tracker import list_bug_requirements
        rows = list_bug_requirements()
        if not rows:
            print("=== 미수정 버그 (0개) ===")
            print("  이슈 기반 미완료 요구사항이 없습니다.")
            print("  힌트: python -m claude_tools tracker sync  # 이슈 → 요구사항 동기화")
            return
        print(f"=== 미수정 버그 ({len(rows)}개) — 개발 참조용 ===\n")
        for r in rows:
            status_label = "🔧 진행중" if r["status"] == "IN_PROGRESS" else "⏳ 대기중"
            print(f"{'─'*70}")
            print(f"[요구사항 #{r['number']}] {status_label}")
            print(f"제목  : {r['title']}")
            print(f"이슈  : #{r['issue_id']} | 미해결 동일오류: {r['open_count']}건 | 소스: {r['source']}")
            print(f"오류  : [{r['error_type']}] {r['error_message']}")
            if r["context"]:
                print(f"컨텍스트: {r['context']}")
            if r["traceback"]:
                tb_lines = r["traceback"].strip().splitlines()
                # 마지막 8줄만 표시 (핵심 스택)
                relevant = tb_lines[-8:] if len(tb_lines) > 8 else tb_lines
                print("트레이스백 (마지막 8줄):")
                for line in relevant:
                    print(f"  {line}")
            print(f"힌트  : python -m claude_tools req move {r['number']} inprogress")
            print()

    elif table == "issue":
        # tracker issue <id>
        if len(sys.argv) < 4:
            print("사용법: python -m claude_tools tracker issue <이슈ID>")
            sys.exit(1)
        _run_tracker_issue(sys.argv[3])

    else:
        print(f"알 수 없는 테이블: {table}")
        print("  사용 가능: requirements | inprogress | pending | bugs | changes | deleted | tests | issues | sync")
        sys.exit(1)


def _run_tracker_issue(issue_id_str: str) -> None:
    """단일 이슈 전체 상세를 출력합니다."""
    from .project_tracker import get_issue_detail, get_db_path
    import sqlite3

    try:
        issue_id = int(issue_id_str)
    except ValueError:
        print(f"오류: 이슈 ID가 숫자가 아닙니다 → '{issue_id_str}'")
        sys.exit(1)

    r = get_issue_detail(issue_id)
    if r is None:
        print(f"이슈 #{issue_id}를 찾을 수 없습니다.")
        sys.exit(1)

    # 동일 시그니처 이슈 전체 개수
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    same = conn.execute(
        """SELECT id, status, created_at FROM issues
           WHERE error_type = ? AND SUBSTR(error_message,1,120) = ?
           ORDER BY id""",
        (r["error_type"], r["error_message"][:120]),
    ).fetchall()
    conn.close()

    print(f"{'═'*70}")
    print(f"이슈 #{r['id']} [{r['status']}|{r['severity']}]")
    print(f"{'─'*70}")
    print(f"제목      : {r['title']}")
    print(f"오류 유형 : {r['error_type']}")
    print(f"오류 메시지: {r['error_message']}")
    print(f"소스      : {r['source'] or '(없음)'}")
    print(f"컨텍스트  : {r['context'] or '(없음)'}")
    print(f"생성 시각 : {r['created_at']}")
    if r["resolved_at"]:
        print(f"해결 시각 : {r['resolved_at']}")
    if r["resolution_note"]:
        print(f"해결 노트 : {r['resolution_note']}")

    # 동일 시그니처 이슈 목록
    print(f"\n동일 오류 이슈 ({len(same)}건):")
    for s in same:
        print(f"  #{s['id']:>3} [{s['status']}] {s['created_at']}")

    # 트레이스백 전체
    if r["traceback"]:
        print(f"\n{'─'*70}")
        print("트레이스백 전체:")
        print(r["traceback"])
    print(f"{'═'*70}")


# status 약칭 → DB 값 매핑
_STATUS_MAP = {
    "pending":    "PENDING",
    "inprogress": "IN_PROGRESS",
    "done":       "DONE",
}


def _run_req_move(number_str: str, status_str: str) -> None:
    """요구사항 상태를 변경합니다."""
    from .project_tracker import update_requirement_status, list_requirements, init_tables

    try:
        number = int(number_str)
    except ValueError:
        print(f"오류: 번호가 숫자가 아닙니다 → '{number_str}'")
        sys.exit(1)

    new_status = _STATUS_MAP.get(status_str.lower())
    if new_status is None:
        print(f"오류: 알 수 없는 상태 '{status_str}'")
        print("  사용 가능: pending | inprogress | done")
        sys.exit(1)

    init_tables()
    ok = update_requirement_status(number=number, new_status=new_status)
    if not ok:
        print(f"  오류: #{number} 요구사항을 찾지 못했습니다.")
        return

    rows = list_requirements()
    found = next((r for r in rows if r["number"] == number), None)
    title = found["title"] if found else "(알 수 없음)"
    print(f"  요구사항 #{number} '{title}' → {new_status}")

    # IN_PROGRESS 전환 시: 연결 이슈 상세 자동 출력 (개발 참조)
    if new_status == "IN_PROGRESS" and found and found.get("issue_id"):
        from .project_tracker import get_issue_detail
        import sqlite3
        r = get_issue_detail(found["issue_id"])
        if r:
            db_path = found.get("db_path") or __import__(
                "claude_tools.project_tracker", fromlist=["get_db_path"]
            ).get_db_path()
            from .project_tracker import get_db_path
            conn = sqlite3.connect(get_db_path())
            same_count = conn.execute(
                """SELECT COUNT(*) FROM issues
                   WHERE error_type = ? AND SUBSTR(error_message,1,120) = ?""",
                (r["error_type"], r["error_message"][:120]),
            ).fetchone()[0]
            open_count = conn.execute(
                """SELECT COUNT(*) FROM issues
                   WHERE status='open' AND error_type = ?
                     AND SUBSTR(error_message,1,120) = ?""",
                (r["error_type"], r["error_message"][:120]),
            ).fetchone()[0]
            conn.close()

            print(f"\n{'─'*65}")
            print(f"[수정 참조] 이슈 #{r['id']} — 동일오류 총 {same_count}건 (미해결: {open_count}건)")
            print(f"오류 유형 : {r['error_type']}")
            print(f"오류 메시지: {r['error_message']}")
            if r["context"]:
                print(f"컨텍스트  : {r['context']}")
            if r["traceback"]:
                tb_lines = r["traceback"].strip().splitlines()
                relevant = tb_lines[-10:] if len(tb_lines) > 10 else tb_lines
                print("트레이스백 (마지막 10줄):")
                for line in relevant:
                    print(f"  {line}")
            print(f"전체 상세 : python -m claude_tools tracker issue {r['id']}")
            print(f"{'─'*65}")


if __name__ == "__main__":
    main()
