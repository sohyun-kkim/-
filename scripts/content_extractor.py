"""
③ content-extractor
입력: data/serp_results.json
출력: data/pages.json

각 URL을 정적 fetch(requests)한 뒤 BeautifulSoup로 온페이지 신호 8종 + 본문을 추출한다.
본문이 500자 미만이면 render_required=true 로 표시하고 분석 대상에서 제외한다
(조용히 빈 데이터로 넘어가지 않는다 — 리포트 부록에 '수집 실패'로 명시됨).
오늘은 semantic 폴백을 만들지 않는다 — 실패는 배지로만 표시한다.
"""
import json
import sys
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from common import DATA_DIR, load_json, log, save_json

STEP = "content-extractor"
HEADERS = {"User-Agent": "Mozilla/5.0 (SEO-Gap-Analysis-Demo/1.0)"}
MIN_BODY_LEN = 500


def extract_signals(html: str, url: str, resp_headers: dict):
    soup = BeautifulSoup(html, "html.parser")
    domain = urlparse(url).netloc.replace("www.", "")

    title = soup.title.get_text(strip=True) if soup.title else ""
    h1_tag = soup.find("h1")
    h1 = h1_tag.get_text(strip=True) if h1_tag else ""
    h2_list = [h.get_text(strip=True) for h in soup.find_all("h2")]

    # 본문 텍스트: script/style/nav/footer/header 제외한 가시 텍스트
    for tag in soup(["script", "style", "nav", "footer", "header", "noscript"]):
        tag.decompose()
    body_text = " ".join(soup.get_text(separator=" ").split())
    word_count = len(body_text)

    imgs = soup.find_all("img")
    image_count = len(imgs)
    filled_alt = sum(1 for img in imgs if img.get("alt", "").strip())
    alt_fill_rate = round(filled_alt / image_count, 2) if image_count else 0.0

    internal_link_count = 0
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.startswith("/") or domain in href:
            internal_link_count += 1

    schema_types = []
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "{}")
            items = data if isinstance(data, list) else [data]
            for item in items:
                t = item.get("@type")
                if t:
                    schema_types.append(t if isinstance(t, str) else str(t))
        except Exception:
            continue

    last_modified = resp_headers.get("Last-Modified")
    if not last_modified:
        meta = soup.find("meta", attrs={"property": "article:modified_time"})
        last_modified = meta.get("content") if meta else None

    return {
        "signals": {
            "title": title,
            "h1": h1,
            "h2_list": h2_list,
            "word_count": word_count,
            "image_count": image_count,
            "alt_fill_rate": alt_fill_rate,
            "internal_link_count": internal_link_count,
            "schema_types": list(set(schema_types)),
            "last_modified": last_modified,
        },
        "body_text": body_text[:3000],  # LLM 프롬프트 용량 보호를 위한 절단
    }


def fetch_page(url: str):
    r = requests.get(url, headers=HEADERS, timeout=10)
    r.raise_for_status()
    return r.text, r.headers


def main():
    serp_path = DATA_DIR / "serp_results.json"
    if not serp_path.exists():
        log(STEP, f"❌ {serp_path} 가 없습니다. ②serp-collector를 먼저 실행하세요.")
        sys.exit(1)

    serp_data = load_json(serp_path)
    client_domain = load_json(DATA_DIR / "keywords.json")["client_domain"]

    pages = []
    seen_urls = {}
    fail_count = 0

    for entry in serp_data:
        keyword = entry["keyword"]
        for r in entry["results"]:
            url = r["url"]
            is_own = client_domain in r["domain"]

            if url in seen_urls:
                # 이미 fetch한 URL이면 재사용하고 키워드/랭크만 추가 기록
                page = dict(seen_urls[url])
                page["keyword"] = keyword
                page["rank"] = r["rank"]
                pages.append(page)
                continue

            log(STEP, f"fetch: {url}")
            try:
                html, resp_headers = fetch_page(url)
            except Exception as e:
                log(STEP, f"❌ fetch 실패({url}): {e}")
                page = {
                    "url": url,
                    "is_own": is_own,
                    "rank": r["rank"],
                    "keyword": keyword,
                    "signals": None,
                    "body_text": "",
                    "render_required": True,
                    "matched_by": "serp",
                    "fetch_error": str(e),
                }
                pages.append(page)
                seen_urls[url] = page
                fail_count += 1
                continue

            extracted = extract_signals(html, url, resp_headers)
            render_required = len(extracted["body_text"]) < MIN_BODY_LEN
            if render_required:
                log(
                    STEP,
                    f"⚠️  본문 {len(extracted['body_text'])}자 (<{MIN_BODY_LEN}자) → "
                    f"render_required=true, 분석 제외: {url}",
                )
                fail_count += 1

            page = {
                "url": url,
                "is_own": is_own,
                "rank": r["rank"],
                "keyword": keyword,
                "signals": extracted["signals"],
                "body_text": extracted["body_text"],
                "render_required": render_required,
                "matched_by": "serp",
            }
            pages.append(page)
            seen_urls[url] = page

    out_path = DATA_DIR / "pages.json"
    save_json(out_path, pages)
    ok = len(pages) - fail_count
    log(STEP, f"✅ 완료: {out_path} (총 {len(pages)}건, 수집성공 {ok}건, 실패/렌더필요 {fail_count}건)")


if __name__ == "__main__":
    main()
