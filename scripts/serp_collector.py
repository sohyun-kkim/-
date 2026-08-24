"""
② serp-collector
입력: data/keywords.json (승인 게이트를 통과한 것)
출력: data/serp_results.json

확정된(selected=true) 키워드 중 최대 3개에 대해 SerpApi로 조회한다.
언론/매거진·커뮤니티(UGC) 도메인은 '실제 판매 경쟁사'가 아니므로 걸러내고,
걸러낸 뒤에도 상위 TOP_N개가 남도록 FETCH_POOL개를 넉넉히 받아온 뒤 상위
TOP_N개만 최종 결과로 남긴다. 제외된 도메인은 조용히 버리지 않고
media_excluded에 남겨 리포트에서 확인할 수 있게 한다.
serp_client.fetch_serp()가 cache/serp/{키워드해시}.json을 먼저 조회하므로
캐시가 있으면 API를 호출하지 않는다.
"""
import sys

from common import DATA_DIR, load_json, log, save_json
from noncompetitor_domains import classify_domain
from serp_client import fetch_serp

STEP = "serp-collector"
FETCH_POOL = 15  # 필터링 후에도 TOP_N이 남도록 넉넉히 받아오는 개수
TOP_N = 5


def main():
    keywords_path = DATA_DIR / "keywords.json"
    if not keywords_path.exists():
        log(STEP, f"❌ {keywords_path} 가 없습니다. ①site-scanner를 먼저 실행하세요.")
        sys.exit(1)

    kdata = load_json(keywords_path)
    client_domain = kdata["client_domain"]
    selected = [k["keyword"] for k in kdata["keyword_candidates"] if k.get("selected")]
    selected = selected[:3]

    if not selected:
        log(STEP, "❌ 승인된(selected=true) 키워드가 없습니다. 승인 게이트를 확인하세요.")
        sys.exit(1)

    log(STEP, f"확정 키워드({len(selected)}개): {selected}")

    all_results = []
    for kw in selected:
        try:
            raw = fetch_serp(kw, num=FETCH_POOL)
        except Exception as e:
            log(STEP, f"❌ '{kw}' SERP 수집 실패, 이 키워드는 건너뜁니다: {e}")
            continue

        own_page_url = None
        for r in raw:
            if client_domain in r["domain"]:
                own_page_url = r["url"]
                break

        media_excluded = []
        competitors = []
        for r in raw:
            if client_domain in r["domain"]:
                continue
            category = classify_domain(r["domain"])
            if category:
                media_excluded.append({**r, "category": category})
            else:
                competitors.append(r)

        results = competitors[:TOP_N]
        if media_excluded:
            log(
                STEP,
                f"'{kw}': 언론/매거진·커뮤니티 {len(media_excluded)}건 제외 → "
                + ", ".join(f"{e['domain']}({e['category']})" for e in media_excluded),
            )

        own_visibility = "ranked" if own_page_url else "not_ranked"
        if own_visibility == "not_ranked":
            log(STEP, f"⚠️  '{kw}': 자사 도메인이 상위 {TOP_N}에 없음 (미노출)")
        else:
            log(STEP, f"'{kw}': 자사 페이지 상위 노출 확인 → {own_page_url}")

        all_results.append(
            {
                "keyword": kw,
                "results": results,
                "media_excluded": media_excluded,
                "own_visibility": own_visibility,
                "own_page_url": own_page_url,
            }
        )

    if not all_results:
        log(STEP, "❌ 모든 키워드에서 SERP 수집에 실패했습니다.")
        sys.exit(1)

    out_path = DATA_DIR / "serp_results.json"
    save_json(out_path, all_results)
    log(STEP, f"✅ 완료: {out_path} ({len(all_results)}개 키워드)")


if __name__ == "__main__":
    main()
