# 정책 문의 게시판 — 개별 작업 가이드

게시판 RAG는 **기존 앱의 `게시판` 탭 위치**에 들어간다. 사용자는 미리랩 설정에서
선택·수정한 정책 원문을 먼저 확인하고, 같은 게시판 화면에서 추가 PDF/TXT/MD 문서를
더 올릴 수 있다.

## 파일 구성

| 파일 | 역할 | 만질 일 |
| --- | --- | --- |
| `ui/tab_board.py` | 기존 앱 `게시판` 탭. 미리랩 정책 원문 + 추가 업로드 문서를 근거로 답변 | 앱 탭 UI/연결 |
| `standalone_board/core.py` | 문서 청킹, 로컬 검색, 추출형 답변, 품질 지표, 인덱스 저장 | RAG 순수 로직 |
| `standalone_board/openai_adapter.py` | OpenAI Responses API 기반 답변 생성기 | 모델/API 작업 |
| `standalone_board/document_loaders.py` | PDF/TXT/MD 업로드 문서 로더 | 문서 입력 작업 |
| `standalone_board/app.py` | 독립 미리보기용 게시판 화면과 공통 인덱스 준비 helper | 미리보기/공통 helper |
| `_preview_board.py` | 독립 게시판 실행 진입점 | 단독 확인용 |
| `_test_board.py` | 기존 앱 게시판 탭 연결 + 기존 mock 계약 테스트 | 필수 검증 |
| `_test_standalone_board.py` | RAG 순수 로직/문서 처리/OpenAI 요청 테스트 | 필수 검증 |
| `board_engine.py` | 기존 mock 답변과 가상 시민 댓글 풀 | 댓글/폴백 유지보수 |

## 앱에서 쓰는 방식

1. 왼쪽 미리랩 설정에서 정책을 선택하거나 정책 원문을 수정한다.
2. 시뮬레이션을 실행한 뒤 `게시판` 탭으로 간다.
3. 게시판 탭은 `view["policy"]`를 **미리랩 설정 정책** 문서로 자동 사용한다.
4. 필요하면 `추가 근거 문서`에서 PDF/TXT/MD를 더 업로드한다.
5. 질문을 등록하면 정책 원문과 추가 문서를 합쳐 검색하고 답변, 근거, 품질 지표를 보여준다.

## 단독 실행

```bash
# 독립 RAG 게시판만 띄우기
streamlit run _preview_board.py

# 기존 앱 게시판 탭 연결 테스트
python _test_board.py

# RAG 로직 테스트
python _test_standalone_board.py
```

## RAG 동작

1. `ui/tab_board.py`가 `view["policy"]`를 `base_policy_text`로 넘긴다.
2. `standalone_board.app.prepare_index_update()`가 기본 정책 문서와 업로드 문서를 합친다.
3. `core.chunk_document()`가 문서를 page-aware chunk로 나누고, `지원 내용:` 같은 정책 라벨은 독립 chunk로 유지한다.
4. 검색은 `Chroma + OpenAI Embedding`을 우선 사용한다. 키가 없거나 임베딩/검색이 실패하면 로컬 해시 벡터 검색으로 폴백한다.
5. 답변 생성 모드:
   - `근거 추출`: OpenAI 답변 생성 없이 검색 근거 문장을 뽑아 답변한다.
   - `OpenAI`: `openai_adapter.py`가 Responses API로 근거 제한 답변을 만든다.
6. `QualityEvaluator`가 검색 수, 근거 일치도, 근거 밖 가능성, 검수 상태를 계산한다.
7. 기존 `board_engine.make_comments()`로 가상 시민 댓글은 유지한다.

OpenAI 키가 없거나 OpenAI/Chroma 호출이 실패하면 게시판 탭은 로컬 해시 벡터 검색과 근거 추출 답변으로 폴백한다.

## OpenAI 모델 호환

`OPENAI_MODEL=gpt-5-nano` 같은 reasoning 모델은 Chat Completions의 일부 파라미터와
맞지 않는다. 게시판은 `client.responses.create(...)`를 사용하고, reasoning 모델에는
`reasoning={"effort": "minimal"}`을 붙인다.

환경 체크도 같은 API 경로를 사용한다.

```bash
python check.py
```

## 경계(계약)

- 기존 게시판 위치는 `ui/tab_board.py`가 담당한다.
- RAG 로직은 `standalone_board/core.py`와 `standalone_board/openai_adapter.py`에 둔다.
- `app.py`, 다른 탭, 시뮬레이션 파이프라인은 건드리지 않는다.
- 런타임 인덱스와 로그는 `standalone_board/.runtime/`에 세션별로 저장되며 git에 올리지 않는다.
