"""
공통 유틸리티: 경로, 로깅, 캐시 키, LLM 호출 래퍼.
모든 단계(①~⑤) 스크립트가 이 모듈을 통해 환경변수/캐시/로그를 다룬다.
"""
import hashlib
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
CACHE_DIR = ROOT_DIR / "cache"
CACHE_SERP_DIR = CACHE_DIR / "serp"

DATA_DIR.mkdir(exist_ok=True)
CACHE_SERP_DIR.mkdir(parents=True, exist_ok=True)

load_dotenv(ROOT_DIR / ".env")


def log(step: str, msg: str):
    """모든 단계에서 동일한 형식으로 진행상황/에러를 콘솔에 출력한다."""
    print(f"[{step}] {msg}", file=sys.stderr)


def get_env(name: str, required: bool = True):
    val = os.environ.get(name, "").strip()
    if required and not val:
        log("ENV", f"⚠️  {name} 가 .env 에 설정되어 있지 않습니다. .env 파일을 확인하세요.")
    return val or None


def keyword_hash(keyword: str) -> str:
    """캐시 파일명을 만들기 위한 키워드 해시(짧고 파일명-안전)."""
    return hashlib.md5(keyword.strip().lower().encode("utf-8")).hexdigest()[:16]


def load_json(path: Path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def call_llm(system: str, user: str, step: str, max_tokens: int = 2000) -> str:
    """
    Anthropic LLM 호출 공통 래퍼.
    실패 시 조용히 넘어가지 않고 원인을 찍은 뒤 예외를 다시 던져
    해당 단계만 재시도할 수 있게 한다.
    """
    api_key = get_env("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY 가 없습니다. .env 파일에 키를 넣은 뒤 이 단계를 다시 실행하세요."
        )
    try:
        import anthropic

        client = anthropic.Anthropic(api_key=api_key)
        resp = client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return resp.content[0].text
    except Exception as e:
        log(step, f"❌ LLM 호출 실패: {e}")
        raise
