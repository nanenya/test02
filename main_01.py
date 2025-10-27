#!/usr/bin/env python3

import typer
import httpx
import uvicorn

app = typer.Typer()

ORCHESTRATOR_URL = "http://127.0.0.1:8000"

@app.command()
def run(
    query: str = typer.Argument(..., help="AI 에이전트에게 내릴 명령어"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="상세 로그를 출력합니다."),
):
    """
    Gemini AI 에이전트를 실행합니다.
    """
    typer.echo(f"🚀 에이전트 실행. 목표: {query}")

    with httpx.Client() as client:
        try:
            response = client.post(
                f"{ORCHESTRATOR_URL}/agent/execute",
                json={"query": query},
                timeout=120  # 2분 타임아웃
            )
            response.raise_for_status()

            data = response.json()

            if verbose:
                typer.secho("\n--- 상세 정보 ---", fg=typer.colors.BRIGHT_BLACK)
                if data.get("tool_call"):
                    typer.echo(f"🛠️ 호출된 도구: {data['tool_call']['tool_name']}")
                    typer.echo(f"💬 인자: {data['tool_call']['arguments']}")
                    typer.echo(f"📋 도구 결과: {data['tool_result']}")
                typer.secho("-----------------\n", fg=typer.colors.BRIGHT_BLACK)

            typer.secho("\n✅ 최종 결과:", fg=typer.colors.GREEN, bold=True)
            typer.echo(data['final_answer'])

        except httpx.HTTPStatusError as e:
            typer.secho(f"오류: 서버에서 에러 응답을 받았습니다. (Status {e.response.status_code})", fg=typer.colors.RED)
            typer.echo(e.response.json())
        except httpx.RequestError:
            typer.secho("오류: 오케스트레이터 서버에 연결할 수 없습니다.", fg=typer.colors.RED)
            typer.echo("FastAPI 서버가 실행 중인지 확인하세요. (예: uvicorn orchestrator.api:app --reload)")

@app.command(name="server")
def run_server(
    host: str = "127.0.0.1",
    port: int = 8000,
    reload: bool = True
):
    """FastAPI 오케스트레이터 서버를 실행합니다."""
    typer.echo(f"🔥 FastAPI 서버 시작: http://{host}:{port}")
    uvicorn.run("orchestrator.api:app", host=host, port=port, reload=reload)


if __name__ == "__main__":
    app()
