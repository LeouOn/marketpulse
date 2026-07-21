"""Warsh Scenario Simulator — Interactive Streamlit Dashboard.

Run with:
    streamlit run scripts/warsh_dashboard.py

Features:
- 6 QE-without-QE tool sliders with live curve updates
- Fed Chair persona rating (gamification)
- Roll Market Event button (X-factor + black swan shocks)
- Scenario match bars (A/B/C hypothesis tracking)
- Market prediction cards (stocks/bonds/gold/crypto/oil/dollar)
- Live FRED data integration
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import streamlit as st
import plotly.graph_objects as go

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.warsh.tools import ToolName, get_all_tools
from src.warsh.simulator import CurveSimulator, ALL_TENORS
from src.warsh.events import roll_event, apply_event_to_curve
from src.warsh.gamification import rate_fed_chair, calculate_scenario_match, get_market_prediction

st.set_page_config(page_title="Warsh Simulator", page_icon="🏦", layout="wide")

TENOR_LABELS = ["3M", "1Y", "2Y", "5Y", "7Y", "10Y", "20Y", "30Y"]
FALLBACK_CURVE = {
    "3mo": 3.84, "1y": 4.02, "2y": 4.16, "5y": 4.31,
    "7y": 4.44, "10y": 4.58, "20y": 5.09, "30y": 5.08,
}


@st.cache_data(ttl=3600)
def load_current_curve():
    try:
        from src.yield_curve.fetcher import FredCurveFetcher
        f = FredCurveFetcher()
        today = date.today()
        data = f.fetch_tenors(ALL_TENORS, today - timedelta(days=10), today)
        curve = {}
        for tenor, df in data.items():
            if not df.empty:
                curve[tenor] = float(df.iloc[-1]["close"])
        return curve if curve else FALLBACK_CURVE
    except Exception:
        return FALLBACK_CURVE


baseline_curve = load_current_curve()
sim = CurveSimulator(baseline_curve)
tools_list = get_all_tools()

if "tool_values" not in st.session_state:
    st.session_state.tool_values = {t.name: t.current_value for t in tools_list}
if "rolled_event" not in st.session_state:
    st.session_state.rolled_event = None

st.title("🏦 Warsh Scenario Simulator")
st.markdown("*Adjust Fed tools, roll for market events, see the curve respond.*")

# ---- Sidebar: Tool sliders ----
st.sidebar.markdown("## 🎛️ Policy Tools")

preset = st.sidebar.selectbox("Quick Scenario", ["custom", "current", "hawkish", "pantomime", "dovish"], index=1)
if preset != "custom":
    presets = CurveSimulator.SCENARIO_PRESETS.get(preset, {})
    if presets:
        st.session_state.tool_values[ToolName.RMP] = presets["rmp"]
        st.session_state.tool_values[ToolName.QT_PACE] = presets["qt_pace"]
        st.session_state.tool_values[ToolName.SRF] = presets["srf"]
        st.session_state.tool_values[ToolName.MBS_SALES] = presets["mbs_sales"]
        st.session_state.tool_values[ToolName.FORWARD_GUIDANCE] = presets["forward_guidance"]
        st.session_state.tool_values[ToolName.BANK_REGULATION] = presets["bank_regulation"]

st.sidebar.markdown("---")

for tool in tools_list:
    current = st.session_state.tool_values.get(tool.name, tool.current_value)
    if tool.is_boolean:
        val = st.sidebar.selectbox(
            tool.display_name,
            ["Active (1)", "Removed (0)"],
            index=0 if current >= 0.5 else 1,
            help=tool.description,
        )
        st.session_state.tool_values[tool.name] = 1.0 if "Active" in val else 0.0
    else:
        val = st.sidebar.slider(
            tool.display_name,
            min_value=float(tool.min_value),
            max_value=float(tool.max_value),
            value=float(current),
            help=tool.description,
        )
        st.session_state.tool_values[tool.name] = val
    st.sidebar.caption(f"_{tool.political_cover}_")

# ---- Run simulation ----
tv = st.session_state.tool_values
result = sim.simulate(
    rmp=tv[ToolName.RMP], qt_pace=tv[ToolName.QT_PACE], srf=tv[ToolName.SRF],
    mbs_sales=tv[ToolName.MBS_SALES], forward_guidance=tv[ToolName.FORWARD_GUIDANCE],
    bank_regulation=tv[ToolName.BANK_REGULATION],
)

# Apply event if rolled
event_curve = None
if st.session_state.rolled_event:
    event_curve = apply_event_to_curve(st.session_state.rolled_event, result.adjusted_curve)

# ---- Top row: Fed Chair rating + key metrics ----
col_rating, col_metrics = st.columns([2, 3])

with col_rating:
    persona, emoji, desc = rate_fed_chair(tv)
    st.markdown(f"### {emoji} {persona}")
    st.markdown(f"*{desc}*")

with col_metrics:
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("2s10s", f"{result.new_2s10s:.0f} bps", f"{result.delta_2s10s:+.1f}")
    with c2:
        if event_curve:
            from src.yield_curve.curves import compute_spreads
            ev_spreads = compute_spreads(event_curve)
            ev_2s10s = ev_spreads.get("2s10s", result.new_2s10s)
            st.metric("2s10s (w/event)", f"{ev_2s10s:.0f} bps", f"{ev_2s10s - result.baseline_2s10s:+.1f}")
        else:
            st.metric("Shape", result.new_shape)
    with c3:
        st.metric("Baseline", f"{result.baseline_2s10s:.0f} bps")

st.markdown("---")

# ---- Middle row: Event button + curve chart ----
col_event, col_chart = st.columns([1, 3])

with col_event:
    st.markdown("### 🎲 Market Events")
    if st.button("🎲 Roll Market Event", use_container_width=True, type="primary"):
        event = roll_event()
        st.session_state.rolled_event = event

    if st.button("🧹 Clear Event", use_container_width=True):
        st.session_state.rolled_event = None

    if st.session_state.rolled_event:
        ev = st.session_state.rolled_event
        category_color = "🔴" if ev.category == "black_swan" else "🟡"
        st.markdown(f"**{category_color} {ev.emoji} {ev.name}**")
        st.markdown(f"*{ev.description}*")
        st.markdown(f"Category: `{ev.category}`")
        st.markdown("**Market Reaction:**")
        for asset, direction in ev.market_reaction.items():
            icon = "📈" if direction == "up" else "📉" if direction == "down" else "➡️"
            st.text(f"  {icon} {asset}: {direction}")
    else:
        st.info("Click roll to trigger a random market event.")

    st.markdown("---")
    st.markdown("### 🎯 Scenario Match")
    match = calculate_scenario_match(tv)
    labels = {"A": "Hawk", "B": "Pantomime", "C": "Transition"}
    for key in ["A", "B", "C"]:
        pct = match.get(key, 0) * 100
        st.progress(int(pct), text=f"Scenario {key} ({labels[key]}): {pct:.0f}%")

with col_chart:
    st.markdown("### 📊 Yield Curve")
    baseline_y = [baseline_curve.get(t, 0) for t in ALL_TENORS]
    sim_y = [result.adjusted_curve.get(t, 0) for t in ALL_TENORS]

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=TENOR_LABELS, y=baseline_y, name="Current (FRED)",
                             line=dict(color="royalblue", width=2)))
    fig.add_trace(go.Scatter(x=TENOR_LABELS, y=sim_y, name="Simulated",
                             line=dict(color="orange", width=2, dash="dash")))
    if event_curve:
        event_y = [event_curve.get(t, 0) for t in ALL_TENORS]
        fig.add_trace(go.Scatter(x=TENOR_LABELS, y=event_y, name="With Event Shock",
                                 line=dict(color="red", width=2.5, dash="dot")))
    fig.update_layout(xaxis_title="Maturity", yaxis_title="Yield (%)",
                      yaxis=dict(range=[3.0, 6.5]), height=400, hovermode="x unified")
    st.plotly_chart(fig, use_container_width=True)

    with st.expander("Tool Effect Breakdown"):
        for tool_name_str, effects in result.tool_effects.items():
            tool = next((t for t in tools_list if t.name.value == tool_name_str), None)
            if tool and effects:
                nonzero = {k: v for k, v in effects.items() if abs(v) > 0.01}
                if nonzero:
                    parts = [f"{t}: {v:+.1f}bps" for t, v in sorted(nonzero.items())]
                    st.text(f"  {tool.display_name}: {', '.join(parts)}")

st.markdown("---")

# ---- Market predictions ----
st.markdown("### 💹 Market Predictions")
pred = get_market_prediction(tv)
pred_cols = st.columns(6)
asset_icons = {"stocks": "📈", "bonds": "🏛️", "gold": "🥇", "crypto": "₿", "oil": "🛢️", "dollar": "💵"}
for i, (asset, direction) in enumerate(pred.items()):
    with pred_cols[i]:
        icon = asset_icons.get(asset, "📊")
        if "bull" in direction or direction == "up":
            color = "green"
            arrow = "📈"
        elif "bear" in direction or direction == "down":
            color = "red"
            arrow = "📉"
        else:
            color = "gray"
            arrow = "➡️"
        st.markdown(f"**{icon} {asset.title()}**")
        st.markdown(f"<span style='color:{color}'>{arrow} {direction}</span>", unsafe_allow_html=True)

st.markdown("---")

# ---- Positioning ----
st.markdown("### 💼 Positioning Implications")

if result.delta_2s10s > 10:
    st.success(f"**Curve steepening +{result.delta_2s10s:.0f}bps** — Scenario B/C accelerating. "
               f"Banks absorbing supply. Value rotation beginning.")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Own:** Value stocks (INTU, ADBE), Small caps (IWM), Gold, BTC")
    with col2:
        st.markdown("**Avoid:** Long bonds, chasing AI momentum at highs")
elif result.delta_2s10s > 3:
    st.info(f"**Gradual steepening +{result.delta_2s10s:.0f}bps** — Scenario C unfolding. "
            f"Patient accumulation window.")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Accumulate:** Quality value on pullbacks (MSFT, CRM, ORCL)")
    with col2:
        st.markdown("**Avoid:** YOLO entries, chasing spikes")
elif result.delta_2s10s > -3:
    st.warning(f"**Curve flat ({result.delta_2s10s:+.0f}bps)** — Status quo. Capital preservation.")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Hold:** Cash, short-duration, existing positions")
    with col2:
        st.markdown("**Avoid:** New deployments until curve signal")
else:
    st.error(f"**Curve flattening ({result.delta_2s10s:+.0f}bps)** — Scenario A dominant. Defensive.")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Own:** USD, cash, defensive sectors")
    with col2:
        st.markdown("**Avoid:** Small caps, EM, crypto, value traps")

st.markdown("---")
st.caption("⚠️ Heuristic simulation for educational purposes. Not investment advice. "
           "Curve effects are approximate directional models.")
