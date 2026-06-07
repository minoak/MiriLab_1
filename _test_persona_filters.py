# -*- coding: utf-8 -*-
"""시민 구성 필터 + 추첨 시드 노출 작업의 회귀 가드 (네트워크 0·LLM 0).

검증 대상:
- _norm_filters: 빈 조건 제거, JSON 왕복 안정형(리스트·정렬) 캐논화
- _apply_filters: 연령(경계 포함)·성별·지역 AND 결합, 무필터 통과
- 캐시: config 비교에 filters 포함 + 구버전 캐시(filters 키 없음) 하위호환
- load_personas: 필터 캐시 적중 시 HF 빌드 미호출 / 빌드 실패 시 salvage 폴백

실행: python _test_persona_filters.py   (프로젝트 루트에서)
"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

import json
import tempfile
from pathlib import Path

import pandas as pd

import data.personas as P

# ── (a) _norm_filters: 캐논화 ──
assert P._norm_filters(None) == {}
assert P._norm_filters({}) == {}
assert P._norm_filters({"age": (60, 99)}) == {"age": [60, 99]}  # tuple→list
assert P._norm_filters({"sex": " 여자 "}) == {"sex": "여자"}     # 공백 정리
assert P._norm_filters({"provinces": ["서울", "경기", "서울"]}) == {
    "provinces": ["경기", "서울"]}                                # 중복 제거+정렬
assert P._norm_filters({"age": None, "sex": "", "provinces": []}) == {}
# JSON 왕복 후에도 동일 → 캐시 config 동등 비교에 안전
f = P._norm_filters({"age": [20, 39], "sex": "남자", "provinces": ["부산", "서울"]})
assert json.loads(json.dumps(f)) == f
print("[a] _norm_filters 캐논화 OK")

# ── (b) _apply_filters: 합성 DF 에서 AND 결합 ──
df = pd.DataFrame({
    "age": [25, 40, 70, 88],
    "sex": ["여자", "남자", "여자", "남자"],
    "province": ["서울", "경기", "전라남", "서울"],
})
assert len(P._apply_filters(df, None)) == 4                      # 무필터 통과
assert list(P._apply_filters(df, {"age": (60, 99)})["age"]) == [70, 88]
assert list(P._apply_filters(df, {"age": (25, 40)})["age"]) == [25, 40]  # 경계 포함
assert list(P._apply_filters(df, {"sex": "여자"})["age"]) == [25, 70]
assert list(P._apply_filters(df, {"provinces": ["서울"]})["age"]) == [25, 88]
combo = P._apply_filters(
    df, {"age": (60, 99), "sex": "남자", "provinces": ["서울"]})
assert list(combo["age"]) == [88]                                # AND 결합
assert len(P._apply_filters(df, {"provinces": ["제주"]})) == 0   # 빈 결과
print("[b] _apply_filters 연령·성별·지역 AND OK")

# ── (c) 캐시: filters 포함 비교 + 구버전 하위호환 ──
tmp = Path(tempfile.mkdtemp()) / "cache.json"
orig_path = P._CACHE_PATH
P._CACHE_PATH = tmp
try:
    people = [{"id": "x1", "name": "테스트"}]
    flt = {"age": [60, 99], "provinces": ["서울", "부산"]}
    P._save_cache(people, 5, 7, flt)
    assert P._load_cache(5, 7, flt) == people                  # 동일 필터 → 적중
    assert P._load_cache(5, 7, {"age": [60, 99]}) is None      # 다른 필터 → 미스
    assert P._load_cache(5, 7, None) is None                   # 무필터 → 미스
    assert P._load_cache(5, 8, flt) is None                    # 다른 시드 → 미스
    # 표기만 다른 동치 필터(tuple/순서) → 캐논화로 적중
    assert P._load_cache(
        5, 7, {"age": (60, 99), "provinces": ["부산", "서울"]}) == people
    # 구버전 캐시(filters 키 없음) ↔ 무필터 요청 = 적중(하위호환)
    tmp.write_text(
        json.dumps({"config": {"n": 5, "seed": 7}, "personas": people}),
        encoding="utf-8")
    assert P._load_cache(5, 7, None) == people
    assert P._load_cache(5, 7, flt) is None
    print("[c] 캐시 filters 비교 + 구버전 하위호환 OK")

    # ── (d) load_personas: 캐시 적중 = HF 빌드 0 / 실패 시 salvage ──
    P._save_cache(people, 5, 7, flt)
    orig_build = P._build_from_hf

    def _boom(*a, **k):
        raise AssertionError("캐시 적중인데 _build_from_hf 가 호출됨")

    P._build_from_hf = _boom
    try:
        assert P.load_personas(5, 7, filters=flt) == people
        # config 불일치(다른 시드) + 빌드 실패 → salvage(있는 캐시라도) 반환

        def _fail(*a, **k):
            raise RuntimeError("네트워크 없음(모의)")

        P._build_from_hf = _fail
        assert P.load_personas(5, 99) == people
    finally:
        P._build_from_hf = orig_build
    print("[d] load_personas 캐시 적중·salvage 폴백 OK")
finally:
    P._CACHE_PATH = orig_path

print("\nALL PASS — 시민 구성 필터 + 캐시 회귀 가드")
