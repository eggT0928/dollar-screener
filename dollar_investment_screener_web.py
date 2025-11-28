import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import plotly.graph_objects as go


def get_exchange_rate():
    """원/달러 환율 조회"""
    try:
        # KRW=X는 원/달러 환율 티커
        ticker = yf.Ticker("KRW=X")
        hist = ticker.history(period="1y")
        if hist.empty:
            return None, None
        
        current_rate = hist["Close"].iloc[-1]
        return current_rate, hist
    except Exception as e:
        st.error(f"환율 조회 실패: {e}")
        return None, None


def get_dxy_index():
    """달러 인덱스 (DXY) 조회"""
    try:
        ticker = yf.Ticker("DX-Y.NYB")
        hist = ticker.history(period="1y")
        if hist.empty:
            return None, None
        
        current_dxy = hist["Close"].iloc[-1]
        return current_dxy, hist
    except Exception as e:
        st.warning(f"DXY 조회 실패: {e}")
        return None, None


def calculate_dollar_gap_ratio(current_rate, rate_hist, current_dxy, dxy_hist, period_days=252):
    """
    달러 갭 비율 및 적정 환율 계산 (블로그 기준)
    - 52주 중간가 = (최저 + 최고) / 2
    - 달러 갭 비율 = DXY / 환율 * 100
    - 적정 환율 = 현재 DXY / 52주 중간 달러 갭 비율 * 100
    """
    if rate_hist is None or len(rate_hist) < period_days:
        return None, None, None, None, None
    
    # 환율 52주 통계
    recent_rate = rate_hist.tail(period_days)
    rate_min = recent_rate["Close"].min()
    rate_max = recent_rate["Close"].max()
    rate_mid = (rate_min + rate_max) / 2  # 52주 중간가
    
    # 환율이 중간가보다 낮은지 여부
    rate_vs_mid = ((current_rate - rate_mid) / rate_mid) * 100
    
    # DXY 52주 통계
    dxy_mid = None
    dxy_vs_mid = None
    if dxy_hist is not None and len(dxy_hist) >= period_days:
        recent_dxy = dxy_hist.tail(period_days)
        dxy_min = recent_dxy["Close"].min()
        dxy_max = recent_dxy["Close"].max()
        dxy_mid = (dxy_min + dxy_max) / 2  # 52주 중간가
        
        if current_dxy:
            dxy_vs_mid = ((current_dxy - dxy_mid) / dxy_mid) * 100
    
    # 달러 갭 비율 계산
    current_gap_ratio = None
    mid_gap_ratio = None
    appropriate_rate = None
    
    if current_dxy and current_rate > 0:
        # 현재 달러 갭 비율 = 현재 DXY / 현재 환율 * 100
        current_gap_ratio = (current_dxy / current_rate) * 100
        
        # 52주 중간 달러 갭 비율 = 52주 중간 DXY / 52주 중간 환율 * 100
        if dxy_mid:
            mid_gap_ratio = (dxy_mid / rate_mid) * 100
            
            # 적정 환율 = 현재 DXY / 52주 중간 달러 갭 비율 * 100
            appropriate_rate = (current_dxy / mid_gap_ratio) * 100
    
    return {
        "rate_vs_mid": rate_vs_mid,  # 환율이 중간가 대비 얼마나 높은지/낮은지
        "dxy_vs_mid": dxy_vs_mid,  # DXY가 중간가 대비 얼마나 높은지/낮은지
        "current_gap_ratio": current_gap_ratio,  # 현재 달러 갭 비율
        "mid_gap_ratio": mid_gap_ratio,  # 52주 중간 달러 갭 비율
        "appropriate_rate": appropriate_rate,  # 적정 환율
        "rate_stats": {
            "current": current_rate,
            "mid": rate_mid,
            "min": rate_min,
            "max": rate_max
        },
        "dxy_stats": {
            "current": current_dxy,
            "mid": dxy_mid,
            "min": recent_dxy["Close"].min() if dxy_hist is not None and len(dxy_hist) >= period_days else None,
            "max": recent_dxy["Close"].max() if dxy_hist is not None and len(dxy_hist) >= period_days else None
        } if dxy_hist is not None and len(dxy_hist) >= period_days else None
    }


def analyze_dxy_trend(dxy_hist):
    """DXY 추세 분석"""
    if dxy_hist is None or len(dxy_hist) < 20:
        return None, None
    
    recent = dxy_hist.tail(20)
    current = recent["Close"].iloc[-1]
    ma20 = recent["Close"].mean()
    
    # 단기 추세 (5일 평균)
    ma5 = recent.tail(5)["Close"].mean()
    
    trend = "상승" if current > ma20 else "하락"
    short_trend = "상승" if current > ma5 else "하락"
    
    return trend, short_trend


def get_investment_recommendation(gap_data):
    """
    투자 판단 추천 (블로그 기준 4가지 조건)
    1. 현재 환율이 52주 중간가보다 낮을 때
    2. 현재 DXY가 52주 중간가보다 낮을 때
    3. 현재 달러 갭 비율이 52주 중간 갭 비율보다 높을 때
    4. 현재 환율이 적정 환율보다 낮을 때
    """
    if gap_data is None:
        return "데이터 부족", "분석에 필요한 데이터가 충분하지 않습니다.", [], 0
    
    recommendations = []
    conditions_met = 0
    total_conditions = 0
    
    # 조건 1: 현재 환율이 52주 중간가보다 낮을 때
    if gap_data["rate_vs_mid"] is not None:
        total_conditions += 1
        if gap_data["rate_vs_mid"] < 0:
            recommendations.append("✅ 조건 1: 현재 원/달러 환율이 52주 중간가보다 낮음 (매수 유리)")
            conditions_met += 1
        else:
            recommendations.append(f"❌ 조건 1: 현재 원/달러 환율이 52주 중간가보다 높음 ({gap_data['rate_vs_mid']:+.2f}%)")
    
    # 조건 2: 현재 DXY가 52주 중간가보다 낮을 때
    if gap_data["dxy_vs_mid"] is not None:
        total_conditions += 1
        if gap_data["dxy_vs_mid"] < 0:
            recommendations.append("✅ 조건 2: 현재 달러 지수가 52주 중간가보다 낮음 (매수 유리)")
            conditions_met += 1
        else:
            recommendations.append(f"❌ 조건 2: 현재 달러 지수가 52주 중간가보다 높음 ({gap_data['dxy_vs_mid']:+.2f}%)")
    
    # 조건 3: 현재 달러 갭 비율이 52주 중간 갭 비율보다 높을 때
    if gap_data["current_gap_ratio"] is not None and gap_data["mid_gap_ratio"] is not None:
        total_conditions += 1
        gap_diff = gap_data["current_gap_ratio"] - gap_data["mid_gap_ratio"]
        if gap_diff > 0:
            recommendations.append(f"✅ 조건 3: 현재 달러 갭 비율이 52주 중간 갭 비율보다 높음 (+{gap_diff:.2f}, 매수 유리)")
            conditions_met += 1
        else:
            recommendations.append(f"❌ 조건 3: 현재 달러 갭 비율이 52주 중간 갭 비율보다 낮음 ({gap_diff:.2f})")
    
    # 조건 4: 현재 환율이 적정 환율보다 낮을 때
    if gap_data["appropriate_rate"] is not None and gap_data["rate_stats"]["current"] is not None:
        total_conditions += 1
        rate_diff = gap_data["rate_stats"]["current"] - gap_data["appropriate_rate"]
        rate_diff_pct = (rate_diff / gap_data["appropriate_rate"]) * 100
        if rate_diff < 0:
            recommendations.append(f"✅ 조건 4: 현재 환율이 적정 환율보다 낮음 ({rate_diff_pct:+.2f}%, 매수 유리)")
            conditions_met += 1
        else:
            recommendations.append(f"❌ 조건 4: 현재 환율이 적정 환율보다 높음 ({rate_diff_pct:+.2f}%)")
    
    # 최종 판단
    if total_conditions == 0:
        decision = "데이터 부족"
        explanation = "분석에 필요한 데이터가 충분하지 않습니다."
    elif conditions_met == total_conditions:
        decision = "🟢 매수 추천"
        explanation = f"4가지 조건 중 {conditions_met}개를 모두 만족합니다. 달러 투자에 매우 유리한 시점입니다."
    elif conditions_met >= total_conditions * 0.75:
        decision = "🟡 매수 고려"
        explanation = f"4가지 조건 중 {conditions_met}개를 만족합니다. 달러 투자를 고려해볼 수 있는 시점입니다."
    elif conditions_met >= total_conditions * 0.5:
        decision = "⚪ 보유/관망"
        explanation = f"4가지 조건 중 {conditions_met}개를 만족합니다. 중립적인 시점입니다."
    elif conditions_met >= total_conditions * 0.25:
        decision = "🟠 매수 신중"
        explanation = f"4가지 조건 중 {conditions_met}개만 만족합니다. 달러 투자에 다소 불리할 수 있습니다."
    else:
        decision = "🔴 매수 비추천"
        explanation = f"4가지 조건 중 {conditions_met}개만 만족합니다. 달러 투자에 불리한 시점입니다."
    
    return decision, explanation, recommendations, conditions_met


def calculate_investment_details(investment_amount, current_rate):
    """투자 상세 계산"""
    if current_rate is None:
        return None
    
    # 달러 구매 가능 금액
    dollar_amount = investment_amount / current_rate
    
    # 수수료 고려 (일반적으로 0.1~0.3% 가정)
    fee_rate = 0.002  # 0.2% 수수료
    fee = investment_amount * fee_rate
    net_investment = investment_amount - fee
    net_dollar = net_investment / current_rate
    
    return {
        "investment_amount": investment_amount,
        "current_rate": current_rate,
        "dollar_amount": dollar_amount,
        "fee": fee,
        "net_investment": net_investment,
        "net_dollar": net_dollar,
        "fee_rate": fee_rate * 100
    }


# ==== Streamlit 앱 메인 ====
st.set_page_config(
    page_title="달러 투자 판단 스크리너",
    page_icon="💵",
    layout="wide"
)

st.title("💵 달러 투자 판단 스크리너")
st.markdown("---")

# 사이드바에 입력 필드
with st.sidebar:
    st.header("⚙️ 설정")
    
    investment_amount = st.number_input(
        "투자 금액 (원)",
        min_value=0.0,
        value=1000000.0,
        step=100000.0,
        format="%.0f",
        help="달러로 투자할 원화 금액을 입력하세요."
    )
    
    st.markdown("---")
    st.subheader("📊 분석 기간")
    
    period_days = st.selectbox(
        "평균 계산 기간",
        options=[126, 252, 504],
        index=1,
        format_func=lambda x: f"{x}일 ({x//21}개월)",
        help="평균 환율 계산에 사용할 기간을 선택하세요."
    )
    
    st.markdown("---")
    
    if st.button("🚀 분석하기", type="primary", use_container_width=True):
        if investment_amount <= 0:
            st.error("투자 금액은 0보다 커야 합니다.")
        else:
            st.session_state['analyze'] = True
            st.session_state['investment_amount'] = investment_amount
            st.session_state['period_days'] = period_days
    
    if st.button("🔄 초기화", use_container_width=True):
        if 'analyze' in st.session_state:
            del st.session_state['analyze']
        st.rerun()

# 메인 영역에 결과 표시
if st.session_state.get('analyze', False):
    investment_amount = st.session_state.get('investment_amount', 0)
    period_days = st.session_state.get('period_days', 252)
    
    # 데이터 조회
    with st.spinner("환율 및 달러 인덱스 데이터를 조회하는 중..."):
        current_rate, rate_hist = get_exchange_rate()
        current_dxy, dxy_hist = get_dxy_index()
    
    if current_rate is None:
        st.error("환율 데이터를 가져올 수 없습니다. 잠시 후 다시 시도해주세요.")
    else:
        # 달러 갭 비율 및 적정 환율 계산 (블로그 기준)
        gap_data = calculate_dollar_gap_ratio(
            current_rate, rate_hist, current_dxy, dxy_hist, period_days
        )
        
        # DXY 추세 분석
        dxy_trend, dxy_short_trend = analyze_dxy_trend(dxy_hist)
        
        # 투자 판단 (블로그 기준 4가지 조건)
        decision, explanation, recommendations, conditions_met = get_investment_recommendation(gap_data)
        
        # 투자 상세 계산
        investment_details = calculate_investment_details(investment_amount, current_rate)
        
        # ==== 요약 정보 ====
        st.subheader("📈 현재 시장 상황")
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            if gap_data and gap_data["rate_stats"]:
                rate_vs_mid = gap_data.get("rate_vs_mid")
                delta_text = f"{rate_vs_mid:+.2f}%" if rate_vs_mid is not None else None
                st.metric(
                    "현재 환율",
                    f"₩{current_rate:,.2f}",
                    delta=delta_text,
                    delta_color="inverse" if rate_vs_mid and rate_vs_mid < 0 else "normal"
                )
            else:
                st.metric("현재 환율", f"₩{current_rate:,.2f}")
        
        with col2:
            if current_dxy:
                dxy_vs_mid = gap_data.get("dxy_vs_mid") if gap_data else None
                delta_text = f"{dxy_vs_mid:+.2f}%" if dxy_vs_mid is not None else None
                st.metric(
                    "달러 인덱스 (DXY)",
                    f"{current_dxy:.2f}",
                    delta=delta_text,
                    delta_color="inverse" if dxy_vs_mid and dxy_vs_mid < 0 else "normal"
                )
            else:
                st.metric("달러 인덱스 (DXY)", "N/A")
        
        with col3:
            if gap_data and gap_data.get("current_gap_ratio") is not None:
                st.metric(
                    "현재 달러 갭 비율",
                    f"{gap_data['current_gap_ratio']:.2f}",
                    help="달러 지수 / 원/달러 환율 * 100"
                )
            else:
                st.metric("현재 달러 갭 비율", "N/A")
        
        with col4:
            if gap_data and gap_data.get("appropriate_rate") is not None:
                rate_diff = current_rate - gap_data["appropriate_rate"]
                rate_diff_pct = (rate_diff / gap_data["appropriate_rate"]) * 100
                st.metric(
                    "적정 환율",
                    f"₩{gap_data['appropriate_rate']:,.2f}",
                    delta=f"{rate_diff_pct:+.2f}%",
                    delta_color="inverse" if rate_diff < 0 else "normal",
                    help="현재 달러 지수 / 52주 중간 달러 갭 비율 * 100"
                )
            else:
                st.metric("적정 환율", "N/A")
        
        st.markdown("---")
        
        # ==== 투자 판단 ====
        st.subheader("🎯 투자 판단")
        
        # 판단 결과를 큰 카드로 표시
        decision_color = {
            "🟢 매수 추천": "success",
            "🟡 매수 고려": "info",
            "⚪ 보유/관망": "",
            "🟠 매수 신중": "warning",
            "🔴 매수 비추천": "error"
        }.get(decision, "")
        
        if decision_color == "success":
            st.success(f"## {decision}")
        elif decision_color == "info":
            st.info(f"## {decision}")
        elif decision_color == "warning":
            st.warning(f"## {decision}")
        elif decision_color == "error":
            st.error(f"## {decision}")
        else:
            st.markdown(f"## {decision}")
        
        st.markdown(f"**{explanation}**")
        
        st.markdown("---")
        
        # 판단 근거
        st.subheader("📋 판단 근거")
        for rec in recommendations:
            st.markdown(f"- {rec}")
        
        st.markdown("---")
        
        # ==== 환율 통계 ====
        if gap_data and gap_data.get("rate_stats"):
            st.subheader("📊 환율 통계 (52주)")
            col1, col2, col3, col4 = st.columns(4)
            rate_stats = gap_data["rate_stats"]
            
            with col1:
                st.metric("현재 환율", f"₩{rate_stats['current']:,.2f}")
            with col2:
                st.metric("52주 중간가", f"₩{rate_stats['mid']:,.2f}")
            with col3:
                st.metric("52주 최저", f"₩{rate_stats['min']:,.2f}")
            with col4:
                st.metric("52주 최고", f"₩{rate_stats['max']:,.2f}")
        
        # ==== DXY 통계 ====
        if gap_data and gap_data.get("dxy_stats") and gap_data["dxy_stats"]:
            st.subheader("📊 달러 인덱스 (DXY) 통계 (52주)")
            col1, col2, col3, col4 = st.columns(4)
            dxy_stats = gap_data["dxy_stats"]
            
            with col1:
                st.metric("현재 DXY", f"{dxy_stats['current']:.2f}" if dxy_stats['current'] else "N/A")
            with col2:
                st.metric("52주 중간가", f"{dxy_stats['mid']:.2f}" if dxy_stats['mid'] else "N/A")
            with col3:
                st.metric("52주 최저", f"{dxy_stats['min']:.2f}" if dxy_stats['min'] else "N/A")
            with col4:
                st.metric("52주 최고", f"{dxy_stats['max']:.2f}" if dxy_stats['max'] else "N/A")
        
        # ==== 달러 갭 비율 상세 ====
        if gap_data and gap_data.get("current_gap_ratio") is not None:
            st.subheader("📊 달러 갭 비율 상세")
            col1, col2 = st.columns(2)
            
            with col1:
                st.metric("현재 달러 갭 비율", f"{gap_data['current_gap_ratio']:.2f}")
            with col2:
                if gap_data.get("mid_gap_ratio") is not None:
                    gap_diff = gap_data["current_gap_ratio"] - gap_data["mid_gap_ratio"]
                    st.metric(
                        "52주 중간 갭 비율",
                        f"{gap_data['mid_gap_ratio']:.2f}",
                        delta=f"{gap_diff:+.2f}",
                        help="현재 갭 비율이 중간 갭 비율보다 높으면 매수 유리"
                    )
        
        st.markdown("---")
        
        # ==== 투자 상세 ====
        if investment_details:
            st.subheader("💰 투자 상세 계산")
            
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.metric("투자 금액", f"₩{investment_details['investment_amount']:,.0f}")
                st.metric("수수료 (약 {:.1f}%)".format(investment_details['fee_rate']), 
                         f"₩{investment_details['fee']:,.0f}")
            
            with col2:
                st.metric("현재 환율", f"₩{investment_details['current_rate']:,.2f}")
                st.metric("순 투자 금액", f"₩{investment_details['net_investment']:,.0f}")
            
            with col3:
                st.metric("구매 가능 달러", f"${investment_details['dollar_amount']:,.2f}")
                st.metric("수수료 제외 달러", f"${investment_details['net_dollar']:,.2f}")
            
            # 환율 변동 시나리오
            st.markdown("---")
            st.subheader("📈 환율 변동 시나리오")
            
            scenarios = [-5, -3, -1, 0, 1, 3, 5]
            scenario_data = []
            
            for change_pct in scenarios:
                new_rate = current_rate * (1 + change_pct / 100)
                new_dollar = investment_details['net_investment'] / new_rate
                profit_loss = (new_dollar - investment_details['net_dollar']) * current_rate
                
                scenario_data.append({
                    "환율 변동": f"{change_pct:+.1f}%",
                    "예상 환율": f"₩{new_rate:,.2f}",
                    "보유 달러": f"${new_dollar:,.2f}",
                    "손익 (원)": f"₩{profit_loss:+,.0f}"
                })
            
            scenario_df = pd.DataFrame(scenario_data)
            st.dataframe(scenario_df, use_container_width=True, hide_index=True)
        
        # ==== DXY 추세 ====
        if dxy_trend:
            st.markdown("---")
            st.subheader("🌍 달러 인덱스 (DXY) 추세")
            col1, col2 = st.columns(2)
            with col1:
                st.metric("중기 추세", dxy_trend)
            with col2:
                st.metric("단기 추세", dxy_short_trend)
        
        # ==== 환율 차트 ====
        if rate_hist is not None and len(rate_hist) > 0:
            st.markdown("---")
            st.subheader("📉 환율 차트")
            
            chart_data = rate_hist.tail(period_days).copy()
            chart_data = chart_data.reset_index()
            chart_data['Date'] = pd.to_datetime(chart_data['Date'])
            
            # 평균선 추가
            chart_data['MA'] = chart_data['Close'].rolling(window=20).mean()
            
            fig = go.Figure()
            
            # 환율 라인
            fig.add_trace(go.Scatter(
                x=chart_data['Date'],
                y=chart_data['Close'],
                mode='lines',
                name='환율',
                line=dict(color='#1f77b4', width=2)
            ))
            
            # 평균선
            fig.add_trace(go.Scatter(
                x=chart_data['Date'],
                y=chart_data['MA'],
                mode='lines',
                name='20일 이동평균',
                line=dict(color='orange', width=1, dash='dash')
            ))
            
            # 현재 환율 표시
            if len(chart_data) > 0:
                fig.add_trace(go.Scatter(
                    x=[chart_data['Date'].iloc[-1]],
                    y=[current_rate],
                    mode='markers',
                    name='현재',
                    marker=dict(color='red', size=10, symbol='star')
                ))
            
            fig.update_layout(
                title="원/달러 환율 추이",
                xaxis_title="날짜",
                yaxis_title="환율 (원)",
                hovermode='x unified',
                height=400
            )
            
            st.plotly_chart(fig, use_container_width=True)
        
        # ==== CSV 다운로드 ====
        if rate_hist is not None:
            st.markdown("---")
            summary_data = {
                "항목": [
                    "현재 환율", "52주 중간가 대비 (%)", "현재 DXY", "52주 중간가 대비 (%)",
                    "현재 달러 갭 비율", "52주 중간 갭 비율", "적정 환율",
                    "투자 금액 (원)", "구매 가능 달러 ($)",
                    "투자 판단", "만족 조건 수"
                ],
                "값": [
                    f"{current_rate:,.2f}",
                    f"{gap_data.get('rate_vs_mid', 0):+.2f}%" if gap_data else "N/A",
                    f"{current_dxy:.2f}" if current_dxy else "N/A",
                    f"{gap_data.get('dxy_vs_mid', 0):+.2f}%" if gap_data and gap_data.get('dxy_vs_mid') is not None else "N/A",
                    f"{gap_data.get('current_gap_ratio', 0):.2f}" if gap_data and gap_data.get('current_gap_ratio') is not None else "N/A",
                    f"{gap_data.get('mid_gap_ratio', 0):.2f}" if gap_data and gap_data.get('mid_gap_ratio') is not None else "N/A",
                    f"₩{gap_data.get('appropriate_rate', 0):,.2f}" if gap_data and gap_data.get('appropriate_rate') is not None else "N/A",
                    f"{investment_amount:,.0f}",
                    f"${investment_details['dollar_amount']:,.2f}" if investment_details else "N/A",
                    decision,
                    str(conditions_met)
                ]
            }
            summary_df = pd.DataFrame(summary_data)
            
            csv = summary_df.to_csv(index=False)
            st.download_button(
                label="📥 분석 결과 CSV 다운로드",
                data=csv,
                file_name=f"dollar_investment_analysis_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv"
            )

else:
    st.info("👈 왼쪽 사이드바에서 투자 금액을 입력하고 '분석하기' 버튼을 클릭하세요.")
    
    # 설명
    st.markdown("### 💡 사용 방법")
    st.markdown("""
    1. **투자 금액 입력**: 달러로 투자할 원화 금액을 입력합니다.
    2. **분석 기간 선택**: 평균 환율 계산에 사용할 기간을 선택합니다.
    3. **분석하기 클릭**: 현재 시장 상황을 분석하여 투자 판단을 제공합니다.
    
    **주요 기능 (블로그 기준):**
    - 현재 원/달러 환율 조회 및 52주 중간가 비교
    - 달러 인덱스 (DXY) 조회 및 52주 중간가 비교
    - 달러 갭 비율 계산 (달러 지수 / 환율 * 100)
    - 적정 환율 계산 (현재 DXY / 52주 중간 갭 비율 * 100)
    - 4가지 조건 기반 투자 판단
    - 투자 상세 계산 (구매 가능 달러, 수수료 등)
    - 환율 변동 시나리오 분석
    
    **투자 판단 기준:**
    1. 현재 환율이 52주 중간가보다 낮을 때 ✅
    2. 현재 DXY가 52주 중간가보다 낮을 때 ✅
    3. 현재 달러 갭 비율이 52주 중간 갭 비율보다 높을 때 ✅
    4. 현재 환율이 적정 환율보다 낮을 때 ✅
    """)

