# 정책 문의 게시판 — 개별 작업 가이드

게시판 작업은 다른 탭·시뮬레이션과 충돌하지 않도록 두 갈래로 분리한다.

- 기존 앱 탭: `ui/tab_board.py` + `board_engine.py`
- RAG 전용 독립 게시판: `standalone_board/` + `_preview_board.py`

현재 RAG 작업은 **`standalone_board/` 안에서만** 진행한다. 기존 `app.py`,
`ui/tab_board.py`, `board_engine.py`는 다른 기능과 연결된 공유 코드라 건드리지 않는다.

## 파일 구성

| 파일 | 역할 | 만질 일 |
| --- | --- | --- |
| `standalone_board/core.py` | 문서 청킹, 로컬 검색, 추출형 답변, 품질 지표, 인덱스 저장 | RAG 로직 작업 |
| `standalone_board/openai_adapter.py` | OpenAI Responses API 기반 답변 생성기 | 모델/API 작업 |
| `standalone_board/document_loaders.py` | PDF/TXT/MD 업로드 문서 로더 | 문서 입력 작업 |
| `standalone_board/app.py` | Streamlit 독립 게시판 화면 | 게시판 UI 작업 |
| `_preview_board.py` | 독립 게시판 실행 진입점 | 실행용 |
| `_test_standalone_board.py` | 독립 게시판 회귀 테스트 | 필수 검증 |
| `board_engine.py` / `ui/tab_board.py` | 기존 앱 탭용 mock 게시판 | 유지보수만 |
| `_test_board.py` | 기존 앱 게시판 계약 테스트 | 공유 코드 회귀 확인 |

## 단독 실행

```bash
# 독립 RAG 게시판만 띄우기
streamlit run _preview_board.py

# 독립 게시판 테스트
python _test_standalone_board.py

# 기존 앱 게시판 계약 회귀 확인
python _test_board.py
```

독립 게시판은 사이드바에서 PDF/TXT/MD 문서를 업로드한 뒤 **인덱스 생성**을 눌러
근거 조각을 만든다. 질문을 등록하면 검색 근거, 답변, 품질 지표를 함께 보여준다.

## RAG 동작

1. `document_loaders.py`가 업로드 문서를 `PolicyDocument`로 읽는다.
2. `core.chunk_document()`가 문서를 page-aware chunk로 나눈다.
3. `VectorIndex`가 로컬 해싱 임베딩으로 관련 근거를 검색한다.
4. 답변 생성 모드:
   - `근거 추출`: 네트워크 없이 검색 근거 문장을 뽑아 답변한다.
   - `OpenAI`: `openai_adapter.py`가 Responses API로 근거 제한 답변을 만든다.
5. `QualityEvaluator`가 검색 수, 근거 충실도, 환각 위험도, 기준 정답 유사도를 계산한다.

OpenAI 키가 없거나 OpenAI 호출이 실패하면 독립 게시판 UI는 근거 추출 답변으로 폴백한다.

## OpenAI 모델 호환

`OPENAI_MODEL=gpt-5-nano` 같은 reasoning 모델은 Chat Completions의 일부 파라미터와
맞지 않는다. 독립 게시판은 `client.responses.create(...)`를 사용하고,
reasoning 모델에는 `reasoning={"effort": "minimal"}`을 붙인다.

환경 체크도 같은 API 경로를 사용한다.

```bash
python check.py
```

## 경계(계약)

- RAG 게시판 작업은 `standalone_board/`, `_preview_board.py`,
  `_test_standalone_board.py` 중심으로 진행한다.
- 기존 앱 탭은 `board_engine.answer_question()` 계약을 유지한다.
- 기존 앱 회귀 테스트인 `_test_board.py`가 깨지면 공유 코드 영향으로 보고 즉시 고친다.
- 런타임 인덱스와 로그는 `standalone_board/.runtime/`에 세션별로 저장되며 git에 올리지 않는다.
