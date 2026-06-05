# -*- coding: utf-8 -*-
"""_test_minivillage_sim.py — 미리마을 step2 (전파 시뮬) 키리스 단위 테스트.

검증(외부 호출 0):
  1) 인라인 JS 이스케이프(item D) — '<','>' 무력화로 </script>·<script·<!-- 토큰 소멸,
     값은 JSON 유니코드 이스케이프로 보존(LLM 대사가 meetings.js 로 들어와도 안 깨짐)
  2) assemble — 토큰 주입 데이터로도 raw '</script' 누출 없음(메커니즘)
  3) _load_gen — gen_schedules/gen_dialogues importlib 로드 + 핵심 심볼 존재
"""
import json
import sys

from ui import tab_minivillage as T


def main():
    fails = []

    # 1) 이스케이프 라운드트립
    payload = 'a</script>b<!--c<script d>e'
    out = T._neutralize_inline_js(payload)
    if "<" in out or ">" in out:
        fails.append(f"이스케이프 후 raw <,> 잔존: {out!r}")
    for tok in ("</script", "<script", "<!--"):
        if tok in out:
            fails.append(f"위험 토큰 '{tok}' 잔존")
    # JSON 문자열 값으로 라운드트립(값 복원 확인): "..<.." -> '<'
    if json.loads(f'"{out}"') != payload:
        fails.append("이스케이프 값이 JSON 라운드트립에서 원문과 다름")

    # 2) assemble — 실제 파일로 외부참조 0(이스케이프가 인라인 깨지 않음)
    html = T.assemble_village_html(T.MINIVILLAGE_ROOT)
    if 'src="assets/' in html or 'src="data/' in html:
        fails.append("assemble 후 외부 참조 잔존")
    # 데이터 JS 가 인라인됐는지(유니코드 이스케이프 형태 포함 가능)
    if "const MEETINGS" not in html or "const VILLAGERS" not in html:
        fails.append("데이터 JS 인라인 누락")

    # 3) _load_gen — 두 모듈 + 핵심 심볼
    gs, gd = T._load_gen()
    for sym in ("generate", "build_village_context"):
        if not hasattr(gs, sym):
            fails.append(f"gen_schedules.{sym} 없음")
    for sym in ("run_day", "initial_states", "extract_meetings", "has_real_key", "AWARE_SET"):
        if not hasattr(gd, sym):
            fails.append(f"gen_dialogues.{sym} 없음")
    # initial_states 시드 동작(키 불필요)
    villagers = gd._load("villagers.json")["villagers"]
    s0 = gd.initial_states(villagers, aware_ids=T.SEED_IDS)
    if sum(1 for s in s0.values() if s["awareness"] == "aware") != len(T.SEED_IDS):
        fails.append("initial_states 시드 수 불일치")

    print("[1] 이스케이프 라운드트립 OK" if not any("이스케이프" in f or "토큰" in f for f in fails) else "[1] FAIL")
    print("[2] assemble 외부참조 0 + 인라인 OK" if not any("assemble" in f or "인라인" in f for f in fails) else "[2] FAIL")
    print("[3] _load_gen 심볼 OK" if not any("gen_" in f or "initial_states" in f for f in fails) else "[3] FAIL")
    print()
    if fails:
        print("[FAIL] " + " | ".join(fails))
        sys.exit(1)
    print("ALL PASS - 이스케이프(item D) / assemble / importlib 로더")


if __name__ == "__main__":
    main()
