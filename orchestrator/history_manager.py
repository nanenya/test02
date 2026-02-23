#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# orchestrator/history_manager.py
"""얇은 어댑터 레이어 — graph_manager에 모든 기능을 위임한다.
기존 함수 시그니처 100% 유지."""

import uuid
from typing import Any, Dict, List, Optional, Tuple

from . import graph_manager


def new_conversation() -> Tuple[str, List]:
    """새 대화 ID(UUID)와 초기 히스토리를 반환합니다."""
    convo_id = str(uuid.uuid4())
    graph_manager.create_conversation(convo_id)
    return convo_id, []


def save_conversation(
    convo_id: str,
    history: List[str],
    title: str = "Untitled",
    plan: Optional[List[Dict]] = None,
    current_group_index: int = 0,
    is_final: bool = False,
) -> str:
    """대화를 SQLite에 저장합니다. convo_id(UUID) 그대로 반환."""
    return graph_manager.save_conversation(
        convo_id, history, title, plan, current_group_index, is_final
    )


def load_conversation(convo_id: str) -> Optional[Dict[str, Any]]:
    """SQLite에서 대화를 불러옵니다."""
    return graph_manager.load_conversation(convo_id)


def list_conversations(
    group_id: Optional[int] = None,
    keyword: Optional[str] = None,
    topic_id: Optional[int] = None,
    status: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """저장된 대화 목록을 반환합니다."""
    return graph_manager.list_conversations(
        group_id=group_id, keyword=keyword, topic_id=topic_id, status=status
    )


def split_conversation(
    original_id: str, split_point_index: int
) -> Tuple[str, str]:
    """대화를 두 개로 분리합니다. (original_id, new_id) 반환."""
    return graph_manager.split_conversation(original_id, split_point_index)
