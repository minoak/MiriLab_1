# -*- coding: utf-8 -*-
"""_test_llm_provider.py — '시민 모델' 선택(런타임 프로바이더 전환) 키리스 단위 테스트.

검증(네트워크 0, 외부 호출 0 — get_client 는 가짜 클래스 주입):
1) set_provider: PROVIDER/MODEL 짝 갱신 + 잘못된 이름 ValueError(상태 유지).
2) has_real_key: 현재 프로바이더 기준 판정(openai 플레이스홀더 키 제외).
3) available_providers: 키 있는 프로바이더만(선택기 선택지 재료).
4) get_client: 프로바이더별 캐시 — 전환 왕복에도 인스턴스 재생성 없음,
   gemini 만 base_url 지정.
5) 미리마을 gen 2종: 같은 분기 독립 복제 + set_provider 동작
   (tab_minivillage._sync_llm_provider 의 전파 대상).
실행: python _test_llm_provider.py
"""
import importlib.util
import os
import sys
from pathlib import Path

import graph.llm as gl

ROOT = Path(__file__).resolve().parent

fails = []


def check(name, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" - {detail}" if detail else ""))
    if not ok:
        fails.append(name)


# 환경·모듈 상태 백업 — 테스트가 .env 로 로드된 실키를 임시로 가린다(끝나면 원복).
_ENV_KEYS = ("OPENAI_API_KEY", "GEMINI_API_KEY")
_env_backup = {k: os.environ.get(k) for k in _ENV_KEYS}
_prov_backup = gl.PROVIDER


def _set_env(openai=None, gemini=None):
    for k, v in (("OPENAI_API_KEY", openai), ("GEMINI_API_KEY", gemini)):
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


def main():
    # 1) set_provider 전환 -------------------------------------------------
    gl.set_provider("openai")
    check("openai 전환: PROVIDER", gl.PROVIDER == "openai")
    check("openai 전환: MODEL 짝", gl.MODEL == gl.PROVIDER_MODELS["openai"])
    gl.set_provider("gemini")
    check("gemini 전환: PROVIDER", gl.PROVIDER == "gemini")
    check("gemini 전환: MODEL 짝", gl.MODEL == gl.PROVIDER_MODELS["gemini"])
    try:
        gl.set_provider("clude")
        check("오타 프로바이더 ValueError", False)
    except ValueError:
        check("오타 프로바이더 ValueError", True)
    check("실패 후 기존 상태 유지", gl.PROVIDER == "gemini")

    # 2) has_real_key — 프로바이더를 따라감 --------------------------------
    _set_env(openai="sk-test-123", gemini=None)
    gl.set_provider("gemini")
    check("gemini 키 없음 -> False", gl.has_real_key() is False)
    gl.set_provider("openai")
    check("openai 키 있음 -> True", gl.has_real_key() is True)
    _set_env(openai="sk-your-key-here", gemini="g-test")
    check("openai 플레이스홀더 -> False", gl.has_real_key() is False)
    gl.set_provider("gemini")
    check("gemini 키 있음 -> True", gl.has_real_key() is True)

    # 3) available_providers ----------------------------------------------
    _set_env(openai="sk-test-123", gemini="g-test")
    check("둘 다 키 -> 둘 다",
          set(gl.available_providers()) == {"openai", "gemini"})
    _set_env(openai="sk-your-key-here", gemini=None)
    check("키 없음(플레이스홀더만) -> 빈 목록", gl.available_providers() == [])
    _set_env(openai=None, gemini="g-test")
    check("gemini 만", gl.available_providers() == ["gemini"])

    # 4) get_client 프로바이더별 캐시(가짜 클래스 주입 — 네트워크 0 보증) ----
    class _FakeOpenAI:
        made = 0

        def __init__(self, **kw):
            _FakeOpenAI.made += 1
            self.kw = kw

    _set_env(openai="sk-test-123", gemini="g-test")
    orig_cls, orig_cache = gl.OpenAI, dict(gl._clients)
    gl.OpenAI = _FakeOpenAI
    gl._clients.clear()
    try:
        gl.set_provider("openai")
        c1 = gl.get_client()
        gl.set_provider("gemini")
        c2 = gl.get_client()
        gl.set_provider("openai")
        c3 = gl.get_client()
        gl.set_provider("gemini")
        c4 = gl.get_client()
        check("프로바이더별 별도 인스턴스", c1 is not c2)
        check("왕복 후 캐시 재사용(openai)", c1 is c3)
        check("왕복 후 캐시 재사용(gemini)", c2 is c4)
        check("총 생성 2회뿐", _FakeOpenAI.made == 2,
              f"made={_FakeOpenAI.made}")
        check("gemini 는 base_url 지정",
              c2.kw.get("base_url") == gl.GEMINI_BASE_URL)
        check("openai 는 base_url 미지정", "base_url" not in c1.kw)
    finally:
        gl.OpenAI = orig_cls
        gl._clients.clear()
        gl._clients.update(orig_cache)

    # 5) 미리마을 gen 2종 — 같은 분기 + set_provider ------------------------
    # (exec 시 load_dotenv 가 .env 키를 되살릴 수 있어, 각 검사 직전에 env 재설정)
    for fname in ("gen_schedules.py", "gen_dialogues.py"):
        path = ROOT / "미리마을" / fname
        spec = importlib.util.spec_from_file_location(f"_t_{fname[:-3]}", str(path))
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod
        spec.loader.exec_module(mod)
        ok_attrs = all(hasattr(mod, a) for a in
                       ("set_provider", "PROVIDER", "MODEL",
                        "PROVIDER_MODELS", "has_real_key"))
        check(f"{fname}: 프로바이더 분기 보유", ok_attrs)
        if not ok_attrs:
            continue
        mod.set_provider("gemini")
        check(f"{fname}: gemini 전환(MODEL 짝)",
              mod.PROVIDER == "gemini"
              and mod.MODEL == mod.PROVIDER_MODELS["gemini"])
        _set_env(openai="sk-test-123", gemini=None)
        check(f"{fname}: has_real_key 프로바이더 추종", mod.has_real_key() is False)
        mod.set_provider("openai")
        check(f"{fname}: openai 복귀 has_real_key", mod.has_real_key() is True)


if __name__ == "__main__":
    try:
        main()
    finally:
        # 환경·모듈 상태 원복(이 테스트는 프로세스 상태를 더럽히지 않는다)
        for k, v in _env_backup.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        gl.set_provider(_prov_backup)

    print()
    if fails:
        print(f"FAILED: {fails}")
        sys.exit(1)
    print("ALL PASS")
