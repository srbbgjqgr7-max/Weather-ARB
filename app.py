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
async def fetch_model(session, name, m_id, weight, lat, lon, date_str):
    coords = [(lat, lon), (round(lat * 4) / 4, round(lon * 4) / 4)]
    for t_lat, t_lon in coords:
        url = (f"https://ensemble-api.open-meteo.com/v1/ensemble?"
               f"latitude={t_lat}&longitude={t_lon}&daily=temperature_2m_max&"
               f"models={m_id}&timezone=auto&start_date={date_str}&end_date={date_str}")
        try:
            async with session.get(url, timeout=12) as response:
                if response.status == 200:
                    data = await response.json()
                    temp_key = next((k for k in data.get('daily', {}).keys() if "max" in k.lower()), None)
                    if temp_key:
                        val = data['daily'][temp_key][0]
                        if val is not None:
                            return {"Model": name, "Temp": val, "Weight": weight}
        except: continue
    return None

async def run_ensemble(lat, lon, date_str, weights):
    model_cfg = {
        "ECMWF": ("ecmwf_ifs025", weights[0]), "GFS": ("gfs_seamless", weights[1]),
        "ICON": ("icon_seamless", weights[2]), "GEM": ("gem_seamless", 1.0),
        "ACCESS-G": ("bom_access_g_global", 1.0), "HRRR": ("hrrr_conus", 1.5),
        "ICON-D2": ("icon_d2", 1.5), "ARPEGE": ("arpege_world", 1.0),
        "CMA": ("cma_grapes_global", 1.0), "JMA": ("jma_seamless", 1.0)
    }
    async with aiohttp.ClientSession() as session:
        tasks = [fetch_model(session, n, m[0], m[1], lat, lon, date_str) for n, m in model_cfg.items()]
        return await asyncio.gather(*tasks)

# --- MAIN LOGIC ---
if run_btn:
    loc = geolocator.geocode(address, timeout=10)
    if loc:
        lat, lon = loc.latitude, loc.longitude
        date_str = selected_date.strftime("%Y-%m-%d")
        
        # Async execution wrapper
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        results = loop.run_until_complete(run_ensemble(lat, lon, date_str, [w_ecmwf, w_gfs, w_icon]))
        weather_results = [r for r in results if r is not None]

        if weather_results:
            # Stats & Agreement
            core_temps = [r["Temp"] for r in weather_results if r["Model"] in ["ECMWF", "GFS", "ICON"]]
            spread = max(core_temps) - min(core_temps) if len(core_temps) > 1 else 0
            agreement = "Strong" if spread < 1.5 else "Moderate" if spread < 3 else "Weak (Risky)"
            
            total_w = sum(r["Weight"] for r in weather_results)
            w_avg = sum(r["Temp"] * r["Weight"] for r in weather_results) / total_w
            p_yes = sum(r["Weight"] for r in weather_results if r["Temp"] > target_temp) / total_w
            
            # Betting Logic
            m_prob = p_yes if "Yes" in bet_side else (1.0 - p_yes)
            m_price = yes_p if "Yes" in bet_side else no_p
            edge = m_prob - m_price
            
            total_payout = wager_amount / m_price
            net_profit = total_payout - wager_amount

            col1, col2 = st.columns(2)
            with col1:
                st.subheader(f"🌐 Ensemble Coverage ({len(weather_results)}/10)")
                st.table(pd.DataFrame(weather_results))
                st.metric("Model Agreement Score", agreement, delta=f"{spread:.1f}°C Spread", delta_color="inverse")
                
                fig_hist = px.histogram(pd.DataFrame(weather_results), x="Temp", nbins=10, title="Spread Distribution")
                fig_hist.add_vline(x=target_temp, line_dash="dash", line_color="red")
                st.plotly_chart(fig_hist, use_container_width=True)

            with col2:
                st.subheader("📊 Quant Results")
                fig_gauge = go.Figure(go.Indicator(
                    mode="gauge+number", value=w_avg, title={'text': "Weighted Mean (°C)"},
                    gauge={'axis': {'range': [None, 45]}, 'threshold': {'line': {'color': "red", 'width': 4}, 'value': target_temp}}
                ))
                st.plotly_chart(fig_gauge, use_container_width=True)

                m1, m2, m3 = st.columns(3)
                m1.metric("Model Prob", f"{int(m_prob*100)}%")
                m2.metric("Market Price", f"${m_price:.2f}")
                m3.metric("Edge", f"{edge*100:.1f}%")

                st.divider()
                color = "green" if edge > 0.05 else "red" if edge < -0.05 else "gray"
                status = "UNDERVALUED" if edge > 0.05 else "OVERVALUED" if edge < -0.05 else "EFFICIENT"
                st.markdown(f"### Status: <span style='color:{color}'>{status}</span>", unsafe_allow_html=True)
                
                p_c1, p_c2 = st.columns(2)
                with p_c1:
                    st.write(f"Potential **Net Profit**: **${net_profit:.2f}**")
                    st.write(f"Total Payout: **${total_payout:.2f}**")
                with p_c2:
                    st.write(f"🎯 **Break-even Price**: **${m_prob:.2f}**")
                    st.info(f"Avoid buying if price > ${m_prob:.2f}")
        else:
            st.error("No model data found. Try rounding coordinates or a closer date.")
    else:
        st.error("Location not found.")
