import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime
import plotly.graph_objects as go


# =========================================================
# 1. 데이터 조회 함수
# =========================================================

def get_market_data(ticker_symbol: str, period: str = "2y"):
    """야후파이낸스에서 티커 데이터를 조회한다."""
    try:
        ticker = yf.Ticker(ticker_symbol)
        hist = ticker.history(period=period)

        if hist is None or hist.empty or "Close" not in hist.columns:
            return None, None, None

        hist = hist.dropna(subset=["Close"])
        if hist.empty:
            return None, None, None

        current_value = float(hist["Close"].iloc[-1])
        last_date = hist.index[-1]

        return current_value, hist, last_date

    except Exception as e:
        st.warning(f"{ticker_symbol} 데이터 조회 실패: {e}")
        return None, None, None


def format_data_date(date_value):
    """데이터 기준일을 화면 표시용 문자열로 변환한다."""
    if date_value is None:
        return "N/A"

    try:
        return pd.to_datetime(date_value).strftime("%Y-%m-%d")
    except Exception:
        return str(date_value)


# =========================================================
# 2. 환전 비용률 가이드 함수
# =========================================================

def calculate_effective_fee_rate(base_spread_percent, preferential_discount_percent):
    """
    예상 환전 비용률을 계산한다.

    예시:
    - 기본 스프레드 1.50%
    - 환율우대 90%
    - 실제 부담 비용률 = 1.50% × (1 - 90%) = 0.15%
    """
    effective_fee_rate = base_spread_percent * (1 - preferential_discount_percent / 100)
    return max(effective_fee_rate, 0)


def get_fee_preset_info(preset_name):
    """환전 비용률 가이드 프리셋을 반환한다."""

    presets = {
        "하나은행 환전지갑 USD 90% 우대 가정": {
            "base_spread": 1.50,
            "discount": 90.0,
            "description": "하나은행 USD 외화현찰 수수료 1.5%, 환전지갑 최대 90% 환율우대 가정",
        },
        "시중은행 USD 80% 우대 가정": {
            "base_spread": 1.50,
            "discount": 80.0,
            "description": "은행권 달러 환전에서 우대율이 80% 정도라고 보수적으로 가정",
        },
        "증권사 USD 95% 환전우대 가정": {
            "base_spread": 1.00,
            "discount": 95.0,
            "description": "증권사 해외주식 이벤트에서 자주 보이는 USD 95% 환율우대 가정",
        },
        "증권사 USD 90% 환전우대 가정": {
            "base_spread": 1.00,
            "discount": 90.0,
            "description": "증권사 환전우대가 90% 수준이라고 가정",
        },
        "우대 없음": {
            "base_spread": 1.00,
            "discount": 0.0,
            "description": "환율우대를 받지 못하는 보수적 가정",
        },
    }

    return presets[preset_name]


# =========================================================
# 3. 달러 갭 비율 및 적정 환율 계산
# =========================================================

def calculate_dollar_gap_ratio(current_rate, rate_hist, current_dxy, dxy_hist, period_days=252):
    """
    달러 갭 비율 및 적정 환율 계산

    핵심 공식:
    - 기간 중간 환율 = (기간 최저 환율 + 기간 최고 환율) / 2
    - 기간 중간 DXY = (기간 최저 DXY + 기간 최고 DXY) / 2
    - 현재 달러 갭 비율 = 현재 DXY / 현재 원달러 환율 * 100
    - 기준 달러 갭 비율 = 기간 중간 DXY / 기간 중간 환율 * 100
    - 적정 환율 = 현재 DXY / 기준 달러 갭 비율 * 100
    """

    if current_rate is None or rate_hist is None or rate_hist.empty:
        return None

    rate_close = rate_hist["Close"].dropna()

    if len(rate_close) < period_days:
        return None

    recent_rate = rate_close.tail(period_days)
    rate_min = float(recent_rate.min())
    rate_max = float(recent_rate.max())
    rate_mid = (rate_min + rate_max) / 2

    rate_vs_mid = ((current_rate - rate_mid) / rate_mid) * 100

    dxy_stats = None
    dxy_vs_mid = None
    current_gap_ratio = None
    mid_gap_ratio = None
    appropriate_rate = None

    if current_dxy is not None and dxy_hist is not None and not dxy_hist.empty:
        dxy_close = dxy_hist["Close"].dropna()

        if len(dxy_close) >= period_days:
            recent_dxy = dxy_close.tail(period_days)
            dxy_min = float(recent_dxy.min())
            dxy_max = float(recent_dxy.max())
            dxy_mid = (dxy_min + dxy_max) / 2

            dxy_vs_mid = ((current_dxy - dxy_mid) / dxy_mid) * 100

            if current_rate > 0 and rate_mid > 0:
                current_gap_ratio = (current_dxy / current_rate) * 100
                mid_gap_ratio = (dxy_mid / rate_mid) * 100

                if mid_gap_ratio > 0:
                    appropriate_rate = (current_dxy / mid_gap_ratio) * 100

            dxy_stats = {
                "current": current_dxy,
                "mid": dxy_mid,
                "min": dxy_min,
                "max": dxy_max,
            }

    return {
        "rate_vs_mid": rate_vs_mid,
        "dxy_vs_mid": dxy_vs_mid,
        "current_gap_ratio": current_gap_ratio,
        "mid_gap_ratio": mid_gap_ratio,
        "appropriate_rate": appropriate_rate,
        "rate_stats": {
            "current": current_rate,
            "mid": rate_mid,
            "min": rate_min,
            "max": rate_max,
        },
        "dxy_stats": dxy_stats,
    }


# =========================================================
# 4. DXY 추세 분석
# =========================================================

def analyze_dxy_trend(dxy_hist):
    """DXY의 단기·중기 추세를 간단히 분석한다."""
    if dxy_hist is None or dxy_hist.empty:
        return None, None

    close = dxy_hist["Close"].dropna()

    if len(close) < 20:
        return None, None

    current = float(close.iloc[-1])
    ma20 = float(close.tail(20).mean())
    ma5 = float(close.tail(5).mean())

    mid_trend = "상승 우위" if current > ma20 else "하락 우위"
    short_trend = "상승 우위" if current > ma5 else "하락 우위"

    return mid_trend, short_trend


# =========================================================
# 5. 달러 매수 적합성 판단
# =========================================================

def get_investment_suitability(gap_data):
    """
    달러 매수 적합성 판단

    4가지 조건:
    1. 현재 원달러 환율이 기간 중간 환율보다 낮은가?
    2. 현재 DXY가 기간 중간 DXY보다 낮은가?
    3. 현재 달러 갭 비율이 기준 달러 갭 비율보다 높은가?
    4. 현재 환율이 적정 환율보다 낮은가?
    """

    if gap_data is None:
        return {
            "decision": "데이터 부족",
            "explanation": "분석에 필요한 환율 데이터가 충분하지 않습니다.",
            "recommendations": [],
            "conditions_met": 0,
            "total_conditions": 4,
            "is_complete": False,
            "missing_conditions": ["환율 데이터", "DXY 데이터"],
        }

    recommendations = []
    conditions_met = 0
    total_conditions = 4
    missing_conditions = []

    # 조건 1
    rate_vs_mid = gap_data.get("rate_vs_mid")

    if rate_vs_mid is None:
        missing_conditions.append("현재 환율 vs 기간 중간 환율")
    else:
        if rate_vs_mid < 0:
            recommendations.append(
                f"✅ 조건 1: 현재 원/달러 환율이 기간 중간가보다 낮음 ({rate_vs_mid:+.2f}%)"
            )
            conditions_met += 1
        else:
            recommendations.append(
                f"❌ 조건 1: 현재 원/달러 환율이 기간 중간가보다 높음 ({rate_vs_mid:+.2f}%)"
            )

    # 조건 2
    dxy_vs_mid = gap_data.get("dxy_vs_mid")

    if dxy_vs_mid is None:
        missing_conditions.append("현재 DXY vs 기간 중간 DXY")
    else:
        if dxy_vs_mid < 0:
            recommendations.append(
                f"✅ 조건 2: 현재 달러지수(DXY)가 기간 중간가보다 낮음 ({dxy_vs_mid:+.2f}%)"
            )
            conditions_met += 1
        else:
            recommendations.append(
                f"❌ 조건 2: 현재 달러지수(DXY)가 기간 중간가보다 높음 ({dxy_vs_mid:+.2f}%)"
            )

    # 조건 3
    current_gap = gap_data.get("current_gap_ratio")
    mid_gap = gap_data.get("mid_gap_ratio")

    if current_gap is None or mid_gap is None:
        missing_conditions.append("현재 달러 갭 비율 vs 기준 달러 갭 비율")
    else:
        gap_diff = current_gap - mid_gap
        gap_diff_pct = (gap_diff / mid_gap) * 100 if mid_gap else 0

        if gap_diff > 0:
            recommendations.append(
                f"✅ 조건 3: 현재 달러 갭 비율이 기준 갭 비율보다 높음 ({gap_diff_pct:+.2f}%)"
            )
            conditions_met += 1
        else:
            recommendations.append(
                f"❌ 조건 3: 현재 달러 갭 비율이 기준 갭 비율보다 낮음 ({gap_diff_pct:+.2f}%)"
            )

    # 조건 4
    current_rate = gap_data.get("rate_stats", {}).get("current")
    appropriate_rate = gap_data.get("appropriate_rate")

    if current_rate is None or appropriate_rate is None:
        missing_conditions.append("현재 환율 vs 적정 환율")
    else:
        rate_diff = current_rate - appropriate_rate
        rate_diff_pct = (rate_diff / appropriate_rate) * 100 if appropriate_rate else 0

        if rate_diff < 0:
            recommendations.append(
                f"✅ 조건 4: 현재 환율이 적정 환율보다 낮음 ({rate_diff_pct:+.2f}%)"
            )
            conditions_met += 1
        else:
            recommendations.append(
                f"❌ 조건 4: 현재 환율이 적정 환율보다 높음 ({rate_diff_pct:+.2f}%)"
            )

    if missing_conditions:
        return {
            "decision": "데이터 부족",
            "explanation": "4가지 지표가 모두 계산되지 않아 최종 판단을 보류합니다.",
            "recommendations": recommendations,
            "conditions_met": conditions_met,
            "total_conditions": total_conditions,
            "is_complete": False,
            "missing_conditions": missing_conditions,
        }

    if conditions_met == 4:
        decision = "🟢 달러 매수 적합성 높음"
        explanation = "4가지 조건을 모두 만족합니다. 현재 구간은 달러 매수에 비교적 우호적인 구간으로 볼 수 있습니다."
    elif conditions_met == 3:
        decision = "🟡 달러 매수 적합성 양호"
        explanation = "4가지 조건 중 3가지를 만족합니다. 일시 매수보다는 분할매수 관점에서 검토할 수 있습니다."
    elif conditions_met == 2:
        decision = "⚪ 중립 구간"
        explanation = "4가지 조건 중 2가지를 만족합니다. 뚜렷하게 유리하거나 불리한 구간으로 보기는 어렵습니다."
    elif conditions_met == 1:
        decision = "🟠 신중 구간"
        explanation = "4가지 조건 중 1가지만 만족합니다. 달러 매수에는 다소 신중한 접근이 필요합니다."
    else:
        decision = "🔴 달러 매수 적합성 낮음"
        explanation = "4가지 조건을 모두 만족하지 못했습니다. 현재 구간은 달러 매수에 불리할 수 있습니다."

    return {
        "decision": decision,
        "explanation": explanation,
        "recommendations": recommendations,
        "conditions_met": conditions_met,
        "total_conditions": total_conditions,
        "is_complete": True,
        "missing_conditions": [],
    }


# =========================================================
# 6. 투자 금액 및 시나리오 계산
# =========================================================

def calculate_investment_details(investment_amount, current_rate, fee_rate_percent):
    """투자금, 환전 비용, 실제 매수 가능 달러를 계산한다."""
    if current_rate is None or current_rate <= 0:
        return None

    fee_rate = fee_rate_percent / 100
    fee = investment_amount * fee_rate
    net_investment = investment_amount - fee

    gross_dollar = investment_amount / current_rate
    net_dollar = net_investment / current_rate

    return {
        "investment_amount": investment_amount,
        "current_rate": current_rate,
        "fee_rate_percent": fee_rate_percent,
        "fee": fee,
        "net_investment": net_investment,
        "gross_dollar": gross_dollar,
        "net_dollar": net_dollar,
    }


def build_exchange_rate_scenarios(investment_details, current_rate):
    """
    환율 변동 시나리오를 계산한다.

    지금 매수한 달러 수량을 고정하고,
    미래 환율 변화에 따른 원화 평가액을 계산한다.
    """

    if investment_details is None:
        return pd.DataFrame()

    held_dollar = investment_details["net_dollar"]
    net_investment = investment_details["net_investment"]

    scenarios = [-10, -7, -5, -3, -1, 0, 1, 3, 5, 7, 10]
    rows = []

    for change_pct in scenarios:
        future_rate = current_rate * (1 + change_pct / 100)
        future_value_krw = held_dollar * future_rate
        profit_loss = future_value_krw - net_investment
        profit_loss_pct = (profit_loss / net_investment) * 100 if net_investment else 0

        rows.append({
            "환율 변동": f"{change_pct:+.1f}%",
            "예상 환율": f"₩{future_rate:,.2f}",
            "보유 달러": f"${held_dollar:,.2f}",
            "원화 평가액": f"₩{future_value_krw:,.0f}",
            "평가손익": f"₩{profit_loss:+,.0f}",
            "수익률": f"{profit_loss_pct:+.2f}%",
        })

    return pd.DataFrame(rows)


# =========================================================
# 7. Streamlit 앱
# =========================================================

st.set_page_config(
    page_title="달러 매수 적합성 가이드",
    page_icon="💵",
    layout="wide",
)

st.title("💵 달러 매수 적합성 가이드")
st.caption(
    "달러리치식 달러 갭 비율 개념을 참고한 교육용 스크리너입니다. "
    "투자 추천이 아니라 현재 구간의 달러 매수 적합성을 점검하는 도구입니다."
)
st.markdown("---")


# =========================================================
# 사이드바 입력
# =========================================================

with st.sidebar:
    st.header("⚙️ 입력 설정")

    investment_amount = st.number_input(
        "투자 금액(원)",
        min_value=0.0,
        value=1_000_000.0,
        step=100_000.0,
        format="%.0f",
        help="달러로 환전하거나 달러자산에 투자하려는 원화 금액을 입력합니다.",
    )

    st.markdown("---")

    st.subheader("💱 환전 비용률 가이드")

    fee_input_mode = st.radio(
        "환전 비용 입력 방식",
        ["가이드에서 선택", "직접 입력"],
        index=0,
        help="수수료를 잘 모르면 가이드에서 선택하세요.",
    )

    if fee_input_mode == "가이드에서 선택":
        fee_preset_name = st.selectbox(
            "환전 비용 가이드 선택",
            [
                "하나은행 환전지갑 USD 90% 우대 가정",
                "시중은행 USD 80% 우대 가정",
                "증권사 USD 95% 환전우대 가정",
                "증권사 USD 90% 환전우대 가정",
                "우대 없음",
            ],
            index=2,
        )

        preset_info = get_fee_preset_info(fee_preset_name)

        base_spread_percent = st.number_input(
            "우대 전 기본 스프레드(%)",
            min_value=0.0,
            max_value=5.0,
            value=float(preset_info["base_spread"]),
            step=0.05,
            format="%.2f",
            help="은행·증권사가 우대 전 적용하는 기본 환전 스프레드입니다.",
        )

        preferential_discount_percent = st.number_input(
            "환율우대율(%)",
            min_value=0.0,
            max_value=100.0,
            value=float(preset_info["discount"]),
            step=1.0,
            format="%.1f",
            help="환전 스프레드를 얼마나 깎아주는지 의미합니다.",
        )

        fee_rate_percent = calculate_effective_fee_rate(
            base_spread_percent,
            preferential_discount_percent,
        )

        st.success(f"예상 환전 비용률: {fee_rate_percent:.3f}%")
        st.caption(preset_info["description"])

    else:
        fee_rate_percent = st.number_input(
            "예상 환전 비용률 직접 입력(%)",
            min_value=0.0,
            max_value=5.0,
            value=0.20,
            step=0.01,
            format="%.3f",
            help="직접 알고 있는 환전 비용률이 있다면 입력합니다.",
        )

    with st.expander("환전 비용률 가이드 보기"):
        guide_df = pd.DataFrame([
            {
                "구분": "하나은행 환전지갑 USD 90% 우대 가정",
                "우대 전 스프레드": "1.50%",
                "환율우대": "90%",
                "예상 비용률": "0.15%",
                "해석": "은행 앱 환전 기준 보수적 가이드",
            },
            {
                "구분": "시중은행 USD 80% 우대 가정",
                "우대 전 스프레드": "1.50%",
                "환율우대": "80%",
                "예상 비용률": "0.30%",
                "해석": "우대율이 낮은 경우의 보수적 가이드",
            },
            {
                "구분": "증권사 USD 95% 환전우대 가정",
                "우대 전 스프레드": "1.00%",
                "환율우대": "95%",
                "예상 비용률": "0.05%",
                "해석": "해외주식 이벤트 계좌에서 자주 보이는 수준",
            },
            {
                "구분": "증권사 USD 90% 환전우대 가정",
                "우대 전 스프레드": "1.00%",
                "환율우대": "90%",
                "예상 비용률": "0.10%",
                "해석": "증권사 우대율이 90% 수준일 때",
            },
            {
                "구분": "우대 없음",
                "우대 전 스프레드": "1.00%",
                "환율우대": "0%",
                "예상 비용률": "1.00%",
                "해석": "우대 이벤트 미적용 가정",
            },
        ])

        st.dataframe(guide_df, use_container_width=True, hide_index=True)

        st.markdown(
            """
            **계산식**

            예상 환전 비용률 = 우대 전 기본 스프레드 × (1 - 환율우대율)

            예를 들어 기본 스프레드가 1.50%이고 환율우대가 90%라면  
            실제 부담 비용률은 1.50% × 10% = **0.15%**입니다.

            단, 실제 환전가는 은행·증권사별 고시환율, 영업시간, 이벤트 적용 여부, 원화주문 여부에 따라 달라질 수 있습니다.
            """
        )

    st.markdown("---")

    st.subheader("📊 분석 기간")

    period_options = {
        "1개월": 21,
        "3개월": 63,
        "6개월": 126,
        "1년": 252,
    }

    period_selection = st.selectbox(
        "분석 기간 선택",
        options=list(period_options.keys()),
        index=3,
        help="중간가와 기준 달러 갭 비율 계산에 사용할 기간을 선택합니다.",
    )

    period_days = period_options[period_selection]

    st.markdown("---")

    analyze_clicked = st.button("🚀 분석하기", type="primary", use_container_width=True)
    reset_clicked = st.button("🔄 초기화", use_container_width=True)

    if analyze_clicked:
        if investment_amount <= 0:
            st.error("투자 금액은 0보다 커야 합니다.")
        else:
            st.session_state["analyze"] = True
            st.session_state["investment_amount"] = investment_amount
            st.session_state["fee_rate_percent"] = fee_rate_percent
            st.session_state["period_days"] = period_days
            st.session_state["period_selection"] = period_selection
            st.session_state["fee_input_mode"] = fee_input_mode

            if fee_input_mode == "가이드에서 선택":
                st.session_state["fee_preset_name"] = fee_preset_name
                st.session_state["base_spread_percent"] = base_spread_percent
                st.session_state["preferential_discount_percent"] = preferential_discount_percent
            else:
                st.session_state["fee_preset_name"] = "직접 입력"
                st.session_state["base_spread_percent"] = None
                st.session_state["preferential_discount_percent"] = None

    if reset_clicked:
        reset_keys = [
            "analyze",
            "investment_amount",
            "fee_rate_percent",
            "period_days",
            "period_selection",
            "fee_input_mode",
            "fee_preset_name",
            "base_spread_percent",
            "preferential_discount_percent",
        ]

        for key in reset_keys:
            if key in st.session_state:
                del st.session_state[key]

        st.rerun()


# =========================================================
# 메인 화면
# =========================================================

if st.session_state.get("analyze", False):
    investment_amount = st.session_state.get("investment_amount", 1_000_000.0)
    fee_rate_percent = st.session_state.get("fee_rate_percent", 0.20)
    period_days = st.session_state.get("period_days", 252)
    period_selection = st.session_state.get("period_selection", "1년")
    fee_preset_name = st.session_state.get("fee_preset_name", "직접 입력")
    base_spread_percent = st.session_state.get("base_spread_percent", None)
    preferential_discount_percent = st.session_state.get("preferential_discount_percent", None)

    with st.spinner("환율과 달러지수 데이터를 조회하는 중입니다."):
        current_rate, rate_hist, rate_date = get_market_data("KRW=X", period="2y")
        current_dxy, dxy_hist, dxy_date = get_market_data("DX-Y.NYB", period="2y")

    if current_rate is None:
        st.error("원/달러 환율 데이터를 가져올 수 없습니다. 잠시 후 다시 시도해주세요.")
        st.stop()

    gap_data = calculate_dollar_gap_ratio(
        current_rate=current_rate,
        rate_hist=rate_hist,
        current_dxy=current_dxy,
        dxy_hist=dxy_hist,
        period_days=period_days,
    )

    suitability = get_investment_suitability(gap_data)

    investment_details = calculate_investment_details(
        investment_amount=investment_amount,
        current_rate=current_rate,
        fee_rate_percent=fee_rate_percent,
    )

    dxy_mid_trend, dxy_short_trend = analyze_dxy_trend(dxy_hist)

    # =====================================================
    # 데이터 기준
    # =====================================================

    st.subheader("🕒 데이터 기준")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("원/달러 환율 기준일", format_data_date(rate_date))

    with col2:
        st.metric("DXY 기준일", format_data_date(dxy_date))

    with col3:
        st.metric("분석 기간", period_selection)

    st.info(
        "야후파이낸스 데이터 기준입니다. 실제 은행·증권사 환전가, 환전 스프레드, "
        "데이터 반영 시간과 차이가 있을 수 있습니다."
    )

    st.markdown("---")

    # =====================================================
    # 환전 비용 가정
    # =====================================================

    st.subheader("💱 환전 비용 가정")

    c1, c2, c3, c4 = st.columns(4)

    with c1:
        st.metric("선택한 가이드", fee_preset_name)

    with c2:
        if base_spread_percent is not None:
            st.metric("우대 전 스프레드", f"{base_spread_percent:.2f}%")
        else:
            st.metric("우대 전 스프레드", "직접 입력")

    with c3:
        if preferential_discount_percent is not None:
            st.metric("환율우대율", f"{preferential_discount_percent:.1f}%")
        else:
            st.metric("환율우대율", "직접 입력")

    with c4:
        st.metric("예상 환전 비용률", f"{fee_rate_percent:.3f}%")

    st.caption(
        "환전 비용률은 실제 환율 고시값과 다를 수 있는 추정치입니다. "
        "앱에서는 투자금에서 예상 비용률만큼 차감한 뒤 매수 가능 달러를 계산합니다."
    )

    st.markdown("---")

    # =====================================================
    # 현재 시장 상황
    # =====================================================

    st.subheader("📈 현재 시장 상황")

    top1, top2, top3 = st.columns(3)

    with top1:
        st.metric("현재 달러지수(DXY)", f"{current_dxy:.2f}" if current_dxy is not None else "N/A")

    with top2:
        if gap_data and gap_data.get("mid_gap_ratio") is not None:
            st.metric(f"{period_selection} 기준 달러 갭", f"{gap_data['mid_gap_ratio']:.2f}")
        else:
            st.metric(f"{period_selection} 기준 달러 갭", "N/A")

    with top3:
        if gap_data and gap_data.get("appropriate_rate") is not None:
            st.metric("적정 환율", f"₩{gap_data['appropriate_rate']:,.2f}")
        else:
            st.metric("적정 환율", "N/A")

    st.markdown("---")

    # =====================================================
    # 상세 지표
    # =====================================================

    st.subheader("📊 상세 지표")

    col1, col2, col3, col4 = st.columns(4)

    if gap_data:
        rate_stats = gap_data.get("rate_stats", {})
        dxy_stats = gap_data.get("dxy_stats", {})
    else:
        rate_stats = {}
        dxy_stats = {}

    with col1:
        rate_vs_mid = gap_data.get("rate_vs_mid") if gap_data else None

        st.metric(
            "현재 원/달러 환율",
            f"₩{current_rate:,.2f}",
            delta=f"{rate_vs_mid:+.2f}%" if rate_vs_mid is not None else None,
            delta_color="inverse",
            help="기간 중간 환율보다 낮을수록 달러 매수 관점에서는 유리하게 해석합니다.",
        )

    with col2:
        dxy_vs_mid = gap_data.get("dxy_vs_mid") if gap_data else None

        st.metric(
            "현재 DXY",
            f"{current_dxy:.2f}" if current_dxy is not None else "N/A",
            delta=f"{dxy_vs_mid:+.2f}%" if dxy_vs_mid is not None else None,
            delta_color="inverse",
            help="기간 중간 DXY보다 낮을수록 달러 매수 관점에서는 유리하게 해석합니다.",
        )

    with col3:
        current_gap = gap_data.get("current_gap_ratio") if gap_data else None
        mid_gap = gap_data.get("mid_gap_ratio") if gap_data else None

        if current_gap is not None and mid_gap is not None and mid_gap != 0:
            gap_delta_pct = ((current_gap - mid_gap) / mid_gap) * 100
        else:
            gap_delta_pct = None

        st.metric(
            "현재 달러 갭 비율",
            f"{current_gap:.2f}" if current_gap is not None else "N/A",
            delta=f"{gap_delta_pct:+.2f}%" if gap_delta_pct is not None else None,
            delta_color="normal",
            help="현재 달러 갭 비율이 기준 달러 갭 비율보다 높으면 매수 관점에서 유리하게 해석합니다.",
        )

    with col4:
        appropriate_rate = gap_data.get("appropriate_rate") if gap_data else None

        if appropriate_rate is not None:
            rate_diff_pct = ((current_rate - appropriate_rate) / appropriate_rate) * 100
        else:
            rate_diff_pct = None

        st.metric(
            "적정 환율",
            f"₩{appropriate_rate:,.2f}" if appropriate_rate is not None else "N/A",
            delta=f"{rate_diff_pct:+.2f}%" if rate_diff_pct is not None else None,
            delta_color="inverse",
            help="현재 환율이 적정 환율보다 낮으면 달러 매수 관점에서 유리하게 해석합니다.",
        )

    st.markdown("---")

    # =====================================================
    # 달러 매수 적합성 판단
    # =====================================================

    st.subheader("🎯 달러 매수 적합성 판단")

    decision = suitability["decision"]
    explanation = suitability["explanation"]

    if decision.startswith("🟢"):
        st.success(f"### {decision}")
    elif decision.startswith("🟡"):
        st.info(f"### {decision}")
    elif decision.startswith("🟠"):
        st.warning(f"### {decision}")
    elif decision.startswith("🔴"):
        st.error(f"### {decision}")
    elif decision == "데이터 부족":
        st.warning(f"### {decision}")
    else:
        st.markdown(f"### {decision}")

    st.write(explanation)

    st.progress(suitability["conditions_met"] / suitability["total_conditions"])

    st.caption(
        f"충족 조건: {suitability['conditions_met']} / {suitability['total_conditions']}"
    )

    if not suitability["is_complete"] and suitability.get("missing_conditions"):
        with st.expander("누락된 판단 지표 보기"):
            for item in suitability["missing_conditions"]:
                st.write(f"- {item}")

    st.markdown("#### 판단 근거")

    for rec in suitability["recommendations"]:
        st.write(f"- {rec}")

    st.markdown("---")

    # =====================================================
    # 기간 통계
    # =====================================================

    st.subheader(f"📌 {period_selection} 통계")

    tab1, tab2, tab3 = st.tabs(["원/달러 환율", "달러지수(DXY)", "달러 갭"])

    with tab1:
        c1, c2, c3, c4 = st.columns(4)

        c1.metric("현재 환율", f"₩{rate_stats.get('current', current_rate):,.2f}")

        if rate_stats:
            c2.metric("기간 중간가", f"₩{rate_stats.get('mid', 0):,.2f}")
            c3.metric("기간 최저", f"₩{rate_stats.get('min', 0):,.2f}")
            c4.metric("기간 최고", f"₩{rate_stats.get('max', 0):,.2f}")
        else:
            c2.metric("기간 중간가", "N/A")
            c3.metric("기간 최저", "N/A")
            c4.metric("기간 최고", "N/A")

        st.caption("기간 중간가는 일별 평균값이 아니라, 기간 내 최고값과 최저값의 중간 지점입니다.")

    with tab2:
        c1, c2, c3, c4 = st.columns(4)

        if dxy_stats:
            c1.metric("현재 DXY", f"{dxy_stats.get('current', 0):.2f}")
            c2.metric("기간 중간가", f"{dxy_stats.get('mid', 0):.2f}")
            c3.metric("기간 최저", f"{dxy_stats.get('min', 0):.2f}")
            c4.metric("기간 최고", f"{dxy_stats.get('max', 0):.2f}")
        else:
            st.warning("DXY 통계 데이터를 계산할 수 없습니다.")

    with tab3:
        c1, c2, c3 = st.columns(3)

        c1.metric(
            "현재 달러 갭 비율",
            f"{current_gap:.2f}" if current_gap is not None else "N/A",
        )

        c2.metric(
            "기준 달러 갭 비율",
            f"{mid_gap:.2f}" if mid_gap is not None else "N/A",
        )

        c3.metric(
            "적정 환율",
            f"₩{appropriate_rate:,.2f}" if appropriate_rate is not None else "N/A",
        )

        st.caption("달러 갭 비율 = 달러지수(DXY) ÷ 원/달러 환율 × 100")

    st.markdown("---")

    # =====================================================
    # 투자 상세 계산
    # =====================================================

    st.subheader("💰 투자 상세 계산")

    if investment_details:
        c1, c2, c3 = st.columns(3)

        with c1:
            st.metric("투자 원금", f"₩{investment_details['investment_amount']:,.0f}")
            st.metric("예상 환전 비용률", f"{investment_details['fee_rate_percent']:.3f}%")

        with c2:
            st.metric("예상 환전 비용", f"₩{investment_details['fee']:,.0f}")
            st.metric("실제 투자 반영 금액", f"₩{investment_details['net_investment']:,.0f}")

        with c3:
            st.metric("수수료 전 매수 가능 달러", f"${investment_details['gross_dollar']:,.2f}")
            st.metric("수수료 후 매수 가능 달러", f"${investment_details['net_dollar']:,.2f}")

    st.markdown("---")

    # =====================================================
    # 환율 변동 시나리오
    # =====================================================

    st.subheader("📈 환율 변동 시나리오")

    st.caption(
        "지금 매수한 달러 수량을 고정하고, 미래 환율 변화에 따른 원화 평가액을 계산합니다."
    )

    scenario_df = build_exchange_rate_scenarios(investment_details, current_rate)

    if not scenario_df.empty:
        st.dataframe(scenario_df, use_container_width=True, hide_index=True)

    st.markdown("---")

    # =====================================================
    # DXY 추세
    # =====================================================

    if dxy_mid_trend is not None:
        st.subheader("🌍 달러지수(DXY) 추세")

        c1, c2 = st.columns(2)

        c1.metric("20거래일 기준", dxy_mid_trend)
        c2.metric("5거래일 기준", dxy_short_trend)

        st.caption("단순 이동평균 기준의 참고용 추세입니다. 매수·매도 신호로 단독 사용하기에는 부족합니다.")

        st.markdown("---")

    # =====================================================
    # 환율 차트
    # =====================================================

    st.subheader("📉 원/달러 환율 차트")

    if rate_hist is not None and not rate_hist.empty:
        chart_data = rate_hist.tail(period_days).copy()
        chart_data = chart_data.reset_index()

        date_col = chart_data.columns[0]
        chart_data[date_col] = pd.to_datetime(chart_data[date_col])
        chart_data["MA20"] = chart_data["Close"].rolling(window=20).mean()

        fig = go.Figure()

        fig.add_trace(go.Scatter(
            x=chart_data[date_col],
            y=chart_data["Close"],
            mode="lines",
            name="원/달러 환율",
            line=dict(width=2),
        ))

        fig.add_trace(go.Scatter(
            x=chart_data[date_col],
            y=chart_data["MA20"],
            mode="lines",
            name="20일 이동평균",
            line=dict(width=1, dash="dash"),
        ))

        if gap_data and gap_data.get("rate_stats"):
            fig.add_hline(
                y=gap_data["rate_stats"]["mid"],
                line_dash="dot",
                annotation_text=f"{period_selection} 중간가",
                annotation_position="bottom right",
            )

        if appropriate_rate is not None:
            fig.add_hline(
                y=appropriate_rate,
                line_dash="dash",
                annotation_text="적정 환율",
                annotation_position="top right",
            )

        fig.update_layout(
            title="원/달러 환율 추이",
            xaxis_title="날짜",
            yaxis_title="환율(원)",
            hovermode="x unified",
            height=420,
        )

        st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")

    # =====================================================
    # 결과 다운로드
    # =====================================================

    st.subheader("📥 결과 다운로드")

    summary_rows = [
        {"항목": "분석일", "값": datetime.now().strftime("%Y-%m-%d %H:%M:%S")},
        {"항목": "분석 기간", "값": period_selection},
        {"항목": "환율 기준일", "값": format_data_date(rate_date)},
        {"항목": "DXY 기준일", "값": format_data_date(dxy_date)},
        {"항목": "선택한 환전 비용 가이드", "값": fee_preset_name},
        {"항목": "우대 전 기본 스프레드", "값": f"{base_spread_percent:.2f}%" if base_spread_percent is not None else "직접 입력"},
        {"항목": "환율우대율", "값": f"{preferential_discount_percent:.1f}%" if preferential_discount_percent is not None else "직접 입력"},
        {"항목": "예상 환전 비용률", "값": f"{fee_rate_percent:.3f}%"},
        {"항목": "현재 원/달러 환율", "값": f"{current_rate:,.2f}"},
        {"항목": "현재 DXY", "값": f"{current_dxy:.2f}" if current_dxy is not None else "N/A"},
        {"항목": "현재 달러 갭 비율", "값": f"{current_gap:.2f}" if current_gap is not None else "N/A"},
        {"항목": "기준 달러 갭 비율", "값": f"{mid_gap:.2f}" if mid_gap is not None else "N/A"},
        {"항목": "적정 환율", "값": f"{appropriate_rate:,.2f}" if appropriate_rate is not None else "N/A"},
        {"항목": "달러 매수 적합성", "값": decision},
        {"항목": "충족 조건 수", "값": f"{suitability['conditions_met']} / {suitability['total_conditions']}"},
        {"항목": "투자 원금", "값": f"{investment_amount:,.0f}"},
        {"항목": "수수료 후 매수 가능 달러", "값": f"{investment_details['net_dollar']:,.2f}" if investment_details else "N/A"},
    ]

    summary_df = pd.DataFrame(summary_rows)
    csv_data = summary_df.to_csv(index=False).encode("utf-8-sig")

    st.download_button(
        label="분석 결과 CSV 다운로드",
        data=csv_data,
        file_name=f"dollar_suitability_{datetime.now().strftime('%Y%m%d')}.csv",
        mime="text/csv",
    )

else:
    st.info("왼쪽 사이드바에서 투자 금액과 분석 기간을 설정한 뒤, '분석하기' 버튼을 눌러주세요.")

    st.markdown("### 💡 앱의 판단 기준")

    st.markdown(
        """
        이 앱은 달러 매수 적합성을 다음 4가지 조건으로 점검합니다.

        1. 현재 원/달러 환율이 기간 중간가보다 낮은가?
        2. 현재 달러지수(DXY)가 기간 중간가보다 낮은가?
        3. 현재 달러 갭 비율이 기준 달러 갭 비율보다 높은가?
        4. 현재 원/달러 환율이 적정 환율보다 낮은가?

        ※ 기간 중간가는 일별 평균값이 아니라, 해당 기간의 최고값과 최저값의 중간 지점입니다.
        """
    )

    st.markdown("### 💱 환전 비용률 계산 방식")

    st.markdown(
        """
        환전 비용률은 다음 방식으로 단순 추정합니다.

        **예상 환전 비용률 = 우대 전 기본 스프레드 × (1 - 환율우대율)**

        예를 들어 기본 스프레드가 1.50%이고 환율우대가 90%라면  
        실제 부담 비용률은 1.50% × 10% = **0.15%**입니다.

        사용자가 정확한 수수료를 모르는 경우에는 왼쪽 사이드바에서  
        `하나은행 환전지갑`, `증권사 95% 환전우대` 같은 가이드를 선택하면 됩니다.
        """
    )

    st.markdown("### ⚠️ 유의사항")

    st.markdown(
        """
        - 이 앱은 투자 추천 도구가 아니라 교육용 적합성 가이드입니다.
        - 실제 환전가는 은행·증권사별 고시환율, 환전 우대율, 이벤트 적용 여부, 거래 시간에 따라 달라질 수 있습니다.
        - 환율 데이터와 DXY 데이터는 기준 시간이 다를 수 있습니다.
        - 달러 투자는 환율 변동에 따라 원금 손실이 발생할 수 있습니다.
        """
    )
