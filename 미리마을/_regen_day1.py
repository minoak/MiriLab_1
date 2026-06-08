# -*- coding: utf-8 -*-
"""시드 교체(staff) 후 실 LLM 1일차 재생성(일회용 dev).

기존 sim_state 의 정책을 재사용해 리셋 → 동선 재생성 + 1일차(만남·전파·일기).
"""
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, r"C:\Users\akals\Downloads\미리랩")

from ui import tab_minivillage as T  # noqa: E402

sd = T._load_sim_state() or {}
policy = (sd.get("policy") or "").strip() or (
    "만 19~34세 무주택 청년에게 월 20만 원의 임대료를 최대 12개월 지원한다. "
    "신청은 복지로 또는 주민센터 방문."
)
print("정책:", policy[:100])

gs, gd = T._load_gen()
print(f"프로바이더: {gd.PROVIDER} ({gd.MODEL}), 실키: {gd.has_real_key()}")
assert gd.has_real_key(), "실키 없음 — 중단"

try:
    T.SIM_STATE_PATH.unlink()
    print("sim_state 리셋")
except OSError:
    pass

T._generate_day(policy, fresh=True)

sd = T._load_sim_state()
rec = sd["history"][-1]
aware = [v for v, s in sd["states"].items() if s["awareness"] in gd.AWARE_SET]
print()
print(f"=== 1일차 결과 (generated_with={sd['generated_with']}) ===")
print(f"인지 {len(aware)}/10: {', '.join(aware)}")
print(f"전파 엣지 {len(rec['propagation'])}개:")
for e in rec["propagation"]:
    t = e.get("time", 0)
    print(f"  {e['from']} -> {e['to']}  ({t//60:02d}:{t%60:02d} @ {e['place']})")
