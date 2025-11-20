#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MCP 모듈 패키지의 메인 __init__ 파일.
모든 하위 MCP 모듈의 핵심 함수들을 임포트합니다.
"""

import logging

logger = logging.getLogger(__name__)

def _safe_import(module_name, elements):
    """모듈 임포트 실패 시 경고만 하고 넘어가기 위한 헬퍼 함수"""
    try:
        module = __import__(module_name, globals(), locals(), elements, 1)
        for element in elements:
            globals()[element] = getattr(module, element)
    except ImportError as e:
        logger.warning(f"모듈 로드 실패: {module_name} ({e})")

from .file_content_operations import read_file, read_binary_file, write_file, write_binary_file, append_to_file

from .file_management import create_directory, list_directory, rename, delete_file, delete_empty_directory

from .file_system_composite import move, copy_directory, find_files, find_text_in_files, find_large_files, read_specific_lines, replace_text_in_file, get_directory_size, batch_rename, delete_directory_recursively, read_multiple_files

from .user_interaction_atomic import ask_user_for_input, ask_for_multiline_input, ask_user_for_confirmation, ask_for_password, show_message, display_table, show_progress_bar, clear_screen, show_alert, render_markdown, show_spinner, update_last_line

from .user_interaction_composite import present_options_and_get_choice, present_checkbox_and_get_choices, ask_for_file_path, ask_for_directory_path, confirm_critical_action, get_form_input, ask_for_validated_input, select_file_from_directory, show_diff, prompt_with_autocomplete

from .code_execution_atomic import execute_shell_command, execute_python_code, read_code_file, get_environment_variable, set_environment_variable, execute_sql_query, check_port_status, get_code_complexity, get_function_signature, list_installed_packages, docker_list_containers, docker_list_images

from .code_execution_composite import run_python_script, install_python_package, uninstall_python_package, lint_code_file, format_code_file, get_git_status, clone_git_repository, setup_python_venv, build_docker_image, run_container_from_image, get_container_logs

from .web_network_atomic import fetch_url_content, download_file_from_url, api_get_request, api_post_request, api_put_request, api_delete_request, get_http_status, ping_host, resolve_dns, parse_rss_feed, send_email_smtp, get_http_headers, get_ssl_certificate_info, fetch_dynamic_content, ftp_upload_file, ftp_download_file

# AI가 Git 도구를 인식하고 사용할 수 있도록 __init__.py에 추가합니다.
from .git_version_control import (
    git_init, git_clone, git_status, git_add, git_commit, git_push, git_pull, 
    git_fetch, git_create_branch, git_switch_branch, git_list_branches, 
    git_merge, git_log, git_diff, git_add_remote, git_create_tag, 
    git_list_tags, git_revert_commit, git_show_commit_details, 
    git_get_current_branch, git_list_all_files
)

from .gemini_atomic import ask_gemini

_safe_import("project_workflows", [
    "initialize_project_repository",
    "start_new_feature_branch",
    "commit_and_push_changes",
    "analyze_and_lint_project",
    "revert_last_ai_commit",
    "load_and_analyze_project_code",
    "switch_to_main_and_pull",
    "publish_new_version_tag",
    "run_project_tests",
    "request_ai_code_review",
    "clean_up_merged_branches"
])
# --- 오류 로그에 나타난 추가 모듈 (안전하게 임포트) ---
_safe_import("file_attributes", [])
_safe_import("mcp_custom_tool", [])
_safe_import("create_code_bundle", [])

