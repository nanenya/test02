#!/usr/bin/env python3


import os
import json
from datetime import datetime
from typing import List, Dict, Any, Tuple
import uuid

HISTORY_DIR = "history"
os.makedirs(HISTORY_DIR, exist_ok=True)

def new_conversation() -> Tuple[str, List[str]]:
    """새 대화 ID와 초기 히스토리 리스트를 생성합니다."""
    return str(uuid.uuid4()), []

def save_conversation(convo_id: str, history: List[str], title: str = "Untitled"):
    """대화 내용을 JSON 파일로 저장합니다."""
    filepath = os.path.join(HISTORY_DIR, f"{convo_id}.json")
    data = {
        "id": convo_id,
        "title": title,
        "last_updated": datetime.now().isoformat(),
        "history": history
    }
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_conversation(convo_id: str) -> List[str]:
    """파일에서 대화 내용을 불러옵니다."""
    filepath = os.path.join(HISTORY_DIR, f"{convo_id}.json")
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data.get("history", [])
    except FileNotFoundError:
        return []

def list_conversations() -> List[Dict[str, Any]]:
    """저장된 모든 대화의 메타데이터 목록을 반환합니다."""
    conversations = []
    for filename in os.listdir(HISTORY_DIR):
        if filename.endswith(".json"):
            filepath = os.path.join(HISTORY_DIR, filename)
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
                conversations.append({
                    "id": data.get("id"),
                    "title": data.get("title"),
                    "last_updated": data.get("last_updated")
                })
    # 최근순으로 정렬
    conversations.sort(key=lambda x: x["last_updated"], reverse=True)
    return conversations
