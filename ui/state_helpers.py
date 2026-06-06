"""Streamlit 세션/리소스 헬퍼.

UI 계층(app.py, tab_*.py)이 직접 LangGraph·페르소나 로더를 다루지 않도록
캐싱과 폴백을 한곳에 모은다.

공개 API:
- get_graph()                : 컴파일된 그래프(앱) — @st.cache_resource
- get_personas(n, seed)      : 페르소나 리스트 — @st.cache_resource
- run_simulation(...)        : 축1 단독 실행 → 완전한 SimState dict
- run_full_pipeline(...)     : 축1→축2→축3 한 흐름 + 층1 체크포인트 (설계방향서 §8-1)
- rerun_from_axis2(...)      : 인생극장만 재실행 — 축1 체크포인트 재사용(축1 호출 0)
- has_demo_snapshot(name) / load_demo_snapshot(name) : 데모 녹화 재생(LLM 0콜)

설계 원칙:
- 임포트 시점에 네트워크/OpenAI 호출 금지(키 없어도 import 되어야 함).
- 키가 없거나 mock 요청이면 외부 호출 없이 sample_simstate 로 데모 동작.
- 실제 실행 중 네트워크/페르소나 로드 실패 시 안내 후 mock 으로 폴백.
"""

import json
from pathlib import Path

import streamlit as st

from graph.build import build_graph
from graph.llm import has_real_key
from ui.mock import sample_simstate
from data.personas import load_personas


@st.cache_resource(show_spinner=False)
def get_graph():
    """컴파일된 LangGraph 앱을 세션 전역에서 1회만 빌드해 재사용한다."""
    return build_graph()


@st.cache_resource(show_spinner=False)
def get_personas(n: int = 24, seed: int = 42):
    """페르소나 리스트를 캐시한다.

    첫 호출에서만 HF 데이터셋 다운로드/샘플링이 일어나고,
    이후 동일 (n, seed) 조합은 캐시된 결과를 즉시 반환한다.
    """
    return load_personas(n, seed)


def run_simulation(
    policy: str,
    mock: bool = False,
    n: int = 24,
    seed: int = 42,
    grounded: bool = True,
    rounds: int = 1,
) -> dict:
    """정책 텍스트에 대한 시뮬레이션을 실행하고 완전한 SimState dict 를 반환한다.

    동작 분기:
    1) mock=True 또는 OpenAI 키 없음  → 외부 호출 없이 sample_simstate 로 데모.
    2) 그 외                         → 페르소나 로드 + 그래프 invoke 로 실제 실행.
       - 페르소나 로드/네트워크/그래프 실행 중 예외 발생 시 경고 후 mock 폴백.

    반환: SimState 형태의 dict (state.SimState 계약 준수).
    """
    # 1) 데모 모드: 명시적 mock 이거나 실제 키가 없으면 즉시 가짜 상태 반환.
    if mock or not has_real_key():
        if mock:
            # 사용자가 의도적으로 데모를 선택한 경우 가볍게 안내.
            st.caption("데모 모드: 샘플 데이터로 결과를 표시합니다(OpenAI 호출 없음).")
        else:
            # 키가 없어 데모로 떨어진 경우만 별도 안내.
            st.info(
                "OpenAI API 키가 없어 데모(샘플) 모드로 실행합니다. "
                "실제 시뮬레이션은 .env 에 OPENAI_API_KEY 를 설정하세요."
            )
        return sample_simstate(policy)

    # 2) 실제 실행 모드: 페르소나 로드 → 그래프 빌드 → invoke.
    try:
        with st.status("시뮬레이션 준비 중...", expanded=False) as status:
            # 2-1) 페르소나 로드(첫 호출 시 다운로드/샘플, 이후 캐시).
            status.update(label="페르소나 불러오는 중...")
            personas = get_personas(n, seed)

            # 2-2) 컴파일된 그래프 확보.
            status.update(label="시뮬레이션 그래프 준비 중...")
            app = get_graph()

            # 2-3) 초기 SimState 구성 후 그래프 실행.
            #      reactions/interactions/edges 는 add 리듀서가 누적하므로 빈 리스트로 시작.
            status.update(label=f"{len(personas)}명 페르소나 반응 생성 중...")
            initial_state = {
                "policy": policy,
                "personas": personas,
                "reactions": [],
                "interactions": [],
                "summary": "",
                "grounded": grounded,
                "rounds": rounds,
                "edges": [],
                "metrics": {},
                "improvements": {},
            }
            result = app.invoke(initial_state)

            status.update(label="시뮬레이션 완료", state="complete")
        return result

    except Exception as exc:  # noqa: BLE001 - 데모 안정성 위해 광범위 폴백.
        # 네트워크/페르소나 로드/그래프 실행 실패 시 데모로 폴백해 UI 가 죽지 않게 한다.
        st.warning(
            f"실제 시뮬레이션 실행에 실패하여 데모(샘플) 결과로 대체합니다. (원인: {exc})"
        )
        return sample_simstate(policy)


def run_village(
    policy: str,
    personas: list,
    grounded: bool = True,
    mock: bool = False,
    step_labels: list | None = None,
) -> dict:
    """미리 마을(시간 경과 영향) 시뮬을 on-demand 로 실행한다.

    마을 시뮬은 주민×스텝 만큼 LLM 을 호출해 무거우므로(DESIGN §8),
    react/interact/aggregate 와 분리해 사용자가 원할 때만 호출한다.

    분기:
    - mock=True / 키 없음 / personas 비었음 → sample_village(외부 호출 0).
    - 그 외 → simulate_village 실제 실행. 실패 시 sample_village 폴백.

    반환: {steps, residents, aggregate} (state.village 형태).
    """
    from ui.mock import sample_village  # 지연 import(순환 방지)

    if mock or not has_real_key() or not personas:
        return sample_village(personas, policy, step_labels=step_labels)

    try:
        from graph.village import simulate_village
        with st.status("미리 마을 시뮬레이션 중...", expanded=False) as status:
            status.update(label=f"{len(personas)}명의 시간 경과 궤적 생성 중...")
            result = simulate_village(
                personas, policy, step_labels=step_labels, grounded=grounded
            )
            status.update(label="마을 시뮬 완료", state="complete")
        return result
    except Exception as exc:  # noqa: BLE001 - 데모 안정성 폴백.
        st.warning(
            f"마을 시뮬 실행에 실패하여 데모(샘플) 궤적으로 대체합니다. (원인: {exc})"
        )
        return sample_village(personas, policy, step_labels=step_labels)


def run_contrast_sim(
    policies: list,
    personas: list,
    grounded: bool = True,
    mock: bool = False,
    step_labels: list | None = None,
    specs: list | None = None,
    reactions_by_id: dict | None = None,
) -> dict:
    """정책 인생극장(DESIGN v3): 전원 인생 시뮬 후 실제 결과에서 대조 3명 선별.

    contrast.run_contrast 를 mock/real 분기와 함께 감싼다.

    분기:
    - mock=True / 키 없음 / personas 비었음 → sample_village 주입(외부 호출 0).
    - 그 외 → 실제 simulate_village. 실패 시 sample_village 폴백.

    specs 가 주어지면(사이드바 policy_spec) 명세 재추출을 건너뛴다 = 슬라이스 2
    '프롬프트 통일'. 그 spec 의 태그가 package_text 를 통해 모델에 함께 전달된다.

    반환: {specs, selection, package_text, village, trio_ids} (contrast.run_contrast).
    """
    from contrast import run_contrast
    from ui.mock import sample_village  # 지연 import(순환 방지)

    def _mock_sim(ps, pol, sl):
        return sample_village(ps, pol, step_labels=sl)

    # mock 경로: 명세 추출도 키워드 폴백(use_llm_spec=False)로 외부 호출 0.
    if mock or not has_real_key() or not personas:
        return run_contrast(
            personas, policies, simulate=_mock_sim,
            grounded=grounded, step_labels=step_labels, use_llm_spec=False,
            specs=specs, reactions_by_id=reactions_by_id,
        )

    # 실제 경로: simulate=None → 진짜 simulate_village, 명세는 LLM 추출 허용.
    try:
        with st.status("정책 인생극장 시뮬레이션 중...", expanded=False) as status:
            status.update(label="전원 인생 궤적 생성 + 대조 3명 선별 중...")
            result = run_contrast(
                personas, policies, simulate=None,
                grounded=grounded, step_labels=step_labels, use_llm_spec=True,
                specs=specs, reactions_by_id=reactions_by_id,
            )
            status.update(label="인생극장 시뮬 완료", state="complete")
        return result
    except Exception as exc:  # noqa: BLE001 - 데모 안정성 폴백.
        st.warning(
            f"실모드 인생극장 실행에 실패하여 데모(샘플) 궤적으로 대체합니다. (원인: {exc})"
        )
        return run_contrast(
            personas, policies, simulate=_mock_sim,
            grounded=grounded, step_labels=step_labels, use_llm_spec=False,
            specs=specs, reactions_by_id=reactions_by_id,
        )


# =====================================================================
# §8-1 실행 묶기 — 단방향 3축 파이프라인 + 층1 체크포인트 (설계방향서 §2·§6)
# =====================================================================
# 층1 결과 체크포인트 세션 키. 축 경계의 중간 산출물을 보존해
# "재실행은 바뀐 축부터만"을 가능하게 한다(호출 수 자체를 줄이는 절감).
PIPELINE_CKPT_KEY = "pipeline_ckpt"


def _adopt_axis3_metrics(view: dict) -> None:
    """v1.2 지표 소유권(§8-14): 게이지 3키를 axis3 t0 지표 값으로 덮는다.

    화면 지표의 단일 진실원 = 축3. behavior_counts 등 나머지 metrics 키는 보존 —
    리포트·정책 개선 탭은 무수정으로 같은 숫자를 읽는다.
    """
    t0m = ((view.get("axis3") or {}).get("t0_metrics")) or {}
    if not t0m:
        return
    merged = dict(view.get("metrics") or {})
    for k in ("정책수용도", "신청의향지수", "사회혼란도"):
        if k in t0m:
            merged[k] = t0m[k]
    view["metrics"] = merged


def run_full_pipeline(
    model_policy: str,
    policy: str | None = None,
    spec: dict | None = None,
    mock: bool = False,
    n: int = 24,
    seed: int = 42,
    grounded: bool = True,
    rounds: int = 1,
) -> tuple:
    """축1(정보) → 축2(결과) → 축3(요약·개선)을 한 흐름으로 실행한다.

    한 실행 = 전수 react(t0 불변 기록) → reactions_by_id 시딩으로 전원 인생극장
    → 코드 집계. 축 경계마다 산출물을 session_state 층1 체크포인트에 보존한다:
      - 정책 수정·A/B      → 이 함수(축1부터 전부)
      - 인생극장만 다시    → rerun_from_axis2 (축1 전수 호출 통째 절약)
      - 표시·집계 옵션     → 축3만(코드라 공짜 — §8-4에서 명시화)

    Args:
        model_policy: 모델에 보낼 정책 텍스트(태그 접두 포함 가능).
        policy: 표시·축2용 정책 원문. None 이면 model_policy 그대로.
        spec: 사이드바 결정론 policy_spec(축2 명세 재추출 생략 + 대상 판정).
        mock/n/seed/grounded/rounds: run_simulation 과 동일. mock 은 축1·2 공통
            (데모 체크 시 두 축 모두 외부 호출 0 — 출처 일관).

    Returns:
        (sim, view) — session_state["sim"]/["view"]/체크포인트에도 저장된다.
    """
    from ui.model import build_view  # 지연 import(ui 계층 순환 방지)

    display_policy = (policy or model_policy).strip()
    ckpt: dict = {}

    # ── 축1 — 정보: 강제 노출 인터뷰 → t0 성향 = 불변 기록 (§3 축1) ──
    sim = run_simulation(
        model_policy, mock=mock, n=n, seed=seed, grounded=grounded, rounds=rounds
    )
    # 표시는 깨끗하게: 원문으로 복원(태그 접두 제거), spec 은 additive 저장.
    sim["policy"] = display_policy
    if spec:
        sim["policy_spec"] = dict(spec)
    # 생성 모델 도장(additive) — 모델 = 측정 도구라, 화면의 결과가 어느 모델
    # 산출인지 박아둔다(gap eval 의 score_scale 표식과 같은 원리).
    from graph import llm as _llm  # 지연 import(이 파일은 has_real_key 만 상단 import)
    sim["llm_model"] = (
        "mock" if (mock or not has_real_key())
        else f"{_llm.PROVIDER}:{_llm.MODEL}"
    )
    ckpt["axis1"] = {
        "sig": {"policy": model_policy, "n": n, "seed": seed, "mock": mock,
                "grounded": grounded, "rounds": rounds},
        "sim": sim,
    }

    view = build_view(sim)

    # ── 축2 — 결과: t0 시딩 → 행동 사다리의 시간 전개 (§3 축2) ──
    # 축1의 reactions_by_id 가 출발점(시딩) — 축2는 이 기록을 수정하지 않는다(역류 금지).
    axis2_spec = dict(spec) if spec else None
    if axis2_spec is not None:
        axis2_spec.setdefault("text", display_policy)
    contrast = run_contrast_sim(
        [display_policy], view.get("personas") or [],
        grounded=grounded, mock=mock,
        specs=[axis2_spec] if axis2_spec else None,
        reactions_by_id=view.get("reactions_by_id"),
    )
    ckpt["axis2"] = {
        "sig": {"policy": display_policy, "mock": mock, "grounded": grounded},
        "contrast": contrast,
    }
    view["selection"] = contrast.get("selection") or {}
    view["village"] = contrast.get("village") or {}
    view["policies"] = [display_policy]

    # ── 축3 — 요약·개선: t0×시계열 읽기 전용 집계 (§3 축3) ──
    # 코드 집계뿐(LLM 0·공짜)이라 체크포인트 없이 매번 다시 센다.
    from axis3 import aggregate_axis3  # 지연 import(임포트 체인 경량 유지)
    view["axis3"] = aggregate_axis3(
        view.get("reactions_by_id"), view.get("village"),
        view.get("personas"), contrast.get("specs") or None,
    )
    _adopt_axis3_metrics(view)  # 게이지 3키 = 축3 산출(단일 진실원, v1.2)

    st.session_state[PIPELINE_CKPT_KEY] = ckpt
    st.session_state["sim"] = sim
    st.session_state["view"] = view
    return sim, view


# =====================================================================
# 데모 스냅샷(녹화 재생) — 실 LLM 1회 녹화 → 데모 모드 0콜 재생
# =====================================================================
# 미리마을의 "녹화방송" 철학을 메인 앱 데모로 가져온 것: 샘플 정책을
# _record_demo.py 가 실 모델로 1회 완주해 저장하면, 데모 모드에서 그 결과를
# 그대로 재생한다(발표 안전망 + 합성 mock 보다 진짜 질감). 합성 mock(ui/mock.py)은
# 직접 입력 정책 폴백 + 키리스 테스트 인프라로 그대로 남는다.
DEMO_SNAPSHOT_DIR = Path(__file__).resolve().parents[1] / "data" / "demo_snapshots"


def demo_snapshot_path(name: str) -> Path:
    """샘플 정책명 → 스냅샷 파일 경로(존재 보장 없음)."""
    return DEMO_SNAPSHOT_DIR / f"{name}.json"


def has_demo_snapshot(name: str) -> bool:
    """해당 샘플 정책의 녹화 스냅샷이 있는지(없으면 합성 mock 경로로)."""
    try:
        return demo_snapshot_path(name).is_file()
    except OSError:
        return False


def restore_snapshot(snap: dict) -> tuple:
    """스냅샷 dict → (sim, view, ckpt). 순수(streamlit 무의존 — 테스트 가능).

    run_full_pipeline 의 조립 순서(build_view → 축2 결과 얹기 → 축3 집계 →
    지표 채택)를 그대로 미러링해, 녹화 재생이 실 실행과 같은 모양임을 보장한다.
    축3는 코드 집계(LLM 0)라 저장본 대신 매번 다시 센다 — 단일 소스 유지.
    """
    from ui.model import build_view  # 지연 import(ui 계층 순환 방지)
    from axis3 import aggregate_axis3

    sim = dict(snap.get("sim") or {})
    contrast = dict(snap.get("contrast") or {})
    stamp = str(snap.get("llm_model") or sim.get("llm_model") or "")
    if stamp:
        sim["llm_model"] = f"{stamp} (녹화 재생)"
    display_policy = (sim.get("policy") or "").strip()

    view = build_view(sim)
    view["selection"] = contrast.get("selection") or {}
    view["village"] = contrast.get("village") or {}
    view["policies"] = [display_policy]
    view["axis3"] = aggregate_axis3(
        view.get("reactions_by_id"), view.get("village"),
        view.get("personas"), contrast.get("specs") or None,
    )
    _adopt_axis3_metrics(view)

    # 층1 체크포인트도 복원 — 단 sig.mock=True 로 박는다: 녹화본 세션에서
    # 파생 재실행(인생극장만 다시 등)이 실콜로 새지 않게 데모 취급(0콜 보증).
    ckpt = {
        "axis1": {
            "sig": {"policy": snap.get("model_policy") or display_policy,
                    "n": snap.get("n"), "seed": snap.get("seed"),
                    "mock": True, "grounded": True, "rounds": 1},
            "sim": sim,
        },
        "axis2": {
            "sig": {"policy": display_policy, "mock": True, "grounded": True},
            "contrast": contrast,
        },
    }
    return sim, view, ckpt


def load_demo_snapshot(name: str) -> tuple | None:
    """녹화 스냅샷을 불러와 세션에 반영(run_full_pipeline 과 같은 저장 모양).

    파일이 없거나 깨졌으면 None — 호출측은 기존 합성 mock 경로로 폴백한다.
    """
    try:
        snap = json.loads(demo_snapshot_path(name).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(snap, dict) or not snap.get("sim"):
        return None
    sim, view, ckpt = restore_snapshot(snap)
    st.session_state[PIPELINE_CKPT_KEY] = ckpt
    st.session_state["sim"] = sim
    st.session_state["view"] = view
    return sim, view


def rerun_from_axis2(
    grounded: bool = True,
    mock: bool | None = None,
    step_labels: list | None = None,
) -> tuple | None:
    """인생극장만 다시 — 층1 체크포인트의 축1 결과를 재사용해 축2부터 재실행한다.

    축1 전수 react 호출이 통째로 절약된다(§6 층1). t0 기록(sim·reactions)은
    그대로 두고 축2 산출물(selection/village)만 갱신한다(단방향 — 역류 금지).

    Args:
        mock: None 이면 축1 체크포인트와 같은 모드(출처 일관). 명시하면 그 값.

    Returns:
        (sim, view) 갱신본. 축1 체크포인트가 없으면 None(사이드바 전체 실행이 먼저).
    """
    from ui.model import build_view  # 지연 import(ui 계층 순환 방지)

    ckpt = st.session_state.get(PIPELINE_CKPT_KEY) or {}
    ax1 = ckpt.get("axis1") or {}
    sim = ax1.get("sim")
    if not sim:
        return None
    if mock is None:
        mock = bool((ax1.get("sig") or {}).get("mock", False))

    view = st.session_state.get("view") or build_view(sim)
    display_policy = (view.get("policy") or "").strip()
    spec = dict(view.get("policy_spec") or {})
    if spec:
        spec.setdefault("text", display_policy)

    contrast = run_contrast_sim(
        [display_policy], view.get("personas") or [],
        grounded=grounded, mock=mock, step_labels=step_labels,
        specs=[spec] if spec else None,
        reactions_by_id=view.get("reactions_by_id"),
    )
    ckpt["axis2"] = {
        "sig": {"policy": display_policy, "mock": mock, "grounded": grounded},
        "contrast": contrast,
    }
    view["selection"] = contrast.get("selection") or {}
    view["village"] = contrast.get("village") or {}
    view["policies"] = [display_policy]

    # 축2가 바뀌었으니 축3(읽기 전용 집계)도 다시 센다 — 코드뿐이라 공짜.
    from axis3 import aggregate_axis3  # 지연 import(임포트 체인 경량 유지)
    view["axis3"] = aggregate_axis3(
        view.get("reactions_by_id"), view.get("village"),
        view.get("personas"), contrast.get("specs") or None,
    )
    _adopt_axis3_metrics(view)  # 게이지 3키 = 축3 산출(단일 진실원, v1.2)

    st.session_state[PIPELINE_CKPT_KEY] = ckpt
    st.session_state["view"] = view
    return sim, view
