# test_architect.py
import os
import google.generativeai as genai
from prompts import PromptManager

# 1. Gemini 설정 (API Key는 환경변수 등에서 로드)
genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))

# JSON 모드를 강제하기 위한 모델 설정 (Gemini 1.5 Pro/Flash 권장)
model = genai.GenerativeModel(
    'gemini-1.5-flash',
    generation_config={"response_mime_type": "application/json"}
)

def test_architect():
    # 2. 프롬프트 매니저 인스턴스 생성
    pm = PromptManager()

    # 3. 시뮬레이션 상황 설정 (Mock Data)
    user_request = "현재 프로젝트의 main.py를 분석해서 로깅 기능을 추가하고 싶어. 로그 파일은 logs 폴더에 저장해줘."
    file_list = """
    - main.py
    - requirements.txt
    - README.md
    """

    # 4. 프롬프트 생성 (동적 컨텍스트 주입)
    try:
        final_prompt = pm.get_prompt(
            role="architect",
            user_request=user_request,
            file_list=file_list
        )
        print(f"--- [Generated Prompt] ---\n{final_prompt}\n--------------------------")
    except Exception as e:
        print(f"Prompt Error: {e}")
        return

    # 5. Gemini 실행
    try:
        response = model.generate_content(final_prompt)
        print(f"--- [Gemini Response] ---\n{response.text}")
        
        # JSON 파싱 검증 확인 (Python Body 역할)
        import json
        plan_json = json.loads(response.text)
        print("\n✅ JSON Parsing Successful!")
        print(f"Plan Steps: {len(plan_json.get('plan', []))}")
        
    except Exception as e:
        print(f"❌ Execution Error: {e}")

if __name__ == "__main__":
    test_architect()
