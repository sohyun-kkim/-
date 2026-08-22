"""
④ gap-analyzer
입력: data/pages.json, data/keywords.json
출력: data/analysis.json

seo-gap-analysis 스킬 규칙에 따라 축1(키워드 사용법)·축3(온페이지 기술요소)만 분석한다.
- 축3은 순수 관찰값 비교이므로 파이썬으로 결정적으로 계산한다(추측 개입 차단).
- 축1은 title/h1/h2 텍스트에서 "같은 개념을 부르는 다른 단어"를 찾아야 하므로 LLM을 쓰되,
  SKILL.md의 규칙(8종 화이트리스트, evidence 강제, fact/estimate 구분)을 시스템 프롬프트에
  그대로 주입해 관찰된 텍스트 밖으로 벗어나지 못하게 한다.
"""
import json
import re
import sys
from pathlib import Path

from common import DATA_DIR, ROOT_DIR, call_llm, load_json, log, save_json

STEP = "gap-analyzer"
SKILL_PATH = ROOT_DIR / ".claude" / "skills" / "seo-gap-analysis" / "SKILL.md"


def keyword_in(text: str, keyword: str) -> bool:
    if not text:
        return False
    return keyword.strip().lower() in text.lower()


def build_axis3(pages_by_keyword):
    """축3: 온페이지 기술요소 비교표를 관찰값 그대로 계산한다 (LLM 미사용)."""
    rows = []
    all_evidence = set()

    for keyword, pages in pages_by_keyword.items():
        valid = [p for p in pages if not p.get("render_required") and p.get("signals")]
        own = next((p for p in valid if p["is_own"]), None)
        competitors = sorted(
            (p for p in valid if not p["is_own"]), key=lambda p: p["rank"]
        )[:3]

        def cell(page, item):
            if not page:
                return None
            s = page["signals"]
            if item == "title_keyword":
                return keyword_in(s["title"], keyword)
            if item == "h1_keyword":
                return keyword_in(s["h1"], keyword)
            if item == "json_ld_schema":
                return ", ".join(s["schema_types"]) if s["schema_types"] else "없음"
            if item == "alt_fill_rate":
                return s["alt_fill_rate"]
            if item == "word_count":
                return s["word_count"]
            if item == "image_count":
                return s["image_count"]
            if item == "internal_link_count":
                return s["internal_link_count"]
            return None

        items = [
            ("title_keyword", "title에 키워드 포함"),
            ("h1_keyword", "h1에 키워드 포함"),
            ("json_ld_schema", "JSON-LD 스키마"),
            ("alt_fill_rate", "alt 채움률"),
            ("word_count", "본문 글자수"),
            ("image_count", "이미지 수"),
            ("internal_link_count", "내부링크 수"),
        ]

        for item_key, item_label in items:
            evidence_urls = [p["url"] for p in ([own] if own else []) + competitors]
            row = {
                "keyword": keyword,
                "item": item_label,
                "own": cell(own, item_key),
                "own_url": own["url"] if own else None,
                "competitors": [
                    {"rank": c["rank"], "url": c["url"], "value": cell(c, item_key)}
                    for c in competitors
                ],
                "type": "fact",
                "evidence": evidence_urls,
            }
            rows.append(row)
            all_evidence.update(evidence_urls)

        if own is None:
            rows.append(
                {
                    "keyword": keyword,
                    "item": "자사 노출 여부",
                    "own": "미노출 (상위 5위 밖)",
                    "own_url": None,
                    "competitors": [{"rank": c["rank"], "url": c["url"]} for c in competitors],
                    "type": "fact",
                    "evidence": [c["url"] for c in competitors],
                }
            )

    return {"comparison_table": rows, "evidence": sorted(all_evidence)}


def build_axis1(pages_by_keyword, client_domain):
    """축1: title/h1/h2 텍스트 기반 키워드 사용법 비교. LLM + SKILL 규칙 주입."""
    skill_text = SKILL_PATH.read_text(encoding="utf-8")

    system = (
        "너는 SEO 콘텐츠 분석가다. 아래는 반드시 지켜야 할 스킬 규칙이다.\n\n"
        f"{skill_text}\n\n"
        "이제 축1(키워드 사용법 비교)만 수행한다. 자사 페이지와 경쟁사 페이지의 title/h1/h2 "
        "텍스트만 보고, '같은 개념을 어떤 단어로 부르는지' 비교하라. 8종 신호 화이트리스트와 "
        "evidence 강제 규칙을 반드시 지켜라. 관찰되지 않은 것을 지어내지 마라. "
        "출력은 반드시 아래 JSON 형식만: "
        '{"own_terms": ["..."], "competitor_terms": ["..."], '
        '"gap_terms": [{"term": "...", "evidence": ["url1", "url2"], "type": "fact"}]} '
        "다른 설명 텍스트는 붙이지 마라."
    )

    own_terms_all, competitor_terms_all, gap_terms_all = {}, {}, {}
    all_evidence = set()

    for keyword, pages in pages_by_keyword.items():
        valid = [p for p in pages if not p.get("render_required") and p.get("signals")]
        own = next((p for p in valid if p["is_own"]), None)
        competitors = sorted((p for p in valid if not p["is_own"]), key=lambda p: p["rank"])[:5]

        if not competitors:
            log(STEP, f"⚠️  '{keyword}': 비교할 경쟁사 페이지가 없어 축1을 건너뜁니다.")
            continue

        own_block = "없음 (자사는 상위 5위 밖, 미노출)"
        if own:
            s = own["signals"]
            own_block = f"title: {s['title']} / h1: {s['h1']} / h2: {s['h2_list']} (URL: {own['url']})"

        comp_blocks = []
        for c in competitors:
            s = c["signals"]
            comp_blocks.append(
                f"- title: {s['title']} / h1: {s['h1']} / h2: {s['h2_list']} (URL: {c['url']})"
            )

        user = (
            f"키워드: {keyword}\n\n자사 페이지:\n{own_block}\n\n경쟁사 페이지:\n"
            + "\n".join(comp_blocks)
        )

        try:
            raw = call_llm(system, user, STEP, max_tokens=3000)
        except Exception as e:
            log(STEP, f"❌ '{keyword}' 축1 LLM 호출 실패, 이 키워드는 건너뜁니다: {e}")
            continue

        match = re.search(r"\{.*\}", raw, re.S)
        if not match:
            log(STEP, f"❌ '{keyword}' LLM 응답 파싱 실패: {raw[:200]}")
            continue
        try:
            parsed = json.loads(match.group(0))
        except Exception as e:
            log(STEP, f"❌ '{keyword}' JSON 파싱 실패: {e}")
            continue

        own_terms_all[keyword] = parsed.get("own_terms", [])
        competitor_terms_all[keyword] = parsed.get("competitor_terms", [])
        gap_terms_all[keyword] = parsed.get("gap_terms", [])
        for g in parsed.get("gap_terms", []):
            all_evidence.update(g.get("evidence", []))

        if own is None:
            gap_terms_all[keyword].insert(
                0,
                {
                    "term": "미노출 — 자사 페이지가 상위 5위 안에 없음",
                    "evidence": [c["url"] for c in competitors],
                    "type": "fact",
                },
            )

    return {
        "own_terms": own_terms_all,
        "competitor_terms": competitor_terms_all,
        "gap_terms": gap_terms_all,
        "evidence": sorted(all_evidence),
    }


def main():
    pages_path = DATA_DIR / "pages.json"
    keywords_path = DATA_DIR / "keywords.json"
    if not pages_path.exists():
        log(STEP, f"❌ {pages_path} 가 없습니다. ③content-extractor를 먼저 실행하세요.")
        sys.exit(1)

    pages = load_json(pages_path)
    client_domain = load_json(keywords_path)["client_domain"]

    pages_by_keyword = {}
    for p in pages:
        pages_by_keyword.setdefault(p["keyword"], []).append(p)

    log(STEP, f"분석 대상 키워드: {list(pages_by_keyword.keys())}")

    axis3 = build_axis3(pages_by_keyword)
    log(STEP, f"축3(온페이지 기술요소) 계산 완료: {len(axis3['comparison_table'])}행")

    axis1 = build_axis1(pages_by_keyword, client_domain)
    log(STEP, f"축1(키워드 사용법) LLM 분석 완료")

    result = {"axis1_keywords": axis1, "axis3_technical": axis3}
    out_path = DATA_DIR / "analysis.json"
    save_json(out_path, result)
    log(STEP, f"✅ 완료: {out_path}")


if __name__ == "__main__":
    main()
