"""
SERP 벤더 어댑터 (오늘은 Serper 하나만 구현, 인터페이스는 다중화 가능하게 분리).
캐시 우선 조회: cache/serp/{키워드해시}.json 이 있으면 API를 호출하지 않는다.
실키가 없을 때는 이 파일 대신 미리 만들어둔 캐시로 데모를 완주할 수 있다.
"""
import requests

from common import CACHE_SERP_DIR, get_env, keyword_hash, load_json, log, save_json

STEP = "serp-client"


def fetch_serp(keyword: str, num: int = 5):
    """
    키워드에 대한 상위 num개 SERP 결과를 반환한다.
    [{rank, url, domain, title, snippet}, ...] 형태.
    cache 우선, 없으면 Serper API 호출 후 캐시에 저장.
    """
    cache_path = CACHE_SERP_DIR / f"{keyword_hash(keyword)}.json"
    if cache_path.exists():
        log(STEP, f"캐시 사용: {keyword} → {cache_path.name}")
        return load_json(cache_path)

    api_key = get_env("SERPER_API_KEY")
    if not api_key:
        raise RuntimeError(
            f"'{keyword}' 캐시가 없고 SERPER_API_KEY도 없습니다. "
            ".env에 키를 넣거나 cache/serp/ 에 샘플 파일을 넣어주세요."
        )

    try:
        r = requests.post(
            "https://google.serper.dev/search",
            headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
            json={"q": keyword, "gl": "kr", "hl": "ko", "num": num},
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        log(STEP, f"❌ Serper API 호출 실패({keyword}): {e}")
        raise

    from urllib.parse import urlparse

    organic = data.get("organic", [])[:num]
    results = []
    for i, item in enumerate(organic, start=1):
        url = item.get("link", "")
        results.append(
            {
                "rank": i,
                "url": url,
                "domain": urlparse(url).netloc.replace("www.", ""),
                "title": item.get("title", ""),
                "snippet": item.get("snippet", ""),
            }
        )
    save_json(cache_path, results)
    log(STEP, f"API 호출 성공, 캐시 저장: {cache_path.name}")
    return results
