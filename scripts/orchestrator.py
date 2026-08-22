"""
오케스트레이터: 전체 파이프라인 흐름을 제어한다.
승인 게이트를 강제하기 위해 두 개의 커맨드로 나눈다.

  python3 orchestrator.py scan <client_url>
      → ①site-scanner만 실행하고 keywords.json을 보여준 뒤 반드시 멈춘다.
        (여기서 사람이 키워드를 확인/수정한다. 자동으로 다음 단계로 넘어가지 않는다.)

  python3 orchestrator.py resume
      → 사람이 keywords.json을 승인/수정한 뒤 호출.
        ②serp-collector → ③content-extractor → ④gap-analyzer → ⑤report-builder 순서로 실행.
        각 단계는 독립 스크립트이므로, 특정 단계만 실패하면 그 단계만 다시
        (예: python3 scripts/serp_collector.py) 실행할 수 있다.
"""
import subprocess
import sys
from pathlib import Path

from common import DATA_DIR, ROOT_DIR, load_json, log

STEP = "orchestrator"
SCRIPTS_DIR = ROOT_DIR / "scripts"


def run_step(script_name: str, *args) -> bool:
    cmd = [sys.executable, str(SCRIPTS_DIR / script_name), *args]
    log(STEP, f"▶ 실행: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=str(SCRIPTS_DIR))
    if result.returncode != 0:
        log(STEP, f"❌ {script_name} 실패 (종료코드 {result.returncode}). 위 로그의 원인을 확인 후 "
                   f"'python3 scripts/{script_name}' 로 이 단계만 다시 실행하세요.")
        return False
    return True


def cmd_scan(client_url: str):
    log(STEP, "① site-scanner 실행: 사이트 구조를 파악해 키워드 후보를 만듭니다.")
    if not run_step("site_scanner.py", client_url):
        sys.exit(1)

    kdata = load_json(DATA_DIR / "keywords.json")
    print("\n" + "=" * 60)
    print("★ 승인 게이트 — 아래 키워드 후보를 확인해주세요")
    print("=" * 60)
    for i, kc in enumerate(kdata["keyword_candidates"], 1):
        mark = "✅" if kc["selected"] else "⬜"
        print(f"  {mark} [{i}] {kc['keyword']}  (카테고리: {kc['source_category']})")
    print("=" * 60)
    print(f"파일 위치: {DATA_DIR / 'keywords.json'}")
    print(
        "\n이 목록이 괜찮으면 그대로 'python3 scripts/orchestrator.py resume' 를 실행해주세요.\n"
        "특정 키워드를 빼고 싶으면 위 파일을 열어 해당 항목의 \"selected\": true 를 "
        "false로 바꾼 뒤 resume 하세요.\n"
        "키워드 자체를 바꾸고 싶으면 \"keyword\" 값을 직접 수정해도 됩니다.\n"
        "(자동으로 다음 단계로 넘어가지 않습니다 — 반드시 확인 후 resume 명령을 입력하세요.)"
    )


def cmd_resume():
    kpath = DATA_DIR / "keywords.json"
    if not kpath.exists():
        log(STEP, "❌ keywords.json이 없습니다. 먼저 'python3 scripts/orchestrator.py scan <url>' 을 실행하세요.")
        sys.exit(1)

    log(STEP, "승인된 keywords.json으로 파이프라인을 재개합니다.")
    steps = [
        ("② serp-collector", "serp_collector.py"),
        ("③ content-extractor", "content_extractor.py"),
        ("④ gap-analyzer", "gap_analyzer.py"),
        ("⑤ report-builder", "report_builder.py"),
    ]
    for label, script in steps:
        log(STEP, f"{label} 실행 중...")
        if not run_step(script):
            sys.exit(1)

    log(STEP, "✅ 전체 파이프라인 완료! report.html 이 생성되었습니다.")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1]
    if command == "scan":
        if len(sys.argv) < 3:
            print("사용법: python3 orchestrator.py scan <client_url>")
            sys.exit(1)
        cmd_scan(sys.argv[2])
    elif command == "resume":
        cmd_resume()
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
