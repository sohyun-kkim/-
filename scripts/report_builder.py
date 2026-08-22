"""
⑤ report-builder
입력: data/keywords.json, data/serp_results.json, data/pages.json, data/analysis.json
출력: report.html (외부 CDN 의존 없는 단일 HTML, 더블클릭으로 열림)
"""
import html
import sys
from datetime import date

from common import DATA_DIR, ROOT_DIR, load_json, log

STEP = "report-builder"


def esc(s):
    return html.escape(str(s)) if s is not None else ""


def link(url, text=None, raw_html=False):
    if not url:
        return ""
    if text is None:
        t = esc(url)
    else:
        t = text if raw_html else esc(text)
    return f'<a href="{esc(url)}" target="_blank" rel="noopener">{t}</a>'


def badge(text, kind="fact"):
    return f'<span class="badge badge-{kind}">{esc(text)}</span>'


def cell_value(v):
    if isinstance(v, bool):
        return badge("✓ 포함", "ok") if v else badge("✗ 미포함", "bad")
    if v is None:
        return badge("데이터 없음", "muted")
    return esc(v)


def build_keyword_table(serp_data, axis1, client_domain):
    rows = []
    for entry in serp_data:
        kw = entry["keyword"]
        own_url = entry.get("own_page_url")
        own_rank = None
        if own_url:
            for r in entry["results"]:
                if r["url"] == own_url:
                    own_rank = r["rank"]
                    break

        own_terms = axis1.get("own_terms", {}).get(kw, [])
        comp_terms = axis1.get("competitor_terms", {}).get(kw, [])
        gap_terms = axis1.get("gap_terms", {}).get(kw, [])

        rank_cell = (
            badge(f"{own_rank}위", "ok")
            if own_rank
            else badge("미노출", "danger")
        )
        own_terms_cell = ", ".join(esc(t) for t in own_terms) if own_terms else "-"
        comp_terms_cell = ", ".join(esc(t) for t in comp_terms) if comp_terms else "-"

        gap_html = ""
        if gap_terms:
            items = []
            for g in gap_terms:
                ev = " ".join(link(u, "근거") for u in g.get("evidence", []))
                cls = "fact" if g.get("type", "fact") == "fact" else "estimate"
                items.append(
                    f'<li><span class="tag tag-{cls}">{esc(g.get("type","fact"))}</span> '
                    f'{esc(g.get("term",""))} {ev}</li>'
                )
            gap_html = f'<ul class="gap-list">{"".join(items)}</ul>'

        rows.append(
            f"""
            <tr>
              <td>{esc(kw)}</td>
              <td>{rank_cell}</td>
              <td>{own_terms_cell}</td>
              <td>{comp_terms_cell}{gap_html}</td>
            </tr>"""
        )
    return "\n".join(rows)


def build_axis3_table(axis3):
    rows_by_kw = {}
    for row in axis3["comparison_table"]:
        rows_by_kw.setdefault(row["keyword"], []).append(row)

    blocks = []
    for kw, rows in rows_by_kw.items():
        trs = []
        for row in rows:
            own_link = (
                link(row["own_url"], cell_value(row["own"]), raw_html=True)
                if row.get("own_url")
                else cell_value(row["own"])
            )
            comp_cells = []
            for i in range(3):
                if i < len(row["competitors"]):
                    c = row["competitors"][i]
                    val = cell_value(c.get("value"))
                    comp_cells.append(f'<td>{link(c["url"], "링크")} {val}</td>')
                else:
                    comp_cells.append("<td>-</td>")
            trs.append(
                f"""
                <tr>
                  <td>{esc(row['item'])}</td>
                  <td>{own_link}</td>
                  {''.join(comp_cells)}
                </tr>"""
            )
        blocks.append(
            f"""
            <h3 class="kw-heading">키워드: {esc(kw)}</h3>
            <table class="tech-table">
              <thead><tr><th>항목</th><th>자사</th><th>경쟁사 1위</th><th>경쟁사 2위</th><th>경쟁사 3위</th></tr></thead>
              <tbody>{''.join(trs)}</tbody>
            </table>"""
        )
    return "\n".join(blocks)


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

    keyword_table = build_keyword_table(serp_data, analysis["axis1_keywords"], client_domain)
    axis3_table = build_axis3_table(analysis["axis3_technical"])
    appendix = build_appendix(pages)

    today = date.today().isoformat()

    html_doc = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<title>SEO 콘텐츠 갭 분석 리포트 — {esc(brand)}</title>
<style>
  :root {{
    --bg: #0f1420; --panel: #171d2b; --border: #2a3245; --text: #e6e9f0;
    --muted: #8891a5; --accent: #4f8cff; --ok: #2fbf71; --bad: #d64545;
    --danger-bg: #4a1620; --danger-fg: #ff8080; --fact: #4f8cff; --estimate: #d99a2b;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    background: var(--bg); color: var(--text); font-family: -apple-system, "Malgun Gothic", "Apple SD Gothic Neo", sans-serif;
    margin: 0; padding: 24px; line-height: 1.5;
  }}
  header {{
    background: var(--panel); border: 1px solid var(--border); border-radius: 10px;
    padding: 20px 24px; margin-bottom: 20px;
  }}
  header h1 {{ margin: 0 0 6px 0; font-size: 22px; }}
  header .meta {{ color: var(--muted); font-size: 13px; }}
  .stats {{ margin-top: 10px; display: flex; gap: 16px; flex-wrap: wrap; }}
  .stat {{ background: #1e2536; border-radius: 6px; padding: 6px 12px; font-size: 13px; }}
  section {{
    background: var(--panel); border: 1px solid var(--border); border-radius: 10px;
    padding: 20px 24px; margin-bottom: 20px;
  }}
  section h2 {{ margin-top: 0; font-size: 17px; border-left: 4px solid var(--accent); padding-left: 10px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; margin-top: 10px; }}
  th, td {{ border: 1px solid var(--border); padding: 8px 10px; text-align: left; vertical-align: top; }}
  th {{ background: #1c2334; color: var(--muted); font-weight: 600; }}
  a {{ color: var(--accent); text-decoration: none; }}
  a:hover {{ text-decoration: underline; }}
  .badge {{ display: inline-block; padding: 2px 8px; border-radius: 12px; font-size: 12px; font-weight: 600; }}
  .badge-ok {{ background: #123a26; color: var(--ok); }}
  .badge-bad {{ background: #3a1414; color: var(--bad); }}
  .badge-danger {{ background: var(--danger-bg); color: var(--danger-fg); border: 1px solid #7a2a35; }}
  .badge-muted {{ background: #262d3f; color: var(--muted); }}
  .tag {{ display: inline-block; padding: 1px 6px; border-radius: 4px; font-size: 11px; margin-right: 4px; }}
  .tag-fact {{ background: #16233d; color: var(--fact); }}
  .tag-estimate {{ background: #3a2c12; color: var(--estimate); }}
  .gap-list {{ margin: 6px 0 0 0; padding-left: 18px; font-size: 12px; color: var(--muted); }}
  .kw-heading {{ margin: 18px 0 4px; font-size: 14px; color: var(--accent); }}
  .legend {{ font-size: 12px; color: var(--muted); margin-top: 8px; }}
  .muted {{ color: var(--muted); }}
  footer {{ text-align: center; color: var(--muted); font-size: 12px; margin-top: 30px; }}
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
  <h2>① 키워드 비교표</h2>
  <table>
    <thead><tr><th>키워드</th><th>자사 순위</th><th>자사가 쓰는 말</th><th>경쟁사가 쓰는 말 / 갭</th></tr></thead>
    <tbody>
      {keyword_table}
    </tbody>
  </table>
  <div class="legend">
    <span class="tag tag-fact">fact</span> 관찰된 사실(원본 데이터 그대로) ·
    <span class="tag tag-estimate">estimate</span> 관찰값 기반 제안(일반 SEO 통념) ·
    {badge('미노출','danger')} 자사 페이지가 상위 5위 밖
  </div>
</section>

<section>
  <h2>③ 온페이지 기술요소 비교표</h2>
  {axis3_table}
  <div class="legend">각 값 옆 링크는 근거 페이지 URL입니다. 회색 배지는 데이터 없음(수집 실패/렌더링 필요).</div>
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
