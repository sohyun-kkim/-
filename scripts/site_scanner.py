"""
① site-scanner
입력: client_url (CLI 인자)
출력: data/keywords.json

로직:
1) {url}/sitemap.xml 을 시도해 URL 목록에서 카테고리(경로 세그먼트)를 추출한다.
2) 실패하면 메인 페이지의 <nav>/헤더 링크 텍스트에서 카테고리를 추출한다.
3) 둘 다 실패하면 사용자에게 카테고리/키워드를 직접 입력하라고 요청한다(예외 발생).
4) 감지된 카테고리를 근거로 LLM에게 검색자가 쓸 법한 키워드 후보 5~8개를 요청한다.
   브랜드명이 포함된 키워드는 제외한다(이미 1위라 분석 가치 없음).
"""
import re
import sys
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from common import DATA_DIR, call_llm, log, save_json

STEP = "site-scanner"
HEADERS = {"User-Agent": "Mozilla/5.0 (SEO-Gap-Analysis-Demo/1.0)"}


def normalize_url(url: str) -> str:
    if not url.startswith("http"):
        url = "https://" + url
    return url.rstrip("/")


def get_domain(url: str) -> str:
    return urlparse(url).netloc.replace("www.", "")


def try_sitemap(base_url: str):
    for path in ("/sitemap.xml", "/sitemap_index.xml"):
        try:
            r = requests.get(base_url + path, headers=HEADERS, timeout=8)
            if r.status_code != 200 or "<" not in r.text:
                continue
            soup = BeautifulSoup(r.text, "xml")
            locs = [loc.text.strip() for loc in soup.find_all("loc")]
            if not locs:
                continue
            log(STEP, f"sitemap 발견: {base_url}{path} ({len(locs)}개 URL)")
            return locs
        except Exception as e:
            log(STEP, f"sitemap 시도 실패({path}): {e}")
    return None


def categories_from_urls(urls):
    cats = {}
    for u in urls:
        segs = [s for s in urlparse(u).path.split("/") if s]
        if not segs:
            continue
        seg = segs[0]
        if re.search(r"\d{4}|\.xml|\.html?$|^page", seg):
            continue
        cats[seg] = cats.get(seg, 0) + 1
    ranked = sorted(cats.items(), key=lambda x: -x[1])
    return [c for c, _ in ranked[:10]]


def try_nav(base_url: str):
    try:
        r = requests.get(base_url, headers=HEADERS, timeout=8)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        nav = soup.find("nav") or soup.find(attrs={"role": "navigation"})
        if not nav:
            # 헤더 내부의 링크들로 대체
            nav = soup.find("header")
        if not nav:
            return None
        texts = []
        for a in nav.find_all("a"):
            t = a.get_text(strip=True)
            if t and 1 < len(t) <= 20:
                texts.append(t)
        texts = list(dict.fromkeys(texts))  # 중복 제거, 순서 유지
        if not texts:
            return None
        log(STEP, f"네비게이션에서 카테고리 후보 {len(texts)}개 발견")
        return texts[:10]
    except Exception as e:
        log(STEP, f"네비게이션 파싱 실패: {e}")
        return None


def get_brand_name(base_url: str, domain: str) -> str:
    try:
        r = requests.get(base_url, headers=HEADERS, timeout=8)
        soup = BeautifulSoup(r.text, "html.parser")
        title = soup.title.get_text(strip=True) if soup.title else ""
        return title or domain.split(".")[0]
    except Exception:
        return domain.split(".")[0]


def generate_keywords(categories, brand_name, domain):
    system = (
        "너는 SEO 컨설턴트다. 아래 카테고리 목록을 보고, 실제 검색자가 네이버/구글에 입력할 법한 "
        "키워드 후보 5~8개를 만들어라. 규칙: "
        f"1) 브랜드명('{brand_name}')이나 도메인명이 포함된 키워드는 절대 만들지 마라(이미 1위라 분석 무의미). "
        "2) 각 키워드는 카테고리 중 하나와 연결되어야 한다. "
        "3) 출력은 반드시 JSON 배열만: [{\"keyword\": \"...\", \"source_category\": \"...\"}, ...] "
        "다른 설명 텍스트는 절대 붙이지 마라."
    )
    user = f"카테고리 목록: {categories}"
    raw = call_llm(system, user, STEP, max_tokens=800)
    match = re.search(r"\[.*\]", raw, re.S)
    if not match:
        raise RuntimeError(f"LLM 응답에서 JSON 배열을 찾지 못했습니다: {raw[:200]}")
    import json

    items = json.loads(match.group(0))
    return items


def main():
    if len(sys.argv) < 2:
        print("사용법: python3 site_scanner.py <client_url>")
        sys.exit(1)
    client_url = normalize_url(sys.argv[1])
    domain = get_domain(client_url)
    log(STEP, f"시작: {client_url} (도메인: {domain})")

    urls = try_sitemap(client_url)
    categories = categories_from_urls(urls) if urls else None

    if not categories:
        log(STEP, "sitemap에서 카테고리를 못 찾음. 네비게이션 메뉴 파싱 시도.")
        categories = try_nav(client_url)

    if not categories:
        log(STEP, "❌ sitemap과 네비게이션 모두 실패했습니다.")
        print(
            "\n카테고리 자동 감지에 실패했습니다. 이 사이트가 다루는 주요 카테고리를 "
            "쉼표로 구분해 직접 입력해주세요 (예: 스킨케어,색조,헤어케어): ",
            end="",
        )
        raise SystemExit(
            "사용자 입력이 필요합니다 — 카테고리를 알려주시면 이어서 진행하겠습니다."
        )

    log(STEP, f"감지된 카테고리: {categories}")
    brand_name = get_brand_name(client_url, domain)
    log(STEP, f"브랜드명 추정: {brand_name} (키워드 생성 시 제외)")

    candidates = generate_keywords(categories, brand_name, domain)
    keyword_candidates = [
        {
            "keyword": c["keyword"],
            "source_category": c.get("source_category", ""),
            "selected": True,
        }
        for c in candidates
    ]

    result = {
        "client_url": client_url,
        "client_domain": domain,
        "detected_categories": categories,
        "keyword_candidates": keyword_candidates,
    }
    out_path = DATA_DIR / "keywords.json"
    save_json(out_path, result)
    log(STEP, f"✅ 완료: {out_path} ({len(keyword_candidates)}개 키워드 후보)")
    print(f"\n생성된 키워드 후보:")
    for kc in keyword_candidates:
        print(f"  - {kc['keyword']}  (카테고리: {kc['source_category']})")


if __name__ == "__main__":
    main()
