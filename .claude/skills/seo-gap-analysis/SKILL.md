---
name: seo-gap-analysis
description: SEO 콘텐츠 갭 분석 시 gap-analyzer 단계가 반드시 지켜야 할 규칙. 관찰 가능한 신호 8종만 근거로 사용하고, 모든 주장에 evidence URL을 첨부하며, "관찰된 사실"과 "추정"을 명확히 구분한다. 축1(키워드 사용법)·축3(온페이지 기술요소) 분석에 적용한다.
---

# SEO 콘텐츠 갭 분석 스킬

이 스킬은 `gap-analyzer` 단계(④)가 `pages.json`을 입력받아 `analysis.json`을
만들 때 지켜야 하는 규칙을 정의한다. 이 규칙을 벗어난 분석은 무효로 간주한다.

## 1. 관찰 가능한 신호 8종 화이트리스트

분석의 근거는 아래 8종으로만 한정한다. 이 목록 밖의 어떤 것도 "왜 상위에
있는가"를 설명하는 근거로 쓸 수 없다.

1. `title` 내 키워드 포함 여부 및 위치(앞/중간/뒤)
2. `h1` 키워드 포함 여부
3. `h2_list` 키워드 포함 여부
4. `word_count` (본문 글자 수)
5. `image_count` (이미지 개수)
6. `alt_fill_rate` (alt 속성 채움률)
7. `internal_link_count` (내부링크 수)
8. `schema_types` (JSON-LD 스키마 타입) 및 `last_modified`

## 2. 금지 사항

- 위 8종 밖의 요인(예: 백링크, 도메인 권위, 페이지 속도, 사용자 체류시간,
  브랜드 인지도, 소셜 시그널 등)을 언급하거나 "상위 노출의 이유"로 추정하지 않는다.
  이런 요소는 애초에 수집하지 않았으므로 언급 자체가 근거 없는 지어내기다.
- 신호값이 없거나 수집 실패(`render_required:true`)한 페이지는 분석 대상에서
  제외하고, 부록의 "수집 실패" 목록으로만 보고한다. 빈 값을 추정치로 채우지 않는다.
- 관찰되지 않은 것을 관찰된 것처럼 단정적으로 서술하지 않는다.

## 3. evidence 필드 강제

`analysis.json`의 모든 주장 항목(비교표의 각 행, gap_terms 각 항목 등)에는
반드시 `evidence` 필드로 근거가 된 페이지의 실제 URL을 첨부한다. evidence가
없는 주장은 출력하지 않는다.

## 4. "관찰된 사실" vs "추정" 구분

- **관찰된 사실**: pages.json의 signals 필드에서 직접 읽은 값을 그대로 보고하는
  경우. 예: "경쟁사 A는 title에 '키워드'를 포함하지만 자사는 미포함" — 이것은
  100% 관찰값이므로 사실(fact)로 표시한다.
- **추정**: 관찰된 값들을 근거로 개선 방향을 제안하는 경우. 예: "title에 키워드를
  포함하면 검색 노출에 도움이 될 수 있음" — 이것은 일반적인 SEO 통념에 기반한
  제안이므로 추정(estimate)으로 표시한다.
- 두 종류를 analysis.json에서 `"type": "fact"` / `"type": "estimate"` 필드로
  구분하고, report-builder가 이를 색상으로 다르게 렌더링한다.

## 5. 축1 — 키워드 사용법 비교

자사 페이지와 상위 경쟁사 페이지가 "같은 개념을 어떤 단어로 부르는지"를
title/h1/h2_list 텍스트에서 추출해 비교한다.

- `own_terms`: 자사 페이지에서 관찰된 키워드 관련 표현
- `competitor_terms`: 경쟁사 페이지들에서 관찰된 표현
- `gap_terms`: 경쟁사는 쓰지만 자사는 안 쓰는 표현 (관찰 기반, 사실)
- 자사가 상위 5에 없는 키워드(`own_visibility: "not_ranked"`)는 own_terms를
  빈 값으로 두고 gap_terms에 "미노출" 사실을 evidence와 함께 기록한다.

## 6. 축3 — 온페이지 기술요소 비교

항목: title 키워드 포함, h1 키워드 포함, JSON-LD 스키마 유무/타입,
alt_fill_rate, word_count, image_count, internal_link_count.

자사 vs 상위 3개 경쟁사를 표 형태(`comparison_table`)로 비교하고, 각 셀은
관찰값 그대로(✓/✗, 숫자)를 채우며 모든 행에 evidence(해당 페이지 URL 목록)를
첨부한다.
