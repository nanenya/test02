#!/usr/bin/env python3

import httpx
import json

async def search_web(query: str) -> str:
    """
    주어진 쿼리(검색어)를 사용하여 웹을 검색하고, 검색 결과 요약을 반환합니다.
    주로 최신 정보나 특정 주제에 대한 개요를 얻기 위해 사용됩니다.
    
    Args:
        query (str): 웹에서 검색할 검색어.
        
    Returns:
        str: 검색 결과 요약. 검색 결과가 없을 경우 빈 문자열을 반환.
    """
    # 실제 구현에서는 Google Search API, Tavily, SearxNG 등 실제 검색 엔진 API를 사용해야 합니다.
    # 여기서는 예시로 DuckDuckGo의 Instant Answer API를 사용합니다.
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"https://api.duckduckgo.com/?q={query}&format=json")
            response.raise_for_status()
            data = response.json()
            if data.get("AbstractText"):
                return f"검색어 '{query}'에 대한 결과: {data['AbstractText']}"
            return "관련 검색 결과를 찾을 수 없습니다."
        except httpx.HTTPStatusError as e:
            return f"웹 검색 중 오류 발생: {e}"
