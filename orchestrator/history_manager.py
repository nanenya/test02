#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# orchestrator/history_manager.py

import os
import json
import re
from datetime import datetime
from typing import List, Dict, Any, Tuple, Optional
import uuid

HISTORY_DIR = "history"
os.makedirs(HISTORY_DIR, exist_ok=True)

def _sanitize_title(title: str, max_length: int = 20) -> str:
    """
    (요청사항 3) 파일명에 사용할 수 있도록 제목을 정리합니다.
    한글, 영문, 숫자, 공백, (-, _)만 허용하고 길이를 제한합니다.
    """
    # 허용 문자 외 모든 문자 제거
    sanitized = re.sub(r'[^\w\s가-힣-]', '', title)
    # 공백을 밑줄로 변경
    sanitized = sanitized.replace(' ', '_')
    # 길이 제한
    return sanitized[:max_length]

def new_conversation() -> Tuple[str, List[str]]:
    """새 대화 ID(UUID)와 초기 히스토리 리스트를 생성합니다."""
    return str(uuid.uuid4()), []

def save_conversation(
    convo_id: str, 
    history: List[str], 
    title: str = "Untitled", 
    plan: List[Dict] = None, 
    current_group_index: int = 0,
    is_final: bool = False # (수정) 이 부분이 추가되어야 합니다.
):
    """
    대화 내용, 실행 계획, 진행 상태를 JSON 파일로 저장합니다.
    (요청사항 3) is_final=True 이면 파일명을 '시간-요약.json'으로 변경합니다.
    """
    
    data = {
        "id": convo_id, # 초기 ID (UUID)
        "title": title,
        "last_updated": datetime.now().isoformat(),
        "history": history,
        "plan": plan or [], 
        "current_group_index": current_group_index
    }

    if is_final:
        # (요청사항 3) 최종 저장: 새 파일명 생성
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        safe_title = _sanitize_title(title)
        new_filename = f"{timestamp}-{safe_title}.json"
        
        # 데이터 내부의 ID도 새 파일명으로 업데이트 (list에서 사용)
        data["id"] = new_filename 
        
        filepath = os.path.join(HISTORY_DIR, new_filename)
        
        # 기존 UUID 기반 파일 삭제 시도
        old_filepath = os.path.join(HISTORY_DIR, f"{convo_id}.json")
        if os.path.exists(old_filepath):
            try:
                os.remove(old_filepath)
            except OSError as e:
                print(f"기존 파일 삭제 오류 {old_filepath}: {e}")
                
    else:
        # (요청사항 3) 임시 저장: UUID 기반 파일명 사용
        filepath = os.path.join(HISTORY_DIR, f"{convo_id}.json")

    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except IOError as e:
        print(f"파일 저장 오류 {filepath}: {e}")


def load_conversation(convo_id: str) -> Optional[Dict[str, Any]]:
    """
    파일에서 대화 상태(히스토리, 계획, 진행도 포함)를 불러옵니다.
    (요청사항 3) UUID 또는 최종 파일명(YYYYMMDD...json)으로 로드 시도.
    """
    
    # 1. convo_id가 .json을 포함하는지 확인 (list에서 클릭한 경우)
    if not convo_id.endswith(".json"):
        filename = f"{convo_id}.json"
    else:
        filename = convo_id

    filepath = os.path.join(HISTORY_DIR, filename)
    
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
                        # (요청사항 3) ID를 파일명으로 반환 (load_conversation을 위해)
                        "id": filename, 
                        "title": data.get("title", "제목 없음"),
                        "last_updated": data.get("last_updated", "날짜 없음")
                    })
            except (IOError, json.JSONDecodeError):
                print(f"대화 목록 로드 실패: {filename}")
                
    # 최근순으로 정렬
    conversations.sort(key=lambda x: x.get("last_updated", ""), reverse=True)
    return conversations
