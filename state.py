"""공유 State 스키마 = 팀 약속 (the team contract).

이 파일은 rag/, graph/, eval/, app.py, ui/ 사이의 인터페이스다.
기존 필드 이름은 절대 바꾸지 말 것. 새 필드는 추가만(additive) 한다.
모든 모듈은 정확히 이 키들을 읽고 쓴다.
"""
from typing import TypedDict, Annotated, Optional, NotRequired
from operator import add


class Scores(TypedDict):
    """시민 1명의 5축 점수 (0~100). 개요의 핵심 점수 체계."""
    understanding: int     # 이해도
    benefit: int           # 수혜 가능성
    intent: int            # 신청 의향
    dissatisfaction: int   # 불만도
    shareability: int      # 공유 가능성


class Persona(TypedDict):
    """가상 시민 1명. nvidia/Nemotron-Personas-Korea 한 행에서 매핑된다."""
    id: str            # uuid
    name: str          # UI 표시용 이름
    description: str   # 한 줄 요약 (예: "76세 여성 · 독거 · 무직 · 서울 서초구")
    sources: list      # grounding 근거 (RAG 사용 시 채워짐, MVP=[])
    # --- 확장 (옵션, 기본 {} / "") ---
    demographics: dict # sex/age/marital_status/family_type/housing_type/education_level/occupation/district/province
    persona_text: str  # HF 페르소나 텍스트 1~2개 필드를 합친 것 (프롬프트 주입용)
    signals: dict      # digital_literacy(float) / income_level(str) / government_trust(float) / social_network(list)
    meta: dict         # 프롬프트엔 안 넣는 나머지 HF 컬럼 (확장/툴팁용)


class Reaction(TypedDict):
    """시민 1명의 정책 반응."""
    persona_id: str
    stance: str        # 'support' | 'oppose' | 'mixed'
    text: str          # 생성된 반응 텍스트
    evidence: list     # grounding 스니펫 (RAG 사용 시)
    # --- 확장 ---
    scores: Scores     # 5축 점수
    actions: list      # 예상 행동: ['신청 시도','가족 공유','주민센터 문의','포기' ...]
    grounded: bool     # True=페르소나 grounding / False=ablation(일반 시민)


class Interaction(TypedDict):
    """전파(채팅) 1건. SNS 채팅방(게시판 댓글)의 원천."""
    round: int
    from_id: str
    to_id: Optional[str]        # None = 채팅방 전체 broadcast
    text: str
    stance_shift: Optional[str] # 다른 의견을 보고 입장이 바뀌었는지 (옵션)


class VillageStep(TypedDict):
    """한 주민의 한 시점(스텝) 삶. 미리 마을 시뮬의 최소 단위."""
    step: int
    label: str          # 시간 라벨 (예: "시행 3개월 후")
    place: str          # 이 시점 주민이 닿은 장소(정책 채널) — graph/spaces.PLACE_KEYS
    action: str         # 그 기간 이 주민의 행동·사건 (디테일 서사)
    policy_status: str  # unaware | aware | applied | received | blocked
    economic: int       # 경제적 여유 0~100
    wellbeing: int      # 심리적 안정·만족 0~100
    note: str           # 타임라인 한 줄 요약
    # --- 확장 (additive, 옵션) — 접근 '방향 추적' ---
    reached_via: NotRequired[str]  # 어떻게/누구를 통해 정책에 닿았나(경로·계기 한 줄)
    barrier: NotRequired[str]      # blocked 일 때 정확히 어디서 막혔는지(한 줄)


class Resident(TypedDict):
    """미리 마을 주민 1명의 누적 궤적(Persona 에서 파생)."""
    id: str
    name: str
    timeline: list      # list[VillageStep]
    policy_status: str  # 최종 정책 관여 상태
    economic: int       # 최종 경제 지표
    wellbeing: int      # 최종 심리 지표


class SpaceNode(TypedDict):
    """미리 마을 공간 트리의 노드 1개 (World→장소→오브젝트).

    각 장소는 '정책 접근 채널'의 의미를 갖는다(graph/spaces.py).
    어느 장소에 닿느냐가 곧 정책 접근 격차다.
    """
    name: str       # 장소명 (예: "복지로(온라인)")
    role: str       # 정책 채널로서의 의미 한 줄
    children: list  # list[SpaceNode] - 하위 장소(현재 1depth, 확장 여지)
    objects: list   # 장소 안 오브젝트/상태 자연어 (예: "복지로 앱: 로그인 복잡")
    state: dict     # 메타 (key/favored/barrier 등)


class SimState(TypedDict):
    """그래프 전체를 흐르는 상태."""
    policy: str                          # 시뮬레이션 대상 정책 원문
    personas: list                       # list[Persona]
    reactions: Annotated[list, add]      # list[Reaction] - 노드가 append
    interactions: Annotated[list, add]   # list[Interaction] - 전파 라운드
    summary: str                         # 갈등/합의 요약
    # --- 확장 ---
    grounded: bool                       # ablation 전역 토글 (기본 True)
    rounds: int                          # 전파 라운드 수 (기본 1, 최대 2)
    metrics: dict                        # 집계: 정책수용도/신청의향지수/사회혼란도 + 축별 평균
    improvements: dict                   # {'easy_text': str, 'policy_fixes': [str, ...]}
    edges: Annotated[list, add]          # (SNS 답글 참조) 전파 엣지: {'from':id,'to':id,'round':int}
    # --- 미리 마을: 정책 시행 후 시간 경과(스텝)별 각 주민의 삶 변화 시뮬 (전파 그래프 대체) ---
    village: dict                        # {steps, residents:[Resident...], aggregate} (graph/village.py)
    # --- 정책 인생극장(DESIGN v3): 멀티 정책 + 대조 3명 선별 ---
    policies: list                       # 동시 시행 정책 패키지(정책명/원문/{name,text} 리스트). 단일은 [policy].
    selection: dict                      # contrast.select_trio_from_outcomes 결과 {specs, trio, outcomes, notes}. (구 select_contrast_trio 매트릭스 선별은 dormant.)
    # --- 정책 태그(사이드바 직접 지정): 결정론 명세 + 분류 라벨 ---
    policy_spec: dict                    # policy_spec.spec_from_tags 결과 {name,text,age,income,family_kw,channel,category,support_type}. 매칭/프롬프트/미래 RAG 라벨용.
