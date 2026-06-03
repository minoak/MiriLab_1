# -*- coding: utf-8 -*-
"""시민 반응 히트맵 표 빌더 회귀 — 순수함수만(streamlit 무의존).

실행: python _test_heatmap.py
"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from ui.mock import sample_simstate
from ui.model import build_view
from ui.tab_dashboard import (
    build_reaction_table, _short_region, _demo_line, _cell_css, _SCORE_LABELS,
)

# 1) 지역 축약
assert _short_region("서울특별시", "관악구") == "서울 관악", _short_region("서울특별시", "관악구")
assert _short_region("경기도", "수원시") == "경기 수원"
assert _short_region("인천광역시", "부평구") == "인천 부평"
print("[1] 지역 축약 OK")

# 2) mock view → 표
view = build_view(sample_simstate())
personas = view["personas"]
rbi = view["reactions_by_id"]
df, counts = build_reaction_table(personas, rbi)

assert not df.empty, "표가 비었음"
assert counts["total"] == len(df), (counts, len(df))
assert counts["total"] == counts["support"] + counts["mixed"] + counts["oppose"]
for col in _SCORE_LABELS:
    assert col in df.columns, f"점수 컬럼 누락: {col}"
    assert df[col].between(0, 100).all(), f"{col} 범위 밖"
assert "_pid" in df.columns and "_stance" in df.columns
print(f"[2] 표 빌드 OK — {len(df)}행, 찬성 {counts['support']}/혼합 {counts['mixed']}/반대 {counts['oppose']}")

# 3) 프로필 줄 + 셀 색(valence)
sample = df.iloc[1]
print(f"    예시 행: {sample['시민']} | {sample['프로필']} | {sample['입장']} | "
      + " ".join(f"{c}={sample[c]}" for c in _SCORE_LABELS))
# 불만도 100=레드 진함(파랑 성분 낮음), 이해도 100=파랑 진함
red_hi = _cell_css(100, neg=True)
blue_hi = _cell_css(100, neg=False)
assert "rgb(231" in red_hi and "#ffffff" in red_hi, red_hi
assert "rgb(31" in blue_hi and "#ffffff" in blue_hi, blue_hi
assert "#1f3b54" in _cell_css(0, neg=False), _cell_css(0, neg=False)  # 낮은값=어두운 글자
print("[3] 프로필/valence 셀 색 OK")

# 4) 필터링 흉내(순수 로직)
sup = df[df["_stance"] == "support"]
assert len(sup) == counts["support"]
srt = df.sort_values("신청의향", ascending=False)
assert list(srt["신청의향"]) == sorted(df["신청의향"], reverse=True)
print("[4] 필터/정렬 로직 OK")

print("\n✅ 히트맵 표 빌더 테스트 통과")
