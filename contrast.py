# -*- coding: utf-8 -*-
"""contrast.py — 정책 인생극장 오케스트레이션 (DESIGN v3).

정책 패키지(여러 정책)를 받아 한 흐름으로 묶는다:

    정책 패키지(list)
      → policy_spec.resolve_specs   : 각 정책의 타깃 명세
      → personas.select_contrast_trio: 대조적인 3명(수혜/경계/사각) 선별 + 매트릭스
      → graph.village.simulate_village: 고른 3명만 시간 경과 인생 시뮬(정책 패키지 주입)

Streamlit 의존이 없어 헤드리스로 검증 가능하다(_verify_contrast.py).
import 시점에는 어떤 네트워크/LLM 호출도 하지 않는다.

공개 API:
    run_contrast(personas, policies, simulate=None, ...) -> dict
"""
from __future__ import annotations

from data.personas import select_contrast_trio
from policy_spec import resolve_specs, package_text


def run_contrast(
    personas: list,
    policies,
    simulate=None,
    grounded: bool = True,
    step_labels: list | None = None,
    max_workers: int = 8,
    use_llm_spec: bool = True,
    specs: list | None = None,
) -> dict:
    """정책 패키지 → 대조 3명 선별 → 그 3명만 인생 시뮬, 한 번에 실행한다.

    Args:
        personas: list[Persona dict] (load_personas 결과, 후보 풀).
        policies: 정책 패키지. 정책명(SAMPLES 키)/원문/{name,text} 의 list(또는 단일).
        simulate: (personas, policy_text, step_labels) -> village dict 콜러블.
                  None 이면 graph.village.simulate_village 를 실제 실행한다.
                  (mock 검증 시 ui.mock.sample_village 래퍼를 주입.)
        grounded: 페르소나 grounding 토글(ablation 시 False).
        step_labels: 시점 라벨(기본 simulate_village 의 1·3·6개월).
        use_llm_spec: 임의 정책의 명세를 LLM 으로 추출할지(False=키워드 폴백).
        specs: 이미 만들어진 타깃 명세(list). 주어지면 resolve_specs 를 건너뛴다.
               (사이드바에서 사용자 태그로 만든 policy_spec 을 그대로 주입 = 슬라이스 2
                '프롬프트 통일'. 명세추출 LLM 호출 0.)

    Returns:
        {
          "specs":        list[spec dict],            # 정책별 타깃 명세
          "selection":    select_contrast_trio 결과,   # {matrix, trio, notes, ...}
          "package_text": str,                        # 시뮬에 주입한 패키지 원문
          "village":      {steps, residents, aggregate},  # 3명 인생 궤적
          "trio_ids":     [선별된 3명 id],
        }
    """
    personas = personas or []
    # 1) 정책 → 타깃 명세(패키지). specs 가 주어지면(사이드바 policy_spec) 재추출 생략.
    if specs is None:
        specs = resolve_specs(policies, use_llm=use_llm_spec)
    bundle = package_text(specs)

    # 2) 후보 풀에서 대조 3명 선별(결정론, LLM 0).
    selection = select_contrast_trio(personas, specs)
    trio = [t["persona"] for t in selection.get("trio", [])]
    trio_ids = [p.get("id") for p in trio]

    # 3) 고른 3명만 시간 경과 인생 시뮬(정책 패키지 텍스트를 정책으로 주입).
    if not trio:
        village = {"steps": step_labels or [], "residents": [], "aggregate": {}}
    elif simulate is not None:
        village = simulate(trio, bundle, step_labels)
    else:
        from graph.village import simulate_village
        village = simulate_village(
            trio, bundle, step_labels=step_labels,
            grounded=grounded, max_workers=max_workers,
        )

    return {
        "specs": specs,
        "selection": selection,
        "package_text": bundle,
        "village": village,
        "trio_ids": trio_ids,
    }
