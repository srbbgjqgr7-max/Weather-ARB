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
geolocator = Nominatim(user_agent="weather_arb_ultimate_v2026")

st.title("🌡️ Weather Arb: 10-Model Consensus Terminal")

# --- SIDEBAR & WEIGHT EDITOR ---
with st.sidebar:
    st.header("📍 Location & Date")
    address = st.text_input("Target City", "London, UK")
    selected_date = st.date_input("Forecast Date", value=date.today() + timedelta(days=1))
    
    st.header("🎯 Market Parameters")
    target_temp = st.slider("Hurdle (°C)", 10.0, 45.0, 30.0, step=0.5)
    bet_side = st.radio("Analyzing Side:", ["Yes (> Target)", "No (≤ Target)"])
    yes_p = st.number_input("'Yes' Price", 0.01, 0.99, 0.50)
    no_p = st.number_input("'No' Price", 0.01, 0.99, 0.50)
    
    st.header("⚖️ Model Weight Editor")
    w_ecmwf = st.slider("ECMWF Weight", 1.0, 5.0, 2.0)
    w_gfs = st.slider("GFS Weight", 1.0, 5.0, 2.0)
    w_icon = st.slider("ICON Weight", 1.0, 5.0, 1.5)
    
    st.header("💰 Risk")
    bankroll = st.number_input("Bankroll ($)", 10, 100000, 1000)
    run_btn = st.button("Analyze Consensus", type="primary")

# --- ASYNC ENGINE ---
async def fetch_model(session, name, m_id, weight, lat, lon, date_str):
    # Coordinate snapping for better model hits
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
        
        # Using loop to handle async in Streamlit
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        results = loop.run_until_complete(run_ensemble(lat, lon, date_str, [w_ecmwf, w_gfs, w_icon]))
        weather_results = [r for r in results if r is not None]

        if weather_results:
            # Stats
            total_w = sum(r["Weight"] for r in weather_results)
            w_avg = sum(r["Temp"] * r["Weight"] for r in weather_results) / total_w
            p_yes = sum(r["Weight"] for r in weather_results if r["Temp"] > target_temp) / total_w
            
            m_prob = p_yes if "Yes" in bet_side else (1.0 - p_yes)
            m_price = yes_p if "Yes" in bet_side else no_p
            edge = m_prob - m_price

            col1, col2 = st.columns(2)
            with col1:
                st.subheader(f"🌐 Ensemble Coverage ({len(weather_results)}/10)")
                st.table(pd.DataFrame(weather_results))
                fig_hist = px.histogram(pd.DataFrame(weather_results), x="Temp", nbins=10, title="Spread Distribution")
                fig_hist.add_vline(x=target_temp, line_dash="dash", line_color="red")
                st.plotly_chart(fig_hist, use_container_width=True)

            with col2:
                st.subheader("📊 Quant Analysis")
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
                if edge > 0:
                    kelly = (m_prob - m_price) / (1 - m_price)
                    stake = bankroll * kelly * 0.25 # Quarter Kelly for safety
                    st.success(f"🔥 Positive Edge! Stake: **${max(0, stake):.2f}**")
                    st.write(f"Break-even Price: **${m_prob:.2f}**")
                    st.write(f"Potential Net Profit: **${((stake/m_price)-stake):.2f}**")
                else:
                    st.error("❄️ Overvalued: No edge found.")
    else:
        st.error("Location not found.")
