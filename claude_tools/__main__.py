#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
claude_tools CLI 진입점

사용법:
    python -m claude_tools scan              # 프로젝트 스캔 (스냅샷 생성)
    python -m claude_tools changes           # 변경 사항 감지
    python -m claude_tools update            # 분석 보고서 자동 갱신
    python -m claude_tools full              # 전체 실행 (scan → changes → update)
    python -m claude_tools summary           # 스냅샷 요약만 출력
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

    else:
        print(f"알 수 없는 명령: {command}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
