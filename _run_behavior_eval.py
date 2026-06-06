# -*- coding: utf-8 -*-
"""일탈 행동 캐스팅 — 발현 안정성 eval (실모드, OpenAI 키 필요).

질문: 캐스팅(LLM 선정 + 임계값 자연 발생)은 비결정론이다 — **같은 정책을 N회
돌리면 같은 인물이 일관되게 발현하는가?** cluster eval 이 입장 안정성(82%)을
잰 것과 동일한 정직성 패턴: 흔들림을 숨기지 않고 측정해 리포트에 쓴다.

측정:
  - 인물별 발현률(manifest_count / N) → 안정 발현(≥80%) / 안정 비발현(≤20%) /
    경계(그 사이) 인원
  - 런 쌍별 발현 집합 Jaccard 평균(런이 서로 얼마나 같은 명단을 뽑나)
  - 인물별 점수 평균·표준편차, 발현자 태그 표본
산출: eval/behavior_results.json + 콘솔 요약.

실행: python _run_behavior_eval.py [N회, 기본 5] [정책이름(기본: 청년 월세)]
비용: 캐스팅만 측정 — LLM 호출 N회(런당 1회). react 전체는 돌리지 않는다.
"""
import sys, io, json, itertools
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from graph.llm import has_real_key
from graph.nodes import run_casting, DEVIANCE_THRESHOLD
from data.personas import load_personas
from sample_policies import SAMPLES, DEFAULT_POLICY


def main() -> None:
    n_runs = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    policy_name = sys.argv[2] if len(sys.argv) > 2 else None
    policy = SAMPLES.get(policy_name, DEFAULT_POLICY) if policy_name else DEFAULT_POLICY

    if not has_real_key():
        print("[SKIP] OPENAI_API_KEY 가 없습니다 — 이 eval 은 실모드 전용입니다.")
        sys.exit(0)

    personas = load_personas(24, seed=42)
    by_id = {p["id"]: p for p in personas}
    print(f"캐스팅 발현 안정성 측정: {n_runs}회 × {len(personas)}명 "
          f"(임계값 {DEVIANCE_THRESHOLD})\n")

    runs = []           # 각 런의 members dict
    manifest_sets = []  # 각 런의 발현 persona_id 집합
    for i in range(n_runs):
        casting = run_casting(personas, policy)
        members = (casting or {}).get("members", {})
        mset = {pid for pid, e in members.items() if e.get("manifest")}
        runs.append(members)
        manifest_sets.append(mset)
        names = ", ".join(sorted(by_id[pid]["name"] for pid in mset)) or "(없음)"
        print(f"  run {i + 1}: 발현 {len(mset)}명 — {names}")

    # 인물별 통계
    stats = []
    for pid, p in by_id.items():
        scores = [r[pid]["score"] for r in runs if pid in r]
        count = sum(1 for s in manifest_sets if pid in s)
        tags = sorted({r[pid]["tag"] for r in runs if pid in r and r[pid].get("tag")})
        if not scores:
            continue
        mean = sum(scores) / len(scores)
        std = (sum((s - mean) ** 2 for s in scores) / len(scores)) ** 0.5
        stats.append({
            "persona_id": pid, "name": p["name"],
            "manifest_count": count, "n_runs": n_runs,
            "score_mean": round(mean, 1), "score_std": round(std, 1),
            "tags": tags,
        })

    ever = [s for s in stats if s["manifest_count"] > 0]
    stable_on = [s for s in ever if s["manifest_count"] / n_runs >= 0.8]
    border = [s for s in ever if 0.2 < s["manifest_count"] / n_runs < 0.8]

    # 런 쌍별 Jaccard — 발현 명단이 런 간 얼마나 일치하나.
    pairs = list(itertools.combinations(manifest_sets, 2))
    def jac(a, b):
        return (len(a & b) / len(a | b)) if (a | b) else 1.0
    jaccard_mean = round(sum(jac(a, b) for a, b in pairs) / len(pairs), 3) if pairs else 1.0

    print(f"\n발현 경험 인물: {len(ever)}명 / 안정 발현(≥80%): {len(stable_on)}명 / "
          f"경계(20~80%): {len(border)}명")
    print(f"런 간 발현 명단 Jaccard 평균: {jaccard_mean}")
    for s in sorted(ever, key=lambda x: -x["manifest_count"]):
        print(f"  - {s['name']}: {s['manifest_count']}/{n_runs}회 "
              f"(점수 {s['score_mean']}±{s['score_std']}) 태그={s['tags']}")

    out = {
        "n_runs": n_runs,
        "threshold": DEVIANCE_THRESHOLD,
        "policy": policy_name or "청년 월세(기본)",
        "jaccard_mean": jaccard_mean,
        "n_ever_manifest": len(ever),
        "n_stable_manifest": len(stable_on),
        "n_borderline": len(border),
        "personas": sorted(stats, key=lambda x: -x["manifest_count"]),
    }
    dest = Path(__file__).parent / "eval" / "behavior_results.json"
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n저장: {dest}")
    print("해석 가이드: Jaccard ≥ 0.6 + 경계 인원 소수면 '발현은 우연이 아니라 "
          "인물 처지에서 나온다'고 발표에서 말할 수 있다. 낮으면 임계값/프롬프트 보정 필요.")


if __name__ == "__main__":
    main()
