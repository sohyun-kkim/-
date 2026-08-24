"""
SERP 결과 중 '실제 판매/이커머스 경쟁사'가 아닌 도메인을 걸러내기 위한 분류.
언론/매거진(기사)과 커뮤니티/UGC 사이트를 모두 제외 대상으로 본다
(사용자 확인: 둘 다 제외 — 실제 판매 경쟁사만 남기는 게 목적).

목록은 하드코딩된 화이트리스트/블랙리스트 방식이라 완전하지 않다.
새로 걸러야 할 도메인이 보이면 이 파일의 두 set에 추가하면 된다.
"""

NEWS_MAGAZINE_DOMAINS = {
    "allure.com", "glamour.com", "byrdie.com", "refinery29.com", "vogue.com",
    "elle.com", "harpersbazaar.com", "cosmopolitan.com", "self.com",
    "marieclaire.com", "instyle.com", "popsugar.com", "buzzfeed.com",
    "nytimes.com", "cnn.com", "forbes.com", "businessinsider.com", "today.com",
    "goodhousekeeping.com", "realsimple.com", "wsj.com", "usatoday.com",
    "people.com", "verywellhealth.com", "healthline.com", "wikihow.com",
    "thezoereport.com", "whowhatwear.com", "teenvogue.com", "allthingshair.com",
    "southernliving.com", "marthastewart.com", "menshealth.com",
    "womenshealthmag.com", "everydayhealth.com", "health.com", "prevention.com",
    "shape.com", "thecut.com", "nymag.com", "vice.com", "mashable.com",
    "huffpost.com", "huffingtonpost.com",
}

UGC_COMMUNITY_DOMAINS = {
    "reddit.com", "quora.com", "pinterest.com", "youtube.com", "tiktok.com",
    "facebook.com", "instagram.com", "twitter.com", "x.com", "medium.com",
    "wikipedia.org",
}


def classify_domain(domain: str):
    """도메인을 'media' | 'ugc' | None(경쟁사 후보)으로 분류한다."""
    d = domain.lower().strip()
    for known in NEWS_MAGAZINE_DOMAINS:
        if d == known or d.endswith("." + known):
            return "media"
    for known in UGC_COMMUNITY_DOMAINS:
        if d == known or d.endswith("." + known):
            return "ugc"
    return None


def is_noncompetitor(domain: str) -> bool:
    return classify_domain(domain) is not None
