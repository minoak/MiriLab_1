# -*- coding: utf-8 -*-
"""임시 스모크 테스트 2 — UI 데이터 흐름 + 모듈 import 검증. 끝나면 삭제."""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

print("== import checks ==")
import graph.spaces            # noqa
import graph.village           # noqa
import prompts                 # noqa
import state                   # noqa
import ui.mock as mock         # noqa
import ui.model as model       # noqa
import ui.tab_village          # noqa  (streamlit import 포함)
import ui.state_helpers        # noqa  (build_graph/langgraph 포함)
import graph.build             # noqa  (diffusion 삭제 후에도 그래프 컴파일?)
print("all imports OK")

print("\n== graph compile (diffusion 삭제 영향 없음 확인) ==")
appg = graph.build.build_graph()
print("graph compiled:", appg is not None)

print("\n== sample_simstate -> build_view (village 패스스루) ==")
sim = mock.sample_simstate(None, n=12)
print("sim has village:", "village" in sim)
view = model.build_view(sim)
v = view.get("village") or {}
agg = v.get("aggregate") or {}
print("view.village keys:", sorted(v.keys()))
print("residents:", len(v.get("residents") or []))
print("steps:", v.get("steps"))
print("aggregate keys:", sorted(agg.keys()))
print("n / blindspot_rate:", agg.get("n"), agg.get("blindspot_rate"))
print("place_reach:", agg.get("place_reach"))
print("home_bound:", [h["name"] for h in (agg.get("home_bound") or [])])
print("blindspot:", [(b["name"], b["status"]) for b in (agg.get("blindspot") or [])])
print("winners:", [(w["name"], w["delta"]) for w in (agg.get("winners") or [])])
print("losers:", [(l["name"], l["delta"]) for l in (agg.get("losers") or [])])

print("\n== per_place 첫 시점 분포 ==")
pp0 = (agg.get("per_place") or [{}])[0]
for k, people in (pp0.get("places") or {}).items():
    if people:
        print(f"  {k}: {[p['name'] for p in people]}")

print("\n== 개별 타임라인 샘플 (이준호=청년, 김복순=독거어르신) ==")
for r in (v.get("residents") or []):
    if r["name"] in ("이준호", "김복순"):
        traj = [(t["place"], t["policy_status"], t["economic"], t["wellbeing"]) for t in r["timeline"]]
        print(f"  {r['name']}: {traj}")

print("\n== state 계약 확인 ==")
print("VillageStep has place:", "place" in state.VillageStep.__annotations__)
print("SpaceNode exists:", hasattr(state, "SpaceNode"))
print("\nOK")
