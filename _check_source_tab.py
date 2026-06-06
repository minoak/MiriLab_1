# dev: tab_input 출처 매칭 단위 확인 (LLM 0, streamlit 렌더 없음)
from sample_policies import SAMPLES, SOURCES
from ui.tab_input import _find_source, _url_label

# 1) 샘플 5종 전부: 무수정 원문 -> 해당 SOURCES 반환
for name, text in SAMPLES.items():
    src = _find_source(text)
    assert src is SOURCES[name], f"매칭 실패: {name}"
    assert src.get("real") and src.get("urls"), f"출처 필드 비었음: {name}"

# 2) 한 글자라도 수정 -> None (정직 게이트)
modified = SAMPLES["청년 월세 한시 특별지원"] + " "
assert _find_source(modified.rstrip() + "수정") is None

# 3) 직접 입력(임의 텍스트) -> None
assert _find_source("전 국민에게 10억 원을 지급한다.") is None

# 4) URL 라벨 = 도메인
assert _url_label("https://www.bokjiro.go.kr/ssis-tbu/x") == "www.bokjiro.go.kr"

print("OK: source matching 5/5, modified/custom -> None, url label")
