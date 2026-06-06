import base64

from ui.tab_chat import (
    _analyze_debate_insights,
    _build_debate_messages,
    _can_use_llm_debate_insights,
    _default_debate_count,
    _message_topic,
    _policy_domain,
    _render_chat_frame,
    _render_debate_loading_html,
    _render_debate_summary_html,
)
import ui.tab_chat as chat
from sample_policies import SAMPLES


def _persona(pid, name, age=26, occupation="사무 보조원", housing="아파트"):
    return {
        "id": pid,
        "name": name,
        "description": f"{age}세 · {occupation} · {housing}",
        "demographics": {
            "age": age,
            "occupation": occupation,
            "housing_type": housing,
            "family_type": "1인 가구",
        },
        "signals": {
            "digital_literacy": 0.55,
            "government_trust": 0.5,
        },
    }


def _reaction(pid, stance, text):
    return {
        "persona_id": pid,
        "stance": stance,
        "text": text,
        "scores": {"shareability": 70},
        "actions": ["대상 여부 확인"],
    }


def _view():
    personas = [
        _persona("p1", "김은서", 26, "주방 보조원", "아파트"),
        _persona("p2", "신민재", 24, "사무 보조원", "아파트"),
        _persona("p3", "조유정", 31, "간호조무사", "오피스텔"),
        _persona("p4", "심석현", 26, "사무 보조원", "고시원"),
        _persona("p5", "정명숙", 60, "무직", "아파트"),
        _persona("p6", "박성인", 46, "자영업", "다세대주택"),
        _persona("p7", "장원주", 66, "무직", "아파트"),
        _persona("p8", "이준영", 41, "배송 기사", "반전세"),
    ]
    reactions = [
        _reaction("p1", "support", "월 최대 20만 원, 12개월 지원은 월세 부담을 줄여줘서 좋아요."),
        _reaction("p2", "mixed", "부모 원가구 소득 기준과 무주택 조건을 먼저 확인해야 해요."),
        _reaction("p3", "support", "복지로 온라인 신청과 행정복지센터 방문 신청이 같이 있으면 편해요."),
        _reaction("p4", "oppose", "임대차계약서, 소득 증빙 서류, 통장 사본 준비가 복잡해 보여요."),
        _reaction("p5", "oppose", "상시 접수라도 예산 소진으로 조기 마감될 수 있으면 불안해요."),
        _reaction("p6", "mixed", "사업소득자는 소득 산정 기준과 제출 서류가 애매할 수 있어요."),
        _reaction("p7", "oppose", "온라인 신청만 강조하면 방문 창구를 못 찾는 사람이 생겨요."),
        _reaction("p8", "mixed", "전세나 반전세처럼 월세가 섞인 경우 지원 금액 기준이 궁금해요."),
    ]
    return {
        "policy": "청년 월세 한시 특별지원",
        "personas": personas,
        "reactions": reactions,
    }


def _domain_view(policy_name, reaction_texts):
    base = _view()
    reactions = []
    stances = ["support", "mixed", "oppose", "mixed", "support", "oppose", "mixed", "support"]
    for idx, text in enumerate(reaction_texts):
        pid = f"p{idx + 1}"
        reactions.append(_reaction(pid, stances[idx % len(stances)], text))
    base["policy"] = SAMPLES[policy_name]
    base["reactions"] = reactions
    return base


def test_message_topic_prefers_specific_signal_over_generic_condition_words():
    assert _message_topic("월 최대 20만 원, 12개월 지원 조건이 궁금해요") == "amount"
    assert _message_topic("임대차계약서와 소득 증빙 서류 제출 조건이 헷갈려요") == "documents"
    assert _message_topic("복지로 온라인 신청과 방문 신청 경로가 같이 보여야 해요") == "access"
    assert _message_topic("상시 접수라도 예산 소진 조기 마감 가능성이 문제예요") == "deadline"


def test_debate_summary_keeps_multiple_issues_and_actions():
    view = _view()
    messages = _build_debate_messages(view, _default_debate_count(view))
    insights = _analyze_debate_insights(view, messages)

    topics = {item["topic"] for item in insights["key_issues"]}
    assert len(messages) == 24
    assert len(topics) >= 4, topics
    assert "general" not in topics or len(topics) >= 5
    assert len(insights["improvement_points"]) >= 3
    assert len(insights["problem_points"]) >= 3


def test_next_actions_are_not_single_item_when_only_one_issue_is_detected():
    html = _render_debate_summary_html(
        {
            "key_issues": [
                {
                    "issue": "정책 문구",
                    "topic": "general",
                    "count": 24,
                    "pressure": "논쟁",
                    "problem": "정책 취지는 보이지만 다음 단계가 흩어져 있습니다.",
                    "suggestion": "신청자가 바로 판단할 조건을 먼저 배치",
                    "sample": "좋은 취지보다 내가 바로 판단할 수 있는 안내가 먼저예요.",
                }
            ],
            "problem_points": [
                {
                    "issue": "정책 문구",
                    "problem": "정책 취지는 보이지만 다음 단계가 흩어져 있습니다.",
                }
            ],
            "improvement_points": [
                {
                    "issue": "정책 문구",
                    "suggestion": "신청자가 바로 판단할 조건을 먼저 배치",
                }
            ],
            "stance_changes": [],
        }
    )
    next_actions = html.split('<div class="next-actions">', 1)[1]
    assert next_actions.count("<li>") >= 3
    assert "재검증" in next_actions
    assert "게시판 반영" in next_actions


def test_failed_reactions_do_not_surface_as_sns_response_failure():
    view = _domain_view(
        "어르신 디지털 금융 교육 및 기기 지원",
        ["(응답 생성 실패)"] * 8,
    )
    messages = _build_debate_messages(view, _default_debate_count(view))
    joined = "\n".join(str(msg.get("text") or "") for msg in messages)
    insights = _analyze_debate_insights(view, messages)

    assert "응답 생성 실패" not in joined
    assert _policy_domain(view) == "digital"
    assert any(item["issue"] in {"방문·전화 접수", "교육·기기 지원", "분기 모집·정원"} for item in insights["key_issues"])


def test_policy_domains_produce_different_improvement_reports():
    digital_view = _domain_view(
        "어르신 디지털 금융 교육 및 기기 지원",
        [
            "전화나 방문 접수 위치가 먼저 보여야 해요.",
            "8주 교육과 태블릿 대여 조건이 헷갈려요.",
            "분기별 모집 정원과 대기 안내가 필요해요.",
            "자녀가 대리 신청할 때 확인 절차가 궁금해요.",
        ] * 2,
    )
    birth_view = _domain_view(
        "출산 가구 첫만남 이용권",
        [
            "200만 원 바우처 사용처와 사용 기한이 궁금해요.",
            "출생신고와 행복출산 원스톱 신청이 연결되는지 봐야 해요.",
            "보호자와 아동 주소가 다르면 별도 확인이 필요해 보여요.",
            "국민행복카드 포인트가 어디서 제한되는지 알려줘야 해요.",
        ] * 2,
    )
    emergency_view = _domain_view(
        "저소득 위기가구 긴급 생활지원",
        [
            "실직이나 질병 같은 위기 사유가 어디까지 인정되는지 궁금해요.",
            "소득 재산 증빙 자료를 긴급 상황에서 준비하기 어려워요.",
            "129 전화와 행정복지센터 중 어디로 먼저 가야 하나요.",
            "사후 조사에서 환수될 수 있다는 말이 신청을 망설이게 해요.",
        ] * 2,
    )

    labels_by_domain = {}
    for label, view in {
        "digital": digital_view,
        "birth": birth_view,
        "emergency": emergency_view,
    }.items():
        messages = _build_debate_messages(view, _default_debate_count(view))
        insights = _analyze_debate_insights(view, messages)
        labels_by_domain[label] = {item["issue"] for item in insights["key_issues"]}

    assert "교육·기기 지원" in labels_by_domain["digital"] or "방문·전화 접수" in labels_by_domain["digital"]
    assert "바우처 금액·사용처" in labels_by_domain["birth"] or "사용 기한" in labels_by_domain["birth"]
    assert "위기 사유·소득 기준" in labels_by_domain["emergency"] or "환수 위험" in labels_by_domain["emergency"]
    assert labels_by_domain["digital"] != labels_by_domain["birth"]
    assert labels_by_domain["birth"] != labels_by_domain["emergency"]


def test_react_node_failure_uses_natural_policy_fallback():
    import graph.nodes as nodes

    original = nodes.structured_call

    def boom(*_args, **_kwargs):
        raise RuntimeError("forced failure")

    nodes.structured_call = boom
    try:
        result = nodes.react_node(
            {
                "policy": SAMPLES["저소득 위기가구 긴급 생활지원"],
                "personas": [_persona("p1", "김은서")],
                "grounded": True,
            }
        )
    finally:
        nodes.structured_call = original

    reaction = result["reactions"][0]
    assert reaction["fallback"] is True
    assert "응답 생성 실패" not in reaction["text"]
    assert "긴급 생계" in reaction["text"]


def test_openai_analysis_uses_uploaded_policy_document_context():
    view = _view()
    view["policy"] = "청년 예술인 창작준비금 지원 정책"
    view["policy_documents"] = [
        {
            "name": "artist-policy.md",
            "text": (
                "신청 대상: 만 19~39세 예술활동증명 완료자. "
                "지원 내용: 창작준비금 300만 원. "
                "유의 사항: 최근 2년 내 동일 사업 수혜자는 제외되며, "
                "창작활동 계획서와 예술활동 증빙을 제출해야 합니다."
            ),
        }
    ]
    messages = [
        {
            "from_id": "p1",
            "round": 1,
            "text": "창작활동 계획서랑 예술활동 증빙을 어디까지 내야 하는지 모르겠어요.",
            "stance": "mixed",
        }
    ]

    calls = []
    original_key = chat.has_real_key
    original_call = chat.structured_call
    if hasattr(chat._cached_llm_debate_insights, "clear"):
        chat._cached_llm_debate_insights.clear()

    def fake_has_real_key():
        return True

    def fake_structured_call(messages_arg, schema, temperature=0.0):
        joined = "\n".join(m["content"] for m in messages_arg)
        calls.append(joined)
        assert "artist-policy.md" in joined
        assert "창작준비금 300만 원" in joined
        assert "예술활동 증빙" in joined
        return chat._LLMDebateInsights(
            verdict="창작활동 증빙과 중복 수혜 제외 조건을 먼저 정리해야 합니다.",
            key_issues=[
                chat._LLMIssue(
                    issue="예술활동 증빙 범위",
                    count=1,
                    pressure="논쟁",
                    problem="창작활동 계획서와 예술활동 증빙의 인정 범위가 불명확합니다.",
                    suggestion="증빙 예시, 불인정 사례, 제출 양식을 한 표로 제공합니다.",
                    sample="창작활동 계획서랑 예술활동 증빙을 어디까지 내야 하는지 모르겠어요.",
                )
            ],
            stance_changes=[],
        )

    chat.has_real_key = fake_has_real_key
    chat.structured_call = fake_structured_call
    try:
        insights = _analyze_debate_insights(view, messages, use_llm=True)
    finally:
        chat.has_real_key = original_key
        chat.structured_call = original_call
        if hasattr(chat._cached_llm_debate_insights, "clear"):
            chat._cached_llm_debate_insights.clear()

    assert calls
    assert insights["analysis_mode"] == "openai"
    assert insights["key_issues"][0]["issue"] == "예술활동 증빙 범위"
    assert "증빙 예시" in insights["key_issues"][0]["suggestion"]


def test_debate_loading_html_explains_openai_analysis_progress():
    view = _view()
    messages = _build_debate_messages(view, _default_debate_count(view))
    html = _render_debate_loading_html(view, messages)

    assert "SNS 채팅 구성 중" in html
    assert "OpenAI" in html
    assert "정책 원문" in html
    assert "시민 발언 정렬" in html
    assert f"{len(messages)}개 SNS 발언" in html
    assert "debate-loading-skeleton" in html


def test_llm_debate_loading_condition_requires_key_and_context():
    view = _view()
    messages = _build_debate_messages(view, _default_debate_count(view))
    original_key = chat.has_real_key

    chat.has_real_key = lambda: False
    try:
        assert _can_use_llm_debate_insights(view, messages) is False
    finally:
        chat.has_real_key = original_key

    chat.has_real_key = lambda: True
    try:
        assert _can_use_llm_debate_insights(view, messages) is True
        assert _can_use_llm_debate_insights({"policy": ""}, messages) is False
    finally:
        chat.has_real_key = original_key


def test_chat_frame_uses_data_url_iframe_for_html_content():
    calls = []
    original_iframe = chat.st.iframe

    def fake_iframe(src, height=None):
        calls.append({"src": src, "height": height})

    chat.st.iframe = fake_iframe
    try:
        _render_chat_frame("<!doctype html><html><body>SNS</body></html>")
    finally:
        chat.st.iframe = original_iframe

    assert calls
    assert calls[0]["height"] == 730
    assert calls[0]["src"].startswith("data:text/html;charset=utf-8;base64,")
    payload = calls[0]["src"].split(",", 1)[1]
    decoded = base64.b64decode(payload).decode("utf-8")
    assert "SNS" in decoded


if __name__ == "__main__":
    test_message_topic_prefers_specific_signal_over_generic_condition_words()
    test_debate_summary_keeps_multiple_issues_and_actions()
    test_next_actions_are_not_single_item_when_only_one_issue_is_detected()
    test_failed_reactions_do_not_surface_as_sns_response_failure()
    test_policy_domains_produce_different_improvement_reports()
    test_react_node_failure_uses_natural_policy_fallback()
    test_openai_analysis_uses_uploaded_policy_document_context()
    test_debate_loading_html_explains_openai_analysis_progress()
    test_llm_debate_loading_condition_requires_key_and_context()
    test_chat_frame_uses_data_url_iframe_for_html_content()
    print("ALL PASS")
