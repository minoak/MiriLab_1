# -*- coding: utf-8 -*-
"""fragment 안에서 안전하게 화면을 다시 그리는 재실행 헬퍼.

@st.fragment 로 감싼 탭 안에서 버튼·카드 조작 뒤 즉시 화면을 갱신해야 할 때 쓴다.

왜 그냥 st.rerun() 을 안 쓰나:
- 본문 탭은 st.tabs() 로 그리는데, 전체 앱 rerun 이 일어나면 st.tabs 가 다시 평가돼
  **무조건 첫 탭으로 튕긴다**(native 로 '현재 탭 지정' 기능이 없음).
- 그래서 탭 안 인터랙션은 st.rerun(scope="fragment") 로 '그 조각만' 다시 그려야
  탭 선택이 유지된다.

왜 폴백이 필요한가:
- 실제 브라우저에선 fragment 안 버튼 클릭이 '조각 재실행'이라 scope="fragment" 가
  유효하다(정상 동작, 탭 유지).
- 하지만 조각 재실행 맥락이 아닐 때(예: Streamlit AppTest 의 .run() 은 전체 실행으로
  처리) scope="fragment" 는 StreamlitAPIException 을 던진다. 그 경우에만 전체
  재실행으로 폴백한다 — 테스트/엣지 안전망이며, 실제 앱에선 거의 타지 않는다.

정확히 StreamlitAPIException 만 잡는다(broad except 금지): st.rerun 의 정상 동작은
RerunException(BaseException 계열) 을 던지는 제어 흐름이라 Exception 으로 잡으면 안 된다.
"""
import streamlit as st
from streamlit.errors import StreamlitAPIException


def rerun_fragment() -> None:
    """조각(fragment)만 다시 그린다. 조각 맥락이 아니면 전체 재실행으로 폴백."""
    try:
        st.rerun(scope="fragment")
    except StreamlitAPIException:
        st.rerun()
