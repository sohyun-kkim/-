# SEO 콘텐츠 갭 분석 리포트 — 오늘 2시간 완결 데모

클라이언트 URL 1개를 넣으면 SERP 상위 5개와 비교해 **키워드 사용법(축1)**과
**온페이지 기술요소(축3)** 갭을 정리한 `report.html` 하나를 만들어주는 파이프라인.

## 팀 구조

```
[오케스트레이터] 전체 흐름 제어·단계별 재실행
   ├─ ① site-scanner     입력:URL → 출력:keywords.json | 도구:fetch + LLM
   ★ 승인 게이트(사람)    keywords.json 확인·수정 후 재개
   ├─ ② serp-collector   입력:keywords.json → 출력:serp_results.json | 도구:SerpApi(+cache 우선)
   │                     언론/매거진·커뮤니티(UGC) 도메인은 실제 판매 경쟁사가 아니므로 제외
   │                     (scripts/noncompetitor_domains.py, 제외 내역은 리포트에 표시)
   ├─ ③ content-extractor 입력:serp_results.json → 출력:pages.json | 도구:requests + BeautifulSoup
   ├─ ④ gap-analyzer     입력:pages.json → 출력:analysis.json | 스킬:seo-gap-analysis(축1·3) | 도구:LLM
   └─ ⑤ report-builder   입력:analysis.json → 출력:report.html
```

## 실행 방법

```bash
# 1) .env 에 ANTHROPIC_API_KEY, SERPAPI_API_KEY 채워넣기 (최초 1회)

# 2) 키워드 후보 생성 (여기서 반드시 멈춤 — 승인 게이트)
python3 scripts/orchestrator.py scan https://client-site.com

# 3) data/keywords.json 을 열어 키워드 확인/수정 후:
python3 scripts/orchestrator.py resume

# 4) 완성된 report.html 을 더블클릭해서 열기
```

특정 단계만 실패했다면 그 단계 스크립트만 다시 실행하면 된다
(예: `python3 scripts/serp_collector.py`). 각 단계는 이전 단계의 JSON 파일만
입력으로 받으므로 독립적으로 재실행 가능하다.

## 파일 구조

- `scripts/` — 단계별 스크립트 (site_scanner, serp_client, serp_collector,
  content_extractor, gap_analyzer, report_builder, orchestrator, common)
- `.claude/skills/seo-gap-analysis/SKILL.md` — gap-analyzer가 지키는 규칙
  (관찰 신호 8종 화이트리스트, evidence 강제, fact/estimate 구분)
- `cache/serp/` — 키워드 해시별 SERP 캐시 (있으면 API 호출 안 함)
- `data/` — 단계별 중간 산출물(JSON), 매 클라이언트 실행마다 덮어씀
- `report.html` — 최종 산출물, 더블클릭으로 열리는 단일 HTML

## 오늘 만들지 않은 것 (로드맵)

- Phase 2: 축2(콘텐츠 형식)·축4(정보 깊이), semantic 폴백 매칭, 카테고리 LLM
  의미정규화, SERP 벤더 다중화(DataForSEO/Serper)
- Phase 3: Playwright headless 렌더링 폴백, 네이버 검색 연동, 클라이언트 제출용
  리포트 모드, GDrive 자동 아카이빙, 시계열 추적·다수 클라이언트 배치 실행
