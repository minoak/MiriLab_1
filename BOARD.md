# 정책 문의 게시판 — 개별 작업 가이드

게시판(자동답변)은 **다른 탭·시뮬레이션과 분리돼 단독으로 작업**할 수 있게 정리돼 있다.
RAG 통합은 **✅ 완료** — `board_engine.answer_with_rag()` 가 격리 패키지 `standalone_board`
(검색→생성→평가)에 위임한다. 키가 있으면 **Chroma + OpenAI Embedding** 의미검색 +
Responses 답변, 없으면 로컬 해시 검색 + 추출식으로 자동 폴백한다. 품질 지표는
`근거 일치도`, `근거 밖 가능성`처럼 근거 문서 범위 기준으로 표시한다.

## 파일 구성

| 파일 | 역할 | 만질 일 |
| --- | --- | --- |
| `board_engine.py` | 답변 엔진(순수 로직, streamlit 무의존). mock + **RAG 시임** | ⭐ 여기서 작업 |
| `ui/tab_board.py` | 화면만(질문 폼·말풍선·근거 보기). 로직은 엔진에 위임 | 보통 안 건드림 |
| `_preview_board.py` | 게시판만 띄우는 단독 실행기 | 시험용 |
| `_test_board.py` | 엔진 단위 테스트 | 회귀 확인 |

## 단독 실행

```bash
# 게시판 탭만 띄우기 (전체 시뮬레이션 불필요)
streamlit run _preview_board.py

# 엔진 단위 테스트 (화면 없이)
python _test_board.py
```

`_preview_board.py` 사이드바에서 정책을 고르거나 직접 붙여넣고, **답변 엔진**을
`mock`/`rag`/`auto` 로 바꿔 가며 시험할 수 있다.

## API + RAG 붙이는 법

`board_engine.py` 의 `answer_with_rag(policy, question, k)` 가 `standalone_board` 에 위임해
**이미 구현돼 있다**. 아래는 그 반환 계약(다른 백엔드로 교체할 때 참고).

**반환 계약** — 아래 dict 를 돌려주면 끝. 면책 문구·근거 표시·폴백은 이미 처리돼 있다.

```python
{
    "answer":  str,    # 표시할 답변 본문
    "sources": list,   # [{"text": 근거청크, "source": 출처라벨}, ...]  (없으면 [])
}
```

현재 구현(`standalone_board` 위임) 흐름:
1. 정책 원문(`policy`)을 `chunk_document` 로 청크 분할 → `build_retrieval_index` 로 검색
   인덱스(키 있으면 Chroma + OpenAI 임베딩, 없으면 로컬 해시 폴백). 같은 정책 재질문은
   `board_engine._rag_index` 캐시로 임베딩을 1회만 한다.
2. `BoardRagService.answer(question, k)` 로 검색 청크 + 질문을 답변 생성기에 넣어 답변 생성.
   - 키 확인: `standalone_board.openai_adapter.has_openai_key()` (키리스면 추출식 폴백).
   - ⚠️ openai·chromadb import 는 **함수 안에서 지연 import**(import 시점 네트워크 호출 금지 규칙).
3. 실패(빈 정책·근거 0건·네트워크·LLM 오류)는 예외로 전파되어 자동 mock 폴백(앱이 안
   죽음). `mode='rag'` 면 답변 앞에 ⚠️ 안내가 붙는다.

## 동작 모드 (`answer_question` 의 `mode`)

- `mock` — 규칙 기반(키·네트워크 불필요). 기본 동작이자 모든 실패의 폴백.
- `rag`  — `answer_with_rag` 강제 시도. 미구현/오류면 안내 문구와 함께 mock 폴백.
- `auto` — `MIRILAB_BOARD_RAG` 환경변수가 켜져 있으면 `rag`, 아니면 `mock`.

본 앱(`app.py`)은 게시판에 mode 를 따로 넘기지 않아 **기본 `auto`** 로 돈다. RAG 를
다 붙인 뒤 본 앱에서도 켜려면:

```bash
# Windows PowerShell
$env:MIRILAB_BOARD_RAG = "1"; streamlit run app.py
```

## 경계(계약)

- 게시판이 바깥에서 받는 것: `view["policy"]`(정책 원문) 하나. (선택: `view["board_mode"]`)
- 게시판이 쓰는 상태: `st.session_state["board"]` (질문/답변 스레드 누적) 한 곳.
- 따라서 다른 탭·`state.py`·사이드바를 건드리지 않고 게시판만 독립적으로 발전시킬 수 있다.
