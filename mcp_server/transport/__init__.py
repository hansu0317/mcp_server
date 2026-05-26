from .stdio import run_stdio


def run_sse():
    # FastAPI 설치된 환경에서만 import
    from .sse import router  # noqa: F401
    raise RuntimeError("SSE transport는 FastAPI uvicorn을 통해 실행하세요.")


__all__ = ["run_stdio", "run_sse"]
