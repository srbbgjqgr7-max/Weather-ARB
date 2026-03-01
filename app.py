import streamlit as st
import asyncio
import aiohttp
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from geopy.geocoders import Nominatim
from datetime import datetime, date, timedelta

# --- PAGE CONFIG ---
st.set_page_config(layout="wide", page_title="Weather Arb Quant Pro")
geolocator = Nominatim(user_agent="weather_arb_v2026_final")

st.title("🌡️ Weather Arb: 10-Model Consensus Terminal")
st.markdown("Global Ensemble Consensus + Risk-Adjusted Edge Analysis")

# --- SIDEBAR ---
with st.sidebar:
    st.header("📍 Location & Date")
    address = st.text_input("Target City", "London, UK")
    selected_date = st.date_input("Forecast Date", value=date.today() + timedelta(days=1))
    
    st.header("🎯 Market Parameters")
    target_temp = st.slider("Polymarket Hurdle (°C)", -10.0, 45.0, 30.0, step=0.5)
    bet_side = st.radio("Analyzing Side:", ["Yes (> Target)", "No (≤ Target)"])
    
    col_p1, col_p2 = st.columns(2)
    yes_p = col_p1.number_input("'Yes' Price", 0.01, 0.99, 0.50, step=0.01)
    no_p = col_p2.number_input("'No' Price", 0.01, 0.99, 0.50, step=0.01)
    
    st.header("⚖️ Model Weights")
    w_ecmwf = st.slider("ECMWF weight", 1.0, 5.0, 2.0)
    w_gfs = st.slider("GFS weight", 1.0, 5.0, 2.0)
    w_icon = st.slider("ICON weight", 1.0, 5.0, 1.5)
    
    st.header("💰 Wager")
    wager_amount = st.number_input("Bet Amount ($)", 1, 10000, 100)
    
    run_btn = st.button("Analyze Consensus", type="primary")

# --- ASYNC FETCHING ENGINE ---
async def fetch_model(session, name, model_id, weight, lat, lon, date_str):
    coords = [(lat, lon), (round(lat * 4) / 4, round(lon * 4) / 4)]
    
    for t_lat, t_lon in coords:
        if name == "ECMWF":
            base_url = "https://api.open-meteo.com/v1/ecmwf"
            models_param = "" 
        else:
            base_url = "https://api.open-meteo.com/v1/forecast"
            models_param = f"&models={model_id}"
        
        url = (
            f"{base_url}?"
            f"latitude={t_lat}&longitude={t_lon}&"
            f"daily=temperature_2m_max"
            f"{models_param}&"
            f"timezone=auto&"
            f"start_date={date_str}&end_date={date_str}"
        )
        
        try:
            async with session.get(url, timeout=15) as response:
                if response.status == 200:
                    data = await response.json()
                    if 'daily' in data and 'temperature_2m_max' in data['daily']:
                        val = data['daily']['temperature_2m_max'][0]
                        if val is not None:
                            return {"Model": name, "Temp": val, "Weight": weight}
        except:
            continue
    return None

async def run_ensemble(lat, lon, date_str):
    model_cfg = {
        "ECMWF":       ("", w_ecmwf),
        "GFS":         ("gfs_seamless", w_gfs),
        "ICON":        ("icon_global", w_icon),
        "GEM":         ("gem_global", 1.0),
        "ACCESS-G":    ("access_g", 1.0),
        "ICON-EU":     ("icon_eu", 1.2),
        "ICON-D2":     ("icon_d2", 1.5),
        "ARPEGE":      ("arpege_world", 1.0),
        "CMA-GFS":     ("cma_gfs_grapes", 1.0),
        "JMA":         ("jma_gsm", 1.0),
    }
    
    async with aiohttp.ClientSession() as session:
        tasks = [
            fetch_model(session, name, m_id, weight, lat, lon, date_str)
            for name, (m_id, weight) in model_cfg.items()
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        valid_results = [r for r in results if not isinstance(r, Exception) and r is not None]
        return valid_results

# --- MAIN LOGIC ---
if run_btn:
    with st.spinner("Geocoding location..."):
        loc = geolocator.geocode(address, timeout=10)
    
    if loc:
        lat, lon = loc.latitude, loc.longitude
        date_str = selected_date.strftime("%Y-%m-%d")
        
        # Run async fetching
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        results = loop.run_until_complete(run_ensemble(lat, lon, date_str))
        weather_results = results

        if weather_results:
            # --- CALCULATIONS ---
            # Model Agreement Score based on Core 3
            core_temps = [r["Temp"] for r in weather_results if r["Model"] in ["ECMWF", "GFS", "ICON"]]
            temp_spread = max(core_temps) - min(core_temps) if len(core_temps) > 1 else 0
            agreement = "Strong" if temp_spread < 1.5 else "Moderate" if temp_spread < 3 else "Weak (Risky)"
            
            total_w = sum(r["Weight"] for r in weather_results)
            w_avg = sum(r["Temp"] * r["Weight"] for r in weather_results) / total_w if total_w > 0 else 0
            p_yes = sum(r["Weight"] for r in weather_results if r["Temp"] > target_temp) / total_w if total_w > 0 else 0
            
            # Betting Logic
            m_prob = p_yes if "Yes" in bet_side else (1.0 - p_yes)
            m_price = yes_p if "Yes" in bet_side else no_p
            edge = m_prob - m_price
            
            # --- IMPROVED AVOID BUYING LOGIC (RISK ADJUSTED) ---
            days_out = (selected_date - date.today()).days
            # min_edge required scales with model disagreement and time
            min_edge_required = 0.04 + (temp_spread * 0.01) + (days_out * 0.005)
            risk_adj_buy_below = m_prob - min_edge_required
            
            total_payout = wager_amount / m_price if m_price > 0 else 0
            net_profit = total_payout - wager_amount

            col1, col2 = st.columns(2)
            
            with col1:
                st.subheader(f"🌐 Ensemble Coverage ({len(weather_results)} models)")
                st.dataframe(pd.DataFrame(weather_results).sort_values("Temp", ascending=False), hide_index=True)
                st.metric("Model Agreement Score", agreement, delta=f"{temp_spread:.1f}°C Spread", delta_color="inverse")
                
                fig_hist = px.histogram(
                    pd.DataFrame(weather_results), 
                    x="Temp", 
                    nbins=12, 
                    title="Max Temperature Distribution",
                    labels={"Temp": "Max Temp (°C)"}
                )
                fig_hist.add_vline(x=target_temp, line_dash="dash", line_color="red", annotation_text=f"Target: {target_temp}°C")
                st.plotly_chart(fig_hist, use_container_width=True)

            with col2:
                st.subheader("📊 Quant Results")
                fig_gauge = go.Figure(go.Indicator(
                    mode="gauge+number+delta",
                    value=w_avg,
                    title={'text': "Weighted Mean Max Temp (°C)"},
                    delta={'reference': target_temp},
                    gauge={
                        'axis': {'range': [None, 45]},
                        'threshold': {'line': {'color': "red", 'width': 4}, 'thickness': 0.75, 'value': target_temp},
                        'bar': {'color': "darkblue"}
                    }
                ))
                st.plotly_chart(fig_gauge, use_container_width=True)

                m1, m2, m3 = st.columns(3)
                m1.metric("Model Prob", f"{int(m_prob*100)}%")
                m2.metric("Market Price", f"${m_price:.2f}")
                m3.metric("Edge", f"{edge*100:+.1f}%")

                st.divider()
                
                # Dynamic Logic Gate
                if edge > min_edge_required:
                    status = "🔥 UNDERVALUED (BUY)"
                    color = "#00ff00"
                    advice = f"Edge exceeds risk-adjusted threshold ({min_edge_required*100:.1f}%)."
                elif edge > 0:
                    status = "⚖️ MARGINAL (HOLD)"
                    color = "orange"
                    advice = f"Positive edge, but doesn't meet safety margin for uncertainty."
                else:
                    status = "🚫 OVERVALUED (AVOID)"
                    color = "#ff4b4b"
                    advice = "Market price is higher than model probability."

                st.markdown(f"### Status: <span style='color:{color}'>{status}</span>", unsafe_allow_html=True)
                st.caption(f"**Action Logic:** {advice}")
                
                p_c1, p_c2 = st.columns(2)
                with p_c1:
                    st.write(f"**Potential Net Profit**: **${net_profit:.2f}**")
                    st.write(f"**Total Payout**: **${total_payout:.2f}**")
                with p_c2:
                    st.write(f"**Raw Break-even:** ${m_prob:.2f}")
                    st.write(f"**Risk-Adj Buy Below:** **${risk_adj_buy_below:.2f}**")

        else:
            st.error("No model data returned. Check coordinates or try a closer date.")
    else:
        st.error("Could not geocode the location. Try a different address.")
