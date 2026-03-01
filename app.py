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
st.markdown("Global Ensemble Consensus + Fixed Stake Analysis")

# --- SIDEBAR ---
with st.sidebar:
    st.header("📍 Location & Date")
    address = st.text_input("Target City", "London, UK")
    selected_date = st.date_input("Forecast Date", value=date.today() + timedelta(days=1))
    
    st.header("🎯 Market Parameters")
    target_temp = st.slider("Polymarket Hurdle (°C)", 10.0, 45.0, 30.0, step=0.5)
    bet_side = st.radio("Analyzing Side:", ["Yes (> Target)", "No (≤ Target)"])
    
    col_p1, col_p2 = st.columns(2)
    yes_p = col_p1.number_input("'Yes' Price", 0.01, 0.99, 0.50)
    no_p = col_p2.number_input("'No' Price", 0.01, 0.99, 0.50)
    
    st.header("⚖️ Model Weights")
    w_ecmwf = st.slider("ECMWF weight", 1.0, 5.0, 2.0)
    w_gfs = st.slider("GFS weight", 1.0, 5.0, 2.0)
    w_icon = st.slider("ICON weight", 1.0, 5.0, 1.5)
    
    st.header("💰 Wager")
    wager_amount = st.number_input("Bet Amount ($)", 1, 10000, 100)
    
    run_btn = st.button("Analyze Consensus", type="primary")

# --- ASYNC FETCHING ENGINE ---
async def fetch_model(session, name, model_id, weight, lat, lon, date_str):
    # Try exact coordinates first, then rounded (0.25° grid)
    coords = [(lat, lon), (round(lat * 4) / 4, round(lon * 4) / 4)]
    
    for t_lat, t_lon in coords:
        url = (
            f"https://api.open-meteo.com/v1/forecast?"
            f"latitude={t_lat}&longitude={t_lon}&"
            f"daily=temperature_2m_max&"
            f"models={model_id}&"
            f"timezone=auto&"
            f"start_date={date_str}&end_date={date_str}"
        )
        try:
            async with session.get(url, timeout=12) as response:
                if response.status == 200:
                    data = await response.json()
                    if 'daily' in data and 'temperature_2m_max' in data['daily']:
                        val = data['daily']['temperature_2m_max'][0]
                        if val is not None:
                            return {"Model": name, "Temp": val, "Weight": weight}
        except Exception:
            continue
    return None

async def run_ensemble(lat, lon, date_str, weights):
    model_cfg = {
        "ECMWF":       ("ecmwf_ifs04", weights[0]),
        "GFS":         ("gfs_seamless", weights[1]),
        "ICON":        ("icon_global", weights[2]),
        "GEM":         ("gem_global", 1.0),
        "ACCESS-G":    ("access_g", 1.0),
        "ICON-EU":     ("icon_eu", 1.2),           # regional – may not cover everywhere
        "ICON-D2":     ("icon_d2", 1.5),           # Germany + nearby only
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
        # Filter out exceptions and None results
        valid_results = [r for r in results if not isinstance(r, Exception) and r is not None]
        return valid_results

# --- MAIN LOGIC ---
if run_btn:
    with st.spinner("Geocoding location..."):
        loc = geolocator.geocode(address, timeout=10)
    
    if loc:
        lat, lon = loc.latitude, loc.longitude
        date_str = selected_date.strftime("%Y-%m-%d")
        
        st.info(f"Querying models for {address} ({lat:.4f}, {lon:.4f}) — {date_str}")
        
        # Run async fetching
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        results = loop.run_until_complete(run_ensemble(lat, lon, date_str, [w_ecmwf, w_gfs, w_icon]))
        weather_results = [r for r in results if r is not None]

        if weather_results:
            # ── Stats & Agreement ────────────────────────────────────────
            core_temps = [r["Temp"] for r in weather_results if r["Model"] in ["ECMWF", "GFS", "ICON"]]
            spread = max(core_temps) - min(core_temps) if len(core_temps) > 1 else 0
            agreement = "Strong" if spread < 1.5 else "Moderate" if spread < 3 else "Weak (Risky)"
            
            total_w = sum(r["Weight"] for r in weather_results)
            w_avg = sum(r["Temp"] * r["Weight"] for r in weather_results) / total_w
            p_yes = sum(r["Weight"] for r in weather_results if r["Temp"] > target_temp) / total_w
            
            # ── Betting Logic ────────────────────────────────────────────
            m_prob = p_yes if "Yes" in bet_side else (1.0 - p_yes)
            m_price = yes_p if "Yes" in bet_side else no_p
            edge = m_prob - m_price
            
            total_payout = wager_amount / m_price if m_price > 0 else 0
            net_profit = total_payout - wager_amount

            col1, col2 = st.columns(2)
            
            with col1:
                st.subheader(f"🌐 Ensemble Coverage ({len(weather_results)} models)")
                st.dataframe(pd.DataFrame(weather_results).sort_values("Temp", ascending=False))
                st.metric("Model Agreement Score", agreement, delta=f"{spread:.1f}°C Spread", delta_color="inverse")
                
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
                        'threshold': {
                            'line': {'color': "red", 'width': 4},
                            'thickness': 0.75,
                            'value': target_temp
                        },
                        'bar': {'color': "darkblue"}
                    }
                ))
                st.plotly_chart(fig_gauge, use_container_width=True)

                m1, m2, m3 = st.columns(3)
                m1.metric("Model-implied Prob", f"{int(m_prob*100)}%")
                m2.metric("Market Price", f"${m_price:.2f}")
                m3.metric("Edge", f"{edge*100:+.1f}%", delta_color="normal")

                st.divider()
                color = "green" if edge > 0.05 else "red" if edge < -0.05 else "gray"
                status = "UNDERVALUED ✓" if edge > 0.05 else "OVERVALUED ⚠" if edge < -0.05 else "FAIR VALUE"
                st.markdown(f"### Market Status: **<span style='color:{color}'>{status}</span>**", unsafe_allow_html=True)
                
                p_c1, p_c2 = st.columns(2)
                with p_c1:
                    st.write(f"**Potential Net Profit**: **${net_profit:.2f}**")
                    st.write(f"**Total Payout**: **${total_payout:.2f}**")
                with p_c2:
                    st.write(f"**Break-even Price**: **${m_prob:.2f}**")
                    if m_price > m_prob + 0.02:
                        st.warning(f"Avoid buying — price too high (> ${m_prob:.2f})")
                    elif m_price < m_prob - 0.02:
                        st.success(f"Potential edge — price below break-even")
        else:
            st.error("No model data returned for this location/date. Try:\n• A major city\n• Date within ~10–14 days\n• Check Open-Meteo model availability")
    else:
        st.error("Could not geocode the location. Please try a different address or spelling.")
