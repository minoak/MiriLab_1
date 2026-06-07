"""미리랩 - 정책 반응 시뮬레이터 (오케스트레이터/엔트리포인트).

이 파일은 Streamlit 앱의 최상위 진입점이다.
- 한글 폰트 설정 후 페이지 설정/타이틀을 그린다.
- 사이드바에서 정책 선택·시민 수·데모 모드를 받고, 버튼 클릭 시 시뮬레이션을 실행한다.
- 실행 결과(SimState)와 그 뷰모델(ViewModel)을 session_state 에 저장한다.
- 본문은 7개 탭으로 구성되며, 각 탭은 해당 render_*_tab(view) 를 호출한다.

주의: import 시점에는 네트워크/OpenAI 호출이 절대 일어나지 않는다.
실제 호출은 '시뮬레이션 실행' 버튼을 눌렀을 때만 run_simulation 내부에서 발생한다.
"""

# --- 최상단: 한글 폰트 → 페이지 설정 → 타이틀 (이 순서 고정) ---
from viz import set_korean_font

set_korean_font()

import streamlit as st

st.set_page_config(page_title="미리랩 - 정책 반응 시뮬레이터", layout="wide")
st.title("미리랩 — 정책 반응 시뮬레이터")

# --- 나머지 import (계약상 정해진 공개 API만 사용) ---
from urllib.parse import urlparse

from sample_policies import SAMPLES, DEFAULT_POLICY, SPECS, SOURCES
from ui.state_helpers import (
    run_full_pipeline, PIPELINE_CKPT_KEY,
    has_demo_snapshot, load_demo_snapshot,
)
from graph import llm as llm_mod
from graph.llm import has_real_key
from graph.spaces import PLACES
from policy_spec import spec_from_tags, prompt_with_tags
from ui import (
    tab_input,
    tab_dashboard,
    tab_village,
    tab_chat,
    tab_improve,
    tab_board,
    tab_minivillage,
)


# =====================================================================
# 정책 태그 옵션 (UI 라벨 ↔ 엔진 코드) — 사이드바 셀렉터용
# =====================================================================
# 소득 수준: 표시 라벨 → signals.income_level 코드
_INCOME_OPTIONS = {"저소득": "low", "중간소득": "mid", "고소득": "high"}
# 가구 조건: 표시 라벨 → family_type 에 포함돼야 할 키워드(None=무관)
_FAMILY_OPTIONS = {
    "무관": None, "자녀 있음": "자녀", "배우자 있음": "배우자",
    "1인 가구": "1인", "부모 부양": "부모",
}
# 주 신청 채널: 한글 장소명 → spaces.PLACE_KEYS (PLACES 순서 유지)
_CHANNEL_OPTIONS = {p["name"]: p["key"] for p in PLACES}
# 분류 태그(매칭엔 미사용, 프롬프트 힌트 + 미래 RAG 라벨). "미지정"=빈 값.
_CATEGORY_OPTIONS = [
    "미지정", "주거", "고용", "돌봄·보육", "노후", "생계·긴급",
    "교육", "금융·자산", "건강",
]
_SUPPORT_OPTIONS = ["미지정", "현금", "바우처", "현물·기기", "서비스·교육", "감면"]
# 콤보박스 '직접 입력' 옵션 라벨 — 분야/지원형태/채널에서 목록 밖 값을 받기 위함.
_OTHER_OPTION = "기타 (직접 입력)"

# =====================================================================
# 시민 구성 필터 옵션 — 데이터셋(Nemotron-Personas-Korea) 원본 표기 기준
# =====================================================================
# 필터 값은 데이터셋 표기 그대로 보내고(빗나감 방지), 화면에는 익숙한 라벨을 입힌다.
# 성별: 표시 라벨 → 데이터셋 값('여자'/'남자')
_SEX_OPTIONS = {"여성": "여자", "남성": "남자"}
# 시·도: 표준 순서, 값 = 데이터셋 표기('경상남'·'전라남'·'전북' 식 축약 — 원본 그대로)
_PROVINCES = [
    "서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종",
    "경기", "강원", "충청북", "충청남", "전북", "전라남", "경상북", "경상남", "제주",
]
# 화면용 약칭(나머지는 원본 표기 그대로 표시)
_PROVINCE_LABELS = {
    "충청북": "충북", "충청남": "충남", "전라남": "전남",
    "경상북": "경북", "경상남": "경남",
}
# 연령 슬라이더 전체 범위 — 데이터셋은 19~99세 성인. 전체 범위 = 필터 없음.
_AGE_FULL = (19, 99)


# =====================================================================
# 사이드바: 입력 컨트롤 + 실행 트리거
# =====================================================================
def _render_sidebar() -> None:
    """사이드바를 그리고, '실행' 버튼이 눌리면 시뮬레이션을 수행한다.

    - 정책 선택 selectbox: 샘플 정책명 + '직접 입력'.
    - text_area: 선택한 샘플 원문을 프리필(직접 입력이면 빈칸).
    - 시민 수 number_input(8~30, 기본 24) + 추첨 시드(기본 42).
    - 시민 구성 expander(선택): 연령대·성별·지역 — 표본 풀을 좁힌 뒤 추첨.
    - 데모 모드 checkbox(키 없으면 기본 체크).
    - 실행 버튼 클릭 시 run_simulation → build_view 결과를 session_state 저장.
    """
    with st.sidebar:
        st.header("시뮬레이션 설정")

        # 1) 정책 선택 ---------------------------------------------------
        policy_names = list(SAMPLES)
        options = policy_names + ["직접 입력"]
        # 기본 선택: DEFAULT_POLICY 가 샘플 목록에 있으면 그것을, 없으면 첫 항목.
        try:
            default_index = options.index(DEFAULT_POLICY)
        except ValueError:
            default_index = 0
        choice = st.selectbox("정책 선택", options, index=default_index)

        # 2) 선택에 따른 원문 프리필 ------------------------------------
        if choice == "직접 입력":
            prefill = ""
        else:
            prefill = SAMPLES.get(choice, "")

        # selectbox 선택이 바뀌면 text_area 가 새 원문으로 갱신되도록
        # key 에 선택값을 포함시킨다(선택 변경 = 위젯 재생성 → 프리필 반영).
        policy_text = st.text_area(
            "정책 원문",
            value=prefill,
            height=260,
            key=f"policy_text::{choice}",
            help="샘플을 고르면 원문이 채워집니다. '직접 입력'을 고르면 직접 작성하세요.",
        )

        # 원문 출처 — 샘플 정책이면 모델이 된 실존 정책의 공식 사이트를
        # 원문 바로 아래에 같이 적어 준다(직접 입력은 출처 없음).
        if choice != "직접 입력":
            src = SOURCES.get(choice) or {}
            urls = src.get("urls") or []
            if urls:
                links = " · ".join(
                    f"[{urlparse(u).netloc or u}]({u})" for u in urls
                )
                st.caption(f"📚 원문 출처: {links}")

        # 3) 시민 수 · 추첨 시드 ------------------------------------------
        col_n, col_seed = st.columns(2)
        with col_n:
            n = st.number_input(
                "시민 수",
                min_value=8,
                max_value=30,
                value=24,
                step=1,
                help="시뮬레이션에 참여할 가상 시민(페르소나) 수입니다.",
            )
        with col_seed:
            seed = st.number_input(
                "추첨 시드",
                min_value=0,
                value=42,
                step=1,
                help="시민을 뽑는 난수 시드입니다. 바꾸면 같은 조건에서 다른 "
                     "시민들이 추첨됩니다(같은 시드 = 같은 시민, 재현 가능). "
                     "기본 42 = 지금까지의 검증·녹화 데모와 같은 시민 풀. "
                     "데모 모드에는 적용되지 않습니다.",
            )

        # 3.2) 시민 구성 필터(선택) ---------------------------------------
        # '마을에 누가 사는가' — 표본 풀(첫 샤드 111,112명)을 인구 조건으로
        # 좁힌 뒤 그 안에서 n명을 추첨한다. 정책 태그의 '대상 연령'(정책이
        # 겨냥하는 사람)과는 별개. 실모드 전용(데모는 합성/녹화 재생이라 무관).
        with st.expander("👥 시민 구성 (선택 — 어떤 시민을 모을까)", expanded=False):
            st.caption(
                "비워두면 전국·전연령에서 무작위로 모읍니다. 조건을 걸면 같은 "
                "정책을 다른 동네(예: 고령 마을 vs 청년 도시)에 투입해 비교할 수 "
                "있습니다. 데모 모드(합성·녹화 재생)에는 적용되지 않습니다."
            )
            comp_age = st.slider(
                "연령대", _AGE_FULL[0], _AGE_FULL[1], _AGE_FULL,
                key="comp_age",
                help="시민의 나이 범위입니다(데이터셋은 19~99세 성인). 정책 태그의 "
                     "'대상 연령'은 정책이 겨냥하는 사람, 이쪽은 마을 주민 구성입니다.",
            )
            comp_sex = st.selectbox(
                "성별", ["무관"] + list(_SEX_OPTIONS), index=0, key="comp_sex",
            )
            comp_prov = st.multiselect(
                "지역(시·도)", _PROVINCES, default=[],
                key="comp_prov",
                format_func=lambda p: _PROVINCE_LABELS.get(p, p),
                help="비워두면 전국. 고르면 그 시·도에 사는 시민만 모읍니다.",
            )

        # 3.5) 시민 모델(LLM 선택) ---------------------------------------
        # 키가 설정된 프로바이더만 선택지로. 선택 즉시 set_provider 로 전환돼
        # 이후 모든 시민 시뮬 호출(반응/전파/집계/인생극장/리포트)이 이 모델로
        # 나가고, 미리마을 생성도 따라간다(tab_minivillage 가 동기화).
        # 게시판 RAG 는 별도(OpenAI 고정). 기본 선택 = .env 의 MIRILAB_LLM.
        providers = llm_mod.available_providers()
        if providers:
            _prov_org = {"openai": "OpenAI", "gemini": "Google"}
            default_provider = (llm_mod.PROVIDER if llm_mod.PROVIDER in providers
                                else providers[0])
            sel_provider = st.selectbox(
                "시민 모델",
                providers,
                index=providers.index(default_provider),
                format_func=lambda p: (
                    f"{llm_mod.PROVIDER_MODELS[p]} ({_prov_org.get(p, p)})"
                ),
                key="llm_provider",
                help="시민 반응을 생성할 LLM 입니다. .env 에 키가 있는 모델만 보입니다. "
                     "모델이 다르면 점수 분포도 달라지므로, 결과 비교는 같은 모델끼리만.",
            )
            llm_mod.set_provider(sel_provider)

        # 4) 데모 모드 ---------------------------------------------------
        real_key = has_real_key()
        demo = st.checkbox(
            "데모 모드(키 없이 모의 데이터)",
            value=not real_key,
            help="체크하면 LLM 호출 없이 모의 데이터로 화면을 채웁니다.",
        )
        if not real_key:
            st.caption(
                "LLM 키가 설정되지 않아 데모 모드를 권장합니다. 실제 시민 반응을 "
                "보려면 .env 에 OPENAI_API_KEY 또는 GEMINI_API_KEY 를 설정하세요."
            )

        # 4.5) 정책 태그(선택) ------------------------------------------
        # 정책의 대상·분류를 직접 지정한다. 지정한 태그는 (1) 정책 원문과 함께
        # 모델에 전달되고(더 정확한 반응), (2) 결정론 spec 으로 저장돼 인생극장
        # 대상 선별을 또렷하게 하며, (3) 미래 RAG 의 라벨이 된다.
        # 샘플 정책을 고르면 검증된 명세(SPECS)로 자동 프리필되고, 위젯 key 에
        # 선택값을 포함시켜 정책을 바꾸면 태그도 그 정책에 맞게 갱신된다.
        sp = SPECS.get(choice)  # 샘플이면 명세, '직접 입력'/미등록이면 None
        with st.expander("🏷️ 정책 태그 (선택 — 대상·분류 직접 지정)", expanded=False):
            st.caption(
                "비워두면 자동 추정합니다. 지정하면 모델에 함께 전달되고 인생극장 "
                "대상 선별이 또렷해집니다."
            )
            # 대상 연령
            def_age = tuple(sp["age"]) if sp else (0, 120)
            age_sel = st.slider(
                "대상 연령", 0, 120, def_age, key=f"tag_age::{choice}"
            )
            # 소득 수준(다중) — 전부 선택 = 소득무관
            inc_labels = list(_INCOME_OPTIONS)
            if sp:
                def_inc = [l for l, c in _INCOME_OPTIONS.items()
                           if c in (sp.get("income") or ())]
                def_inc = def_inc or inc_labels
            else:
                def_inc = inc_labels
            inc_sel = st.multiselect(
                "소득 수준", inc_labels, default=def_inc, key=f"tag_income::{choice}"
            )
            # 가구 조건
            fam_labels = list(_FAMILY_OPTIONS)
            if sp and sp.get("family_kw"):
                def_fam = next((l for l, c in _FAMILY_OPTIONS.items()
                                if c == sp["family_kw"]), "무관")
            else:
                def_fam = "무관"
            fam_sel = st.selectbox(
                "가구 조건", fam_labels, index=fam_labels.index(def_fam),
                key=f"tag_family::{choice}",
            )
            # 주 신청 채널
            ch_labels = list(_CHANNEL_OPTIONS)
            if sp:
                def_ch = next((l for l, c in _CHANNEL_OPTIONS.items()
                               if c == sp.get("channel")), ch_labels[0])
            else:
                def_ch = next((l for l, c in _CHANNEL_OPTIONS.items()
                               if c == "community_center"), ch_labels[0])
            ch_pick = st.selectbox(
                "주 신청 채널", ch_labels + [_OTHER_OPTION],
                index=ch_labels.index(def_ch), key=f"tag_channel::{choice}",
            )
            if ch_pick == _OTHER_OPTION:
                ch_value = st.text_input(
                    "주 신청 채널 직접 입력", key=f"tag_channel_custom::{choice}",
                    placeholder="예: 전화 상담(129)",
                ).strip()
                st.caption(
                    "※ 직접 입력한 채널은 태그·모델 힌트로만 쓰이고, 인생극장 지도의 "
                    "5개 공간에는 추가되지 않습니다."
                )
            else:
                ch_value = _CHANNEL_OPTIONS.get(ch_pick)

            # 분류 태그(매칭엔 미사용 — RAG 라벨/프롬프트 힌트). 목록 밖 값은 직접 입력.
            cat_pick = st.selectbox(
                "정책 분야", _CATEGORY_OPTIONS + [_OTHER_OPTION], index=0,
                key=f"tag_cat::{choice}",
            )
            if cat_pick == _OTHER_OPTION:
                cat_sel = st.text_input(
                    "정책 분야 직접 입력", key=f"tag_cat_custom::{choice}",
                    placeholder="예: 교통·이동",
                ).strip()
            else:
                cat_sel = cat_pick

            sup_pick = st.selectbox(
                "지원 형태", _SUPPORT_OPTIONS + [_OTHER_OPTION], index=0,
                key=f"tag_sup::{choice}",
            )
            if sup_pick == _OTHER_OPTION:
                sup_sel = st.text_input(
                    "지원 형태 직접 입력", key=f"tag_sup_custom::{choice}",
                    placeholder="예: 대출·융자",
                ).strip()
            else:
                sup_sel = sup_pick

        # 5) 실행 버튼 ---------------------------------------------------
        run_clicked = st.button(
            "시뮬레이션 실행", type="primary", width="stretch"
        )

    # --- 버튼 클릭 처리(사이드바 컨텍스트 밖에서 스피너 표시) ---------
    if run_clicked:
        policy = (policy_text or "").strip()
        if not policy:
            st.warning("정책 원문이 비어 있습니다. 샘플을 선택하거나 직접 입력해 주세요.")
            return

        # 데모 + 샘플 원문 그대로 + 녹화본 있음 + 녹화본의 원문도 현재 원문과 같음
        # → 실 LLM 녹화 스냅샷 재생(호출 0). 스냅샷 원문이 오래됐으면 SNS 채팅이
        # 과거 정책으로 만들어지므로 아래 합성 mock 경로로 흘려 현재 문안을 쓴다.
        if (demo and choice != "직접 입력"
                and policy == SAMPLES.get(choice, "").strip()
                and has_demo_snapshot(choice)):
            loaded = load_demo_snapshot(choice, expected_policy=policy)
            if loaded:
                _sim, _view = loaded
                # 새 정책으로 갈아탔으니 이전 A/B·리포트 무효화(아래 본 경로와 동일).
                st.session_state.pop("view_b", None)
                st.session_state.pop("abtest_policy_b", None)
                st.session_state.pop("improve_report", None)
                st.success(
                    "녹화된 실제 시뮬 결과를 재생했습니다 — LLM 호출 0 · "
                    f"시민 {len(_view.get('personas') or [])}명 · "
                    f"생성 모델: {_sim.get('llm_model', '')}"
                )
                st.session_state["main_tab"] = "시민 반응"
                return

        # 시민 구성 필터 — 기본값(전체 연령/무관/빈 지역)은 조건에서 빼서
        # '필터 없음'과 같은 캐시 키가 되게 한다(불필요한 재추첨 방지).
        filters = {}
        if tuple(comp_age) != _AGE_FULL:
            filters["age"] = [int(comp_age[0]), int(comp_age[1])]
        if comp_sex != "무관":
            filters["sex"] = _SEX_OPTIONS.get(comp_sex, comp_sex)
        if comp_prov:
            filters["provinces"] = list(comp_prov)
        filters = filters or None

        # 사용자 태그 → 결정론 spec(LLM/네트워크 0). 모델엔 '태그 + 원문'을 보낸다.
        income_codes = [_INCOME_OPTIONS[l] for l in inc_sel if l in _INCOME_OPTIONS]
        spec = spec_from_tags(
            age=tuple(age_sel),
            income=income_codes,
            family_kw=_FAMILY_OPTIONS.get(fam_sel),
            channel=ch_value,
            category="" if cat_sel == "미지정" else cat_sel,
            support_type="" if sup_sel == "미지정" else sup_sel,
            name=("" if choice == "직접 입력" else choice),
            text=policy,
        )
        model_policy = prompt_with_tags(policy, spec)  # 모델 입력(태그 접두 + 원문)

        spinner_msg = (
            "모의 데이터를 생성하는 중입니다..."
            if demo
            else "시민 반응(축1) → 인생극장(축2) → 집계(축3)를 한 번에 실행 중입니다..."
        )
        with st.spinner(spinner_msg):
            try:
                # 한 버튼 = 축1→축2→축3 완주(설계방향서 §8-2). 단계 표시는
                # run_simulation/run_contrast_sim 안의 st.status 가 담당하고,
                # sim/view/층1 체크포인트 저장은 run_full_pipeline 이 한다.
                run_full_pipeline(
                    model_policy, policy=policy, spec=spec, mock=demo,
                    n=int(n), seed=int(seed), filters=filters,
                )
                # 새 정책으로 다시 시뮬했으니 이전 A/B 비교/후보와 종합 리포트를
                # 무효화한다(정책이 바뀌면 옛 정책 기준이라 표시가 착시가 됨).
                st.session_state.pop("view_b", None)
                st.session_state.pop("abtest_policy_b", None)
                st.session_state.pop("improve_report", None)
            except Exception as e:  # 실행 실패 시 화면을 깨뜨리지 않고 예외 표시.
                st.session_state["sim"] = None
                st.session_state["view"] = None
                st.session_state.pop(PIPELINE_CKPT_KEY, None)
                st.session_state.pop("view_b", None)
                st.session_state.pop("abtest_policy_b", None)
                st.session_state.pop("improve_report", None)
                st.error("시뮬레이션 실행 중 오류가 발생했습니다.")
                st.exception(e)
                return

        if demo:
            st.success("모의 데이터로 전체 파이프라인을 완료했습니다. 아래 탭에서 확인하세요.")
        else:
            st.success(
                "축1(시민 반응)→축2(인생극장)→축3(집계)를 완료했습니다. "
                "아래 탭에서 결과를 확인하세요."
            )
        # 시민 구성 필터로 풀이 좁아져 요청 인원보다 적게 모였으면 알린다
        # (조용한 축소 방지 — 결과 화면의 시민 수가 왜 다른지 설명).
        got = len(((st.session_state.get("view") or {}).get("personas")) or [])
        if not demo and filters and 0 < got < int(n):
            st.info(
                f"시민 구성 조건에 맞는 시민이 {got}명뿐이라 {got}명으로 진행했습니다."
            )
        st.session_state["main_tab"] = "시민 반응"


# =====================================================================
# 본문: 7개 결과 화면
# =====================================================================
def _render_body() -> None:
    """본문 결과 화면을 그린다. view 가 없으면 화면이 알아서 안내(st.info)한다."""
    tab_labels = [
        "정책 입력",
        "시민 반응",
        "정책 인생극장",
        "SNS 채팅방",
        "정책 개선",
        "게시판",
        "미리마을",
    ]
    view = st.session_state.get("view")

    current_tab = st.session_state.get("main_tab")
    if current_tab not in tab_labels:
        current_tab = tab_labels[0]
        st.session_state["main_tab"] = current_tab

    radio_kwargs = {
        "horizontal": True,
        "key": "main_tab",
        "label_visibility": "collapsed",
    }
    if "main_tab" not in st.session_state:
        radio_kwargs["index"] = tab_labels.index(current_tab)
    selected_tab = st.radio("결과 화면", tab_labels, **radio_kwargs)

    # 각 화면과 렌더 함수를 1:1로 매핑한다(라벨 순서와 동일).
    renderers = [
        tab_input.render_input_tab,
        tab_dashboard.render_dashboard_tab,
        tab_village.render_village_tab,
        tab_chat.render_chat_tab,
        tab_improve.render_improve_tab,
        tab_board.render_board_tab,
        tab_minivillage.render_minivillage_tab,
    ]

    render_fn = dict(zip(tab_labels, renderers))[selected_tab]
    try:
        render_fn(view)
    except Exception as e:  # 한 화면이 죽어도 앱 전체는 살아 있도록 격리.
        st.exception(e)


# =====================================================================
# 진입점
# =====================================================================
def main() -> None:
    _render_sidebar()
    _render_body()


main()
