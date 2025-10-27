#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# orchestrator/history_manager.py

import os
import json
from datetime import datetime
from typing import List, Dict, Any, Tuple, Optional
import uuid

HISTORY_DIR = "history"
os.makedirs(HISTORY_DIR, exist_ok=True)

def new_conversation() -> Tuple[str, List[str]]:
    """새 대화 ID와 초기 히스토리 리스트를 생성합니다."""
    return str(uuid.uuid4()), []

def save_conversation(
    convo_id: str, 
    history: List[str], 
    title: str = "Untitled", 
    plan: List[Dict] = None, 
    current_group_index: int = 0
):
    """
    대화 내용, 실행 계획, 진행 상태를 JSON 파일로 저장합니다.
    """
    filepath = os.path.join(HISTORY_DIR, f"{convo_id}.json")
    data = {
        "id": convo_id,
        "title": title,
        "last_updated": datetime.now().isoformat(),
        "history": history,
        "plan": plan or [],  # (요청사항 2) 실행 계획 저장
        "current_group_index": current_group_index # (요청사항 2) 계획 진행도 저장
    }
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except IOError as e:
        print(f"파일 저장 오류 {filepath}: {e}")


def load_conversation(convo_id: str) -> Optional[Dict[str, Any]]:
    """
    파일에서 대화 상태(히스토리, 계획, 진행도 포함)를 불러옵니다.
    """
    filepath = os.path.join(HISTORY_DIR, f"{convo_id}.json")
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data
    except FileNotFoundError:
        return None
    except json.JSONDecodeError:
        print(f"JSON 파싱 오류: {filepath}")
        return None

def list_conversations() -> List[Dict[str, Any]]:
    """저장된 모든 대화의 메타데이터 목록을 반환합니다."""
    conversations = []
    for filename in os.listdir(HISTORY_DIR):
        if filename.endswith(".json"):
            filepath = os.path.join(HISTORY_DIR, filename)
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    conversations.append({
                        "id": data.get("id"),
                        "title": data.get("title", "제목 없음"),
                        "last_updated": data.get("last_updated", "날짜 없음")
                    })
            except (IOError, json.JSONDecodeError):
                print(f"대화 목록 로드 실패: {filename}")
                
    # 최근순으로 정렬
    conversations.sort(key=lambda x: x.get("last_updated", ""), reverse=True)
    return conversations
