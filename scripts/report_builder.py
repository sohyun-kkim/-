"""
⑤ report-builder
입력: data/keywords.json, data/serp_results.json, data/pages.json, data/analysis.json
출력: report.html (외부 CDN 의존 없는 단일 HTML, 더블클릭으로 열림)

레이아웃: 표 하나에 모든 걸 몰아넣지 않고, 키워드별 카드로 나눠 스캔하기 쉽게 구성.
맨 위 "핵심 요약"은 LLM 추정이 아니라 데이터에서 결정적으로 집계한 사실(fact)만 담는다
(경쟁사 도메인 등장 빈도, 자사 노출 여부 등 — seo-gap-analysis 스킬의 fact/estimate 구분 원칙).
"""
import html
import sys
from collections import Counter
from datetime import date
from urllib.parse import urlparse

from common import DATA_DIR, ROOT_DIR, load_json, log

STEP = "report-builder"


def esc(s):
    return html.escape(str(s)) if s is not None else ""


def domain_of(url):
    if not url:
        return ""
    return urlparse(url).netloc.replace("www.", "")


def link(url, text=None, raw_html=False):
    if not url:
        return ""
    if text is None:
        t = esc(url)
    else:
        t = text if raw_html else esc(text)
    return f'<a href="{esc(url)}" target="_blank" rel="noopener" title="{esc(url)}">{t}</a>'


def badge(text, kind="fact"):
    return f'<span class="badge badge-{kind}">{esc(text)}</span>'


def chips(terms):
    """쉼표로 줄줄이 나열하는 대신 스캔하기 쉬운 칩 목록으로."""
    if not terms:
        return "<span class='muted'>-</span>"
    return "".join(f'<span class="chip">{esc(t)}</span>' for t in terms)


def evidence_links(urls):
    """근거를 숫자가 아니라 '어느 경쟁사인지' 도메인 이름으로 바로 보여준다."""
    if not urls:
        return ""
    pills = "".join(
        f'<a href="{esc(u)}" target="_blank" rel="noopener" title="{esc(u)}" class="ev-pill">{esc(domain_of(u))}</a>'
        for u in urls
    )
    return f'<span class="ev">근거 {pills}</span>'


def cell_value(v):
    if isinstance(v, bool):
        return badge("✓ 포함", "ok") if v else badge("✗ 미포함", "bad")
    if v is None:
        return badge("데이터 없음", "muted")
    return esc(v)


def build_competitor_list(entry, client_domain):
    """이 키워드의 SERP 상위 5에 누가 있는지 순위·도메인으로 바로 보여준다."""
    items = []
    for r in entry["results"]:
        if client_domain in r["domain"]:
            continue
        items.append(
            f'<a href="{esc(r["url"])}" target="_blank" rel="noopener" '
            f'title="{esc(r.get("title",""))}" class="comp-pill">'
            f'<span class="comp-rank">{r["rank"]}위</span>{esc(r["domain"])}</a>'
        )
    return "".join(items) if items else "<span class='muted'>SERP 결과 없음</span>"


def build_excluded_note(media_excluded):
    """조용히 버리지 않고 어떤 도메인을 왜 제외했는지 보여준다."""
    if not media_excluded:
        return ""
    label = {"media": "언론/매거진", "ugc": "커뮤니티"}
    pills = "".join(
        f'<a href="{esc(e["url"])}" target="_blank" rel="noopener" title="{esc(e["url"])}" '
        f'class="excl-pill">{e["rank"]}위 {esc(e["domain"])} · {label.get(e["category"], e["category"])}</a>'
        for e in media_excluded
    )
    return f'<div class="excl-note">제외됨 <div class="excl-list">{pills}</div></div>'


def build_axis3_mini(rows):
    """키워드 하나에 대한 온페이지 비교표. 열 제목을 '경쟁사 1위'가 아니라 실제 도메인으로."""
    if not rows:
        return "<p class='muted'>온페이지 비교 데이터 없음.</p>"

    header_domains = [domain_of(c["url"]) for c in rows[0]["competitors"][:3]]
    while len(header_domains) < 3:
        header_domains.append("-")

    trs = []
    for row in rows:
        own_cell = (
            link(row["own_url"], cell_value(row["own"]), raw_html=True)
            if row.get("own_url")
            else cell_value(row["own"])
        )
        comp_cells = []
        for i in range(3):
            if i < len(row["competitors"]):
                c = row["competitors"][i]
                val = cell_value(c.get("value"))
                val = link(c["url"], val, raw_html=True) if c.get("url") else val
                comp_cells.append(f"<td>{val}</td>")
            else:
                comp_cells.append("<td>-</td>")
        trs.append(
            f"<tr><td>{esc(row['item'])}</td><td>{own_cell}</td>{''.join(comp_cells)}</tr>"
        )

    head_cells = "".join(f"<th>{esc(d)}</th>" for d in header_domains)
    return (
        '<table class="tech-table">'
        f"<thead><tr><th>항목</th><th>자사</th>{head_cells}</tr></thead>"
        f"<tbody>{''.join(trs)}</tbody></table>"
    )


def build_keyword_card(idx, entry, axis1, axis3_rows, client_domain):
    kw = entry["keyword"]
    own_url = entry.get("own_page_url")
    own_rank = None
    if own_url:
        for r in entry["results"]:
            if r["url"] == own_url:
                own_rank = r["rank"]
                break
    rank_badge = (
        badge(f"{own_rank}위 노출", "ok") if own_rank else badge("미노출 (상위 5위 밖)", "danger")
    )

    own_terms = axis1.get("own_terms", {}).get(kw, [])
    comp_terms = axis1.get("competitor_terms", {}).get(kw, [])
    gap_terms = axis1.get("gap_terms", {}).get(kw, [])

    own_terms_html = chips(own_terms) if own_url else "<span class='muted'>자사 페이지가 상위 5위 밖 — 비교 불가</span>"
    comp_terms_html = chips(comp_terms)

    gap_items = []
    for g in gap_terms:
        cls = "fact" if g.get("type", "fact") == "fact" else "estimate"
        gap_items.append(
            f'<li><span class="tag tag-{cls}">{esc(g.get("type","fact"))}</span>'
            f'<span class="gap-term">{esc(g.get("term",""))}</span>'
            f"{evidence_links(g.get('evidence', []))}</li>"
        )
    gap_html = (
        f'<ul class="gap-list">{"".join(gap_items)}</ul>'
        if gap_items
        else "<p class='muted'>발견된 갭 없음.</p>"
    )

    return f"""
    <div class="kw-card">
      <div class="kw-card-header">
        <h3><span class="kw-idx">{idx}</span>{esc(kw)}</h3>
        {rank_badge}
      </div>

      <div class="kw-card-block">
        <div class="block-label">경쟁사 (SERP 상위 5, 언론/매거진·커뮤니티 제외)</div>
        <div class="comp-list">{build_competitor_list(entry, client_domain)}</div>
        {build_excluded_note(entry.get("media_excluded", []))}
      </div>

      <div class="kw-card-grid">
        <div>
          <div class="block-label">자사가 쓰는 표현</div>
          <div class="chip-block">{own_terms_html}</div>
        </div>
        <div>
          <div class="block-label">경쟁사가 쓰는 표현</div>
          <div class="chip-block">{comp_terms_html}</div>
        </div>
      </div>

      <div class="kw-card-block">
        <div class="block-label">자사와의 갭 (근거: 경쟁사 도메인 클릭 시 해당 페이지로 이동)</div>
        {gap_html}
      </div>

      <div class="kw-card-block">
        <div class="block-label">온페이지 기술요소 비교</div>
        {build_axis3_mini(axis3_rows)}
      </div>
    </div>"""


def build_summary(serp_data, client_domain):
    """LLM 추정이 아니라 SERP/노출 데이터에서 결정적으로 집계한 요약 — 전부 fact."""
    total = len(serp_data)
    not_ranked = [e["keyword"] for e in serp_data if not e.get("own_page_url")]
    ranked = total - len(not_ranked)

    domain_counts = Counter()
    for entry in serp_data:
        seen_this_kw = set()
        for r in entry["results"]:
            d = r["domain"]
            if client_domain not in d and d not in seen_this_kw:
                domain_counts[d] += 1
                seen_this_kw.add(d)
    top_domains = domain_counts.most_common(5)

    bullets = [
        (
            "fact",
            f"분석한 키워드 {total}개 중 자사 페이지가 상위 5위 안에 노출된 건 {ranked}개"
            + (f" — 미노출: {', '.join(not_ranked)}" if not_ranked else ""),
        )
    ]
    if top_domains:
        dom_str = ", ".join(f"{esc(d)}({c}/{total}개 키워드)" for d, c in top_domains)
        bullets.append(("fact", f"SERP 상위권에 반복 등장하는 경쟁 도메인: {dom_str}"))
    if not_ranked:
        bullets.append(
            (
                "estimate",
                "미노출 키워드는 온페이지 기술요소 비교 자체가 불가능함 — 경쟁사 대응보다 "
                "콘텐츠 신설이 선행 과제로 보임",
            )
        )
    return bullets


def build_appendix(pages):
    failed = [p for p in pages if p.get("render_required")]
    if not failed:
        return "<p class='muted'>수집 실패 페이지 없음.</p>"
    items = []
    for p in failed:
        reason = p.get("fetch_error", "본문 500자 미만 (동적 렌더링 필요 추정)")
        items.append(f"<li>{link(p['url'])} — {esc(reason)}</li>")
    return f"<ul>{''.join(items)}</ul>"


def main():
    required = ["keywords.json", "serp_results.json", "pages.json", "analysis.json"]
    for fname in required:
        if not (DATA_DIR / fname).exists():
            log(STEP, f"❌ {fname} 가 없습니다. 이전 단계를 먼저 실행하세요.")
            sys.exit(1)

    kdata = load_json(DATA_DIR / "keywords.json")
    serp_data = load_json(DATA_DIR / "serp_results.json")
    pages = load_json(DATA_DIR / "pages.json")
    analysis = load_json(DATA_DIR / "analysis.json")

    client_domain = kdata["client_domain"]
    brand = client_domain.split(".")[0]
    competitor_domains = set()
    for entry in serp_data:
        for r in entry["results"]:
            if client_domain not in r["domain"]:
                competitor_domains.add(r["domain"])

    axis3_by_kw = {}
    for row in analysis["axis3_technical"]["comparison_table"]:
        axis3_by_kw.setdefault(row["keyword"], []).append(row)

    summary_bullets = build_summary(serp_data, client_domain)
    summary_html = "".join(
        f'<li><span class="tag tag-{t}">{t}</span> {msg}</li>' for t, msg in summary_bullets
    )

    cards_html = "".join(
        build_keyword_card(i, entry, analysis["axis1_keywords"], axis3_by_kw.get(entry["keyword"], []), client_domain)
        for i, entry in enumerate(serp_data, 1)
    )

    appendix = build_appendix(pages)
    today = date.today().isoformat()

    html_doc = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<title>SEO 콘텐츠 갭 분석 리포트 — {esc(brand)}</title>
<style>
  :root {{
    --bg: #f4f5f7; --panel: #ffffff; --border: #e1e4ea; --text: #1c2130;
    --muted: #6b7280; --accent: #2f6fed; --accent-bg: #eaf0ff;
    --ok: #17824e; --ok-bg: #e6f7ee; --bad: #b3261e; --bad-bg: #fbeceb;
    --danger-bg: #fdecec; --danger-fg: #b3261e;
    --fact: #2f6fed; --fact-bg: #eaf0ff; --estimate: #92600a; --estimate-bg: #fbf1de;
    --chip-bg: #f1f3f7;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    background: var(--bg); color: var(--text);
    font-family: -apple-system, "Malgun Gothic", "Apple SD Gothic Neo", sans-serif;
    margin: 0 auto; max-width: 980px; padding: 28px 20px 60px; line-height: 1.6; font-size: 15px;
  }}
  header {{
    background: var(--panel); border: 1px solid var(--border); border-radius: 12px;
    padding: 22px 26px; margin-bottom: 18px; box-shadow: 0 1px 2px rgba(20,25,40,0.04);
  }}
  header h1 {{ margin: 0 0 6px 0; font-size: 21px; }}
  header .meta {{ color: var(--muted); font-size: 13px; }}
  .stats {{ margin-top: 12px; display: flex; gap: 10px; flex-wrap: wrap; }}
  .stat {{ background: var(--chip-bg); border-radius: 8px; padding: 6px 12px; font-size: 13px; }}

  section {{
    background: var(--panel); border: 1px solid var(--border); border-radius: 12px;
    padding: 20px 26px; margin-bottom: 18px; box-shadow: 0 1px 2px rgba(20,25,40,0.04);
  }}
  section > h2 {{ margin-top: 0; font-size: 16px; border-left: 4px solid var(--accent); padding-left: 10px; }}

  .summary-list {{ margin: 10px 0 0; padding: 0; list-style: none; }}
  .summary-list li {{
    display: flex; gap: 8px; align-items: baseline; padding: 9px 0;
    border-top: 1px solid var(--border); font-size: 14px;
  }}
  .summary-list li:first-child {{ border-top: none; }}

  .kw-card {{
    border: 1px solid var(--border); border-radius: 10px; padding: 18px 20px;
    margin-top: 14px;
  }}
  .kw-card:first-child {{ margin-top: 0; }}
  .kw-card-header {{ display: flex; align-items: center; gap: 10px; margin-bottom: 12px; }}
  .kw-card-header h3 {{ margin: 0; font-size: 15px; display: flex; align-items: center; gap: 8px; }}
  .kw-idx {{
    display: inline-flex; align-items: center; justify-content: center;
    width: 20px; height: 20px; border-radius: 50%; background: var(--accent-bg);
    color: var(--accent); font-size: 12px; font-weight: 700;
  }}
  .kw-card-block {{ margin-top: 14px; }}
  .kw-card-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-top: 14px; }}
  @media (max-width: 640px) {{ .kw-card-grid {{ grid-template-columns: 1fr; }} }}

  .block-label {{
    font-size: 11.5px; color: var(--muted); text-transform: uppercase;
    letter-spacing: .04em; margin-bottom: 6px; font-weight: 600;
  }}

  .comp-list {{ display: flex; flex-wrap: wrap; gap: 6px; }}
  .comp-pill {{
    display: inline-flex; align-items: center; gap: 6px; background: var(--chip-bg);
    border: 1px solid var(--border); border-radius: 8px; padding: 4px 10px 4px 6px;
    font-size: 12.5px; color: var(--text); text-decoration: none;
  }}
  .comp-pill:hover {{ border-color: var(--accent); }}
  .comp-rank {{
    background: var(--accent); color: #fff; border-radius: 5px; padding: 1px 6px;
    font-size: 11px; font-weight: 700;
  }}
  .excl-note {{ margin-top: 8px; font-size: 11.5px; color: var(--muted); }}
  .excl-list {{ display: flex; flex-wrap: wrap; gap: 5px; margin-top: 4px; }}
  .excl-pill {{
    display: inline-block; padding: 2px 8px; border-radius: 8px; background: #f3f1ec;
    color: var(--muted) !important; font-size: 11px; text-decoration: none !important;
    border: 1px dashed var(--border);
  }}
  .excl-pill:hover {{ border-color: var(--muted); }}

  table {{ width: 100%; border-collapse: collapse; font-size: 13.5px; margin-top: 6px; }}
  th, td {{ border: 1px solid var(--border); padding: 9px 11px; text-align: left; vertical-align: top; }}
  th {{ background: #f8f9fb; color: var(--muted); font-weight: 600; font-size: 12.5px; }}
  tbody tr:nth-child(odd) {{ background: #fbfbfc; }}

  a {{ color: var(--accent); text-decoration: none; }}
  a:hover {{ text-decoration: underline; }}

  .badge {{ display: inline-block; padding: 3px 10px; border-radius: 12px; font-size: 12px; font-weight: 700; }}
  .badge-ok {{ background: var(--ok-bg); color: var(--ok); }}
  .badge-bad {{ background: var(--bad-bg); color: var(--bad); }}
  .badge-danger {{ background: var(--danger-bg); color: var(--danger-fg); }}
  .badge-muted {{ background: var(--chip-bg); color: var(--muted); }}

  .tag {{
    display: inline-block; padding: 2px 7px; border-radius: 4px; font-size: 10.5px;
    font-weight: 700; text-transform: uppercase; flex-shrink: 0;
  }}
  .tag-fact {{ background: var(--fact-bg); color: var(--fact); }}
  .tag-estimate {{ background: var(--estimate-bg); color: var(--estimate); }}

  .chip-block {{ display: flex; flex-wrap: wrap; gap: 6px; }}
  .chip {{
    display: inline-block; background: var(--chip-bg); border: 1px solid var(--border);
    color: var(--text); padding: 3px 10px; border-radius: 12px; font-size: 12.5px;
  }}

  .gap-list {{ margin: 0; padding: 0; list-style: none; font-size: 13.5px; }}
  .gap-list li {{
    display: flex; align-items: baseline; gap: 8px; padding: 8px 0;
    border-top: 1px solid var(--border); flex-wrap: wrap;
  }}
  .gap-list li:first-child {{ border-top: none; }}
  .gap-term {{ flex: 1 1 auto; min-width: 160px; }}
  .ev {{ color: var(--muted); font-size: 11.5px; display: flex; gap: 4px; flex-wrap: wrap; align-items: center; }}
  .ev-pill {{
    display: inline-block; padding: 1px 8px; border-radius: 9px; background: var(--chip-bg);
    color: var(--muted) !important; font-size: 11px; text-decoration: none !important;
    border: 1px solid var(--border);
  }}
  .ev-pill:hover {{ background: var(--accent); color: #fff !important; border-color: var(--accent); }}

  .legend {{ font-size: 12px; color: var(--muted); margin-top: 10px; }}
  .muted {{ color: var(--muted); }}
  footer {{ text-align: center; color: var(--muted); font-size: 12px; margin-top: 26px; }}
</style>
</head>
<body>

<header>
  <h1>SEO 콘텐츠 갭 분석 리포트 — {esc(brand)}</h1>
  <div class="meta">생성일: {esc(today)} · 대상: {link(kdata['client_url'])}</div>
  <div class="stats">
    <div class="stat">분석 키워드 {len(serp_data)}개</div>
    <div class="stat">경쟁사 도메인 {len(competitor_domains)}개</div>
    <div class="stat">수집 페이지 {len(pages)}건</div>
  </div>
</header>

<section>
  <h2>핵심 요약</h2>
  <ul class="summary-list">
    {summary_html}
  </ul>
</section>

<section>
  <h2>키워드별 상세 분석</h2>
  {cards_html}
  <div class="legend">
    <span class="tag tag-fact">fact</span> 관찰된 사실(원본 데이터 그대로) ·
    <span class="tag tag-estimate">estimate</span> 관찰값 기반 제안(일반 SEO 통념) ·
    근거 옆 도메인 pill을 클릭하면 해당 경쟁사 페이지로 이동합니다.
  </div>
</section>

<section>
  <h2>부록 — 수집 실패(render_required) 페이지</h2>
  {appendix}
</section>

<footer>SEO 콘텐츠 갭 분석 데모 · 관찰 신호 8종 기반 (축1·축3) · 축2/축4/시맨틱 폴백은 로드맵 참고</footer>

</body>
</html>
"""

    out_path = ROOT_DIR / "report.html"
    out_path.write_text(html_doc, encoding="utf-8")
    log(STEP, f"✅ 완료: {out_path}")
    print(f"\n리포트가 생성되었습니다: {out_path}")
    print("파일 탐색기에서 report.html을 더블클릭해 열어보세요.")


if __name__ == "__main__":
    main()
