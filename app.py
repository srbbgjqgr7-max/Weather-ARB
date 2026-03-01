import streamlit as st
import requests
import pandas as pd
import statistics
import plotly.express as px
import plotly.graph_objects as go
import asyncio
import aiohttp
from geopy.geocoders import Nominatim
from datetime import datetime, date, timedelta

# --- PAGE CONFIG ---
st.set_page_config(layout="wide", page_title="Weather Arb Quant Pro")
geolocator = Nominatim(user_agent="weather_arb_v20")

st.title("🌡️ Weather Arb: 10-Model Consensus Terminal")

# --- SIDEBAR ---
with st.sidebar:
    st.header("📍 Location & Date")
    address = st.text_input("Target City", "London, UK")
    location = geolocator.geocode(address, timeout=10)
    lat, lon = (location.latitude, location.longitude) if location else (51.5, -0.1)
    
    selected_date = st.date_input("Forecast Date", value=date.today() + timedelta(days=1))
    target_temp = st.slider("Hurdle (°C)", 10.0, 45.0, 30.0, step=0.5)
    bet_side = st.radio("Analyzing Side:", ["Yes (> Target)", "No (≤ Target)"])

    st.header("⚙️ Risk Strategy")
    use_kelly = st.toggle("Enable Kelly Criterion", value=True)
    bankroll = st.number_input("Bankroll ($)", 100, 1000000, 1000) if use_kelly else 0
    wager = st.number_input("Fixed Wager ($)", 10, 10000, 100) if not use_kelly else 0

    c_p1, c_p2 = st.columns(2)
    yes_price = c_p1.number_input("'Yes' Price", 0.01, 0.99, 0.50)
    no_price = c_p2.number_input("'No' Price", 0.01, 0.99, 0.50)

    run_btn = st.button("Analyze Consensus", type="primary")

# --- ASYNC FETCHING ---
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
                    keys = data.get('daily', {}).keys()
                    temp_key = next((k for k in keys if "max" in k.lower()), None)
                    if temp_key:
                        val = data['daily'][temp_key][0]
                        if val is not None:
                            return {"Model": name, "Temp": val, "Weight": weight}
        except: continue
    return None

async def run_ensemble(lat, lon, date_str):
    # Expanded model list matching Windy's core providers
    model_config = {
        "ECMWF": ("ecmwf_ifs025", 2.0), "GFS": ("gfs_seamless", 2.0),
        "ICON": ("icon_seamless", 1.5), "GEM": ("gem_seamless", 1.0),
        "ACCESS-G": ("bom_access_g_global", 1.0), "HRRR": ("hrrr_conus", 1.5),
        "ICON-D2": ("icon_d2", 1.5), "ARPEGE": ("arpege_world", 1.0),
        "CMA": ("cma_grapes_global", 1.0), "JMA": ("jma_seamless", 1.0)
    }
    async with aiohttp.ClientSession() as session:
        tasks = [fetch_model(session, n, m[0], m[1], lat, lon, date_str) for n, m in model_config.items()]
        return await asyncio.gather(*tasks)

# --- ANALYSIS ---
if run_btn:
    date_str = selected_date.strftime("%Y-%m-%d")
    results = asyncio.run(run_ensemble(lat, lon, date_str))
    weather_results = [r for r in results if r is not None]

    if weather_results:
        # Agreement Score Calculation
        core_temps = [r["Temp"] for r in weather_results if r["Model"] in ["ECMWF", "GFS", "ICON"]]
        spread = max(core_temps) - min(core_temps) if len(core_temps) > 1 else 0
        agreement = "Strong" if spread < 1.5 else "Moderate" if spread < 3 else "Weak (Risky)"
        
        # Weighted Math
        total_w = sum(r["Weight"] for r in weather_results)
        w_avg = sum(r["Temp"] * r["Weight"] for r in weather_results) / total_w
        p_yes = sum(r["Weight"] for r in weather_results if r["Temp"] > target_temp) / total_w
        
        # Betting Math
        m_prob = p_yes if "Yes" in bet_side else (1.0 - p_yes)
        m_price = yes_price if "Yes" in bet_side else no_price
        edge = m_prob - m_price

        col1, col2 = st.columns(2)
        with col1:
            st.subheader(f"🌐 Ensemble ({len(weather_results)} Models)")
            st.table(pd.DataFrame(weather_results))
            st.metric("Model Consensus Score", agreement, delta=f"{spread:.1f}°C Spread", delta_color="inverse")

        with col2:
            st.subheader("📊 Profit & Stake")
            fig_gauge = go.Figure(go.Indicator(
                mode="gauge+number", value=w_avg, title={'text': "Weighted Mean (°C)"},
                gauge={'axis': {'range': [None, 45]}, 'threshold': {'line': {'color': "red", 'width': 4}, 'value': target_temp}}
            ))
            st.plotly_chart(fig_gauge, use_container_width=True)

            # Execution Logic
            if edge > 0:
                stake = (bankroll * ((m_prob - m_price) / (1 - m_price)) * 0.25) if use_kelly else wager
                st.success(f"🔥 Buy {bet_side}: Stake **${max(0, stake):.2f}**")
                st.write(f"Edge: **{edge*100:.1f}%** | Break-even: **${m_prob:.2f}**")
            else:
                st.error("❄️ No Edge Detected. Market price exceeds model probability.")
    else:
        st.error("Data fetch failed. Ensure date is within 14 days and location is valid.")
