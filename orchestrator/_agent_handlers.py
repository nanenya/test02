#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# orchestrator/_agent_handlers.py — decide_and_act 핸들러 내부 함수

import logging
from .models import AgentRequest, AgentResponse
from .llm_client import (
    generate_execution_plan,
    generate_parallel_plan,
    generate_final_answer,
    generate_title_for_conversation,
    extract_keywords,
    detect_topic_split,
    classify_intent_and_category,
    validate_execution_plan,
)
from .constants import USER_REQUEST_PREFIX, PLAN_VALIDATION_MIN_SCORE
from ._api_helpers import (
    _resp,
    _apply_category_preference,
    _validate_and_replan,
    _format_wisdom,
    _maybe_auto_summarize,
    _prune_history,
    _extract_first_query,
)
from . import history_manager, graph_manager, agent_config_manager, issue_tracker, token_tracker
from . import pipeline_manager

async def _handle_new_query(
    request: AgentRequest,
    convo_id: str,
    history: list,
    effective_system_prompts: list,
    effective_allowed_skills,
) -> AgentResponse:
    """신규 user_input 처리: 의도 분류 → 계획 생성 → PLAN_CONFIRMATION 반환."""
    query = request.user_input or "무엇을 할까요?"

    if request.user_input:
        history.append(f"{USER_REQUEST_PREFIX} {query}")

    # 히스토리 자동 요약 (임계값 초과 시)
    history = await _maybe_auto_summarize(history)

    # P3-C + [D]: 의도 + 복잡도 통합 분류 (단일 LLM 호출)
    intent_full = "analysis"  # 기본값
    task_cat = "deep"         # 기본값
    try:
        intent_full, task_cat = await classify_intent_and_category(
            query, request.model_preference
        )
        if intent_full == "dialogue":
            direct_answer = await generate_final_answer(history, request.model_preference)
            history.append(f"최종 답변: {direct_answer}")
            title_summary = await generate_title_for_conversation(history, request.model_preference)
            history_manager.save_conversation(
                convo_id, history, title_summary, [], 0, is_final=True
            )
            return _resp(
                conversation_id=convo_id,
                status="FINAL_ANSWER",
                history=history,
                message=direct_answer,
            )
    except Exception as intent_err:
        logging.warning(f"IntentGate 실패, 기본값으로 진행: {intent_err}")

    # 카테고리별 시스템 프롬프트 자동 주입
    _intent_system_map = {
        "code_write": "intent_code_write_system",
        "file_ops":   "intent_file_ops_system",
        "web_search": "intent_search_system",
        "analysis":   "intent_analysis_system",
    }
    intent_prompt_name = _intent_system_map.get(intent_full)
    if intent_prompt_name:
        try:
            intent_prompt = agent_config_manager.get_prompt(intent_prompt_name)
            effective_system_prompts = [intent_prompt] + effective_system_prompts
        except KeyError:
            pass

    # [C] 3-tier 자동 라우팅: ultrabrain이면 pipeline_endpoint로
    if task_cat == "ultrabrain" and not request.force_react:
        logging.info(f"[3-tier] 복잡 쿼리 감지 → pipeline_endpoint 라우팅")
        return await pipeline_endpoint(request)

    # P3-B: Planner 역할 프롬프트 주입
    planner_prompts = [agent_config_manager.get_prompt("role_planner")] + effective_system_prompts

    # [B] 지식 로드 및 주입
    try:
        wisdom_entries = graph_manager.load_wisdom(convo_id)
        if wisdom_entries:
            planner_prompts.append(_format_wisdom(wisdom_entries))
    except Exception:
        pass

    requirements_content = ""
    if request.requirement_paths:
        history.append(f"요구사항 파일 참조: {', '.join(request.requirement_paths)}")
        for path in request.requirement_paths:
            try:
                real_path = _validate_requirement_path(path)
                with open(real_path, 'r', encoding='utf-8') as f:
                    requirements_content += f"--- {os.path.basename(real_path)} ---\n"
                    requirements_content += f.read()
                    requirements_content += "\n-----------------------------------\n\n"
            except Exception as e:
                history.append(f"경고: 요구사항 파일 '{path}' 읽기 실패: {e}")

    try:
        _plan_fn = generate_parallel_plan if request.parallel_mode else generate_execution_plan
        plan_list = await _plan_fn(
            user_query=query,
            requirements_content=requirements_content,
            history=history,
            model_preference=request.model_preference,
            system_prompts=planner_prompts,
            allowed_skills=effective_allowed_skills,
        )

        if not plan_list:
            return _resp(
                conversation_id=convo_id,
                status="FINAL_ANSWER",
                history=history,
                message="요청하신 작업에 대해 실행할 단계가 없습니다. (작업 완료)"
            )

        # [D] 카테고리 → model_preference 자동 적용
        _apply_category_preference(plan_list)

        # [E] 계획 검증 게이트
        plan_list = await _validate_and_replan(
            plan_list, query, requirements_content, history,
            request.model_preference, planner_prompts, effective_allowed_skills,
        )

        if not plan_list:
            return _resp(
                conversation_id=convo_id,
                status="FINAL_ANSWER",
                history=history,
                message="요청하신 작업에 대해 실행할 단계가 없습니다. (작업 완료)"
            )

        history = _prune_history(history)
        plan_dicts = [group.model_dump() for group in plan_list]
        history_manager.save_conversation(
            convo_id, history, f"계획: {plan_list[0].description[:20]}...", plan_dicts, 0, is_final=False
        )

        # 병렬 모드 or 여러 그룹 → 전체 계획 요약 표시
        if len(plan_list) > 1:
            parallel_count = sum(1 for g in plan_list if g.can_parallel)
            serial_count = len(plan_list) - parallel_count
            plan_summary = "\n".join(
                f"  [{g.group_id}] {'⚡병렬' if g.can_parallel else '→순차'}: {g.description}"
                for g in plan_list
            )
            msg = (
                f"[전체 {len(plan_list)}단계 계획 | ⚡병렬 {parallel_count}개 · →순차 {serial_count}개]\n"
                f"{plan_summary}"
            )
        else:
            first_group = plan_list[0]
            msg = f"[{first_group.group_id}] {first_group.description}"

        return _resp(
            conversation_id=convo_id,
            status="PLAN_CONFIRMATION",
            history=history,
            message=msg,
            execution_group=plan_list[0],
        )

    except Exception as e:
        issue_tracker.capture_exception(
            e, context=f"generate_execution_plan convo_id={convo_id}", source="agent"
        )
        history.append(f"계획 수립 오류: {e}")
        history_manager.save_conversation(
            convo_id, history, "계획 실패", plan=[], current_group_index=0, is_final=False
        )
        return _resp(
            conversation_id=convo_id,
            status="ERROR",
            history=history,
            message=f"계획 수립 중 오류 발생: {e}",
        )


async def _handle_replan(
    request: AgentRequest,
    convo_id: str,
    history: list,
    data: dict,
    effective_system_prompts: list,
    effective_allowed_skills,
) -> AgentResponse:
    """재계획 처리: 이전 히스토리 기반 다음 그룹 → PLAN_CONFIRMATION or FINAL_ANSWER."""
    try:
        first_query = _extract_first_query(history)

        # P3-B: Reviewer 역할 프롬프트 주입 (재계획 단계)
        reviewer_prompts = [agent_config_manager.get_prompt("role_reviewer")] + effective_system_prompts

        # [B] 지식 로드 및 주입
        try:
            wisdom_entries = graph_manager.load_wisdom(convo_id)
            if wisdom_entries:
                reviewer_prompts.append(_format_wisdom(wisdom_entries))
        except Exception:
            pass

        plan_list = await generate_execution_plan(
            user_query=first_query,
            requirements_content="",
            history=history,
            model_preference=request.model_preference,
            system_prompts=reviewer_prompts,
            allowed_skills=effective_allowed_skills,
        )

        # [D] 카테고리 → model_preference 자동 적용
        if plan_list:
            _apply_category_preference(plan_list)

        # [E] 계획 검증 게이트
        if plan_list:
            plan_list = await _validate_and_replan(
                plan_list, first_query, "", history,
                request.model_preference, reviewer_prompts, effective_allowed_skills,
            )

        if not plan_list:
            final_answer = await generate_final_answer(history, request.model_preference)
            history.append(f"최종 답변: {final_answer}")
            title_summary = await generate_title_for_conversation(history, request.model_preference)
            history_manager.save_conversation(
                convo_id, history, title_summary, [], 0, is_final=True
            )

            # 키워드 추출 (실패 무시)
            try:
                keywords = await extract_keywords(history, request.model_preference)
                if keywords:
                    graph_manager.assign_keywords_to_conversation(convo_id, keywords)
            except Exception as e:
                logging.warning(f"키워드 추출 실패: {e}")

            # 주제 분리 감지 (실패 무시)
            topic_split_info = None
            try:
                topic_split_info = await detect_topic_split(history, request.model_preference)
            except Exception as e:
                logging.warning(f"주제 분리 감지 실패: {e}")

            return _resp(
                conversation_id=convo_id,
                status="FINAL_ANSWER",
                history=history,
                message=final_answer,
                topic_split_info=topic_split_info,
            )

        history = _prune_history(history)
        plan_dicts = [group.model_dump() for group in plan_list]
        history_manager.save_conversation(
            convo_id, history, data.get("title", "진행 중"), plan_dicts, 0, is_final=False
        )

        next_group = plan_list[0]
        return _resp(
            conversation_id=convo_id,
            status="PLAN_CONFIRMATION",
            history=history,
            message=f"[{next_group.group_id}] {next_group.description}",
            execution_group=next_group
        )

    except Exception as e:
        issue_tracker.capture_exception(
            e, context=f"re-plan convo_id={convo_id}", source="agent"
        )
        history.append(f"다음 단계 계획 중 오류: {e}")
        history_manager.save_conversation(
            convo_id, history, "계획 오류", plan=[], current_group_index=0, is_final=False
        )
        return _resp(
            conversation_id=convo_id,
            status="ERROR",
            history=history,
            message=f"다음 단계 계획 중 오류 발생: {e}",
        )


