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

# --- SIDEBAR ---
with st.sidebar:
    st.header("📍 Location & Date")
    address = st.text_input("Target City", "London, UK")
    selected_date = st.date_input("Forecast Date", value=date.today() + timedelta(days=1))
    
    # Unit Toggle
    unit = st.toggle("Display in Fahrenheit", value=False)
    u_lab = "°F" if unit else "°C"
    
    if unit:
        target_temp = st.slider(f"Market Hurdle ({u_lab})", 14.0, 115.0, 86.0, step=1.0)
        actual_target_c = (target_temp - 32) * 5/9
    else:
        target_temp = st.slider(f"Market Hurdle ({u_lab})", -10.0, 45.0, 30.0, step=0.5)
        actual_target_c = target_temp

    st.header("🎯 Market Parameters")
    # Clarified Labels for Betting
    bet_side = st.radio("My Bet Side:", ["Yes (Expect ABOVE Hurdle)", "No (Expect BELOW Hurdle)"])
    
    col_p1, col_p2 = st.columns(2)
    yes_p = col_p1.number_input("'Yes' Mkt Price", 0.01, 0.99, 0.50, step=0.01)
    no_p = col_p2.number_input("'No' Mkt Price", 0.01, 0.99, 0.50, step=0.01)
    
    st.header("⚖️ Model Weights")
    w_ecmwf = st.slider("ECMWF weight", 1.0, 5.0, 2.0)
    w_gfs = st.slider("GFS weight", 1.0, 5.0, 2.0)
    w_icon = st.slider("ICON weight", 1.0, 5.0, 1.5)
    
    wager_amount = st.number_input("Bet Amount ($)", 1, 10000, 100)
    run_btn = st.button("Analyze Consensus", type="primary")

# --- ASYNC FETCHING ENGINE ---
async def fetch_model(session, name, model_id, weight, lat, lon, date_str):
    coords = [(lat, lon), (round(lat * 4) / 4, round(lon * 4) / 4)]
    for t_lat, t_lon in coords:
        base_url = "https://api.open-meteo.com/v1/ecmwf" if name == "ECMWF" else "https://api.open-meteo.com/v1/forecast"
        models_param = "" if name == "ECMWF" else f"&models={model_id}"
        url = f"{base_url}?latitude={t_lat}&longitude={t_lon}&daily=temperature_2m_max{models_param}&timezone=auto&start_date={date_str}&end_date={date_str}"
        try:
            async with session.get(url, timeout=15) as response:
                if response.status == 200:
                    data = await response.json()
                    val = data['daily']['temperature_2m_max'][0]
                    if val is not None: return {"Model": name, "Temp": val, "Weight": weight}
        except: continue
    return None

async def run_ensemble(lat, lon, date_str):
    model_cfg = {
        "ECMWF": ("", w_ecmwf), "GFS": ("gfs_seamless", w_gfs), "ICON": ("icon_global", w_icon),
        "GEM": ("gem_global", 1.0), "ACCESS-G": ("access_g", 1.0), "ICON-EU": ("icon_eu", 1.2),
        "ICON-D2": ("icon_d2", 1.5), "ARPEGE": ("arpege_world", 1.0), "CMA-GFS": ("cma_gfs_grapes", 1.0), "JMA": ("jma_gsm", 1.0),
    }
    async with aiohttp.ClientSession() as session:
        tasks = [fetch_model(session, n, m[0], m[1], lat, lon, date_str) for n, m in model_cfg.items()]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return [r for r in results if not isinstance(r, Exception) and r is not None]

# --- MAIN LOGIC ---
if run_btn:
    loc = geolocator.geocode(address, timeout=10)
    if loc:
        lat, lon, date_str = loc.latitude, loc.longitude, selected_date.strftime("%Y-%m-%d")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        weather_results = loop.run_until_complete(run_ensemble(lat, lon, date_str))

        if weather_results:
            # Internal Math (Celsius)
            core_temps = [r["Temp"] for r in weather_results if r["Model"] in ["ECMWF", "GFS", "ICON"]]
            temp_spread = max(core_temps) - min(core_temps) if len(core_temps) > 1 else 0
            
            total_w = sum(r["Weight"] for r in weather_results)
            w_avg_c = sum(r["Temp"] * r["Weight"] for r in weather_results) / total_w
            p_yes = sum(r["Weight"] for r in weather_results if r["Temp"] > actual_target_c) / total_w
            
            # Prediction Logic
            m_prob = p_yes if "Yes" in bet_side else (1.0 - p_yes)
            m_price = yes_p if "Yes" in bet_side else no_p
            edge = m_prob - m_price
            
            # Risk Adjustment
            days_out = (selected_date - date.today()).days
            min_edge = 0.04 + (temp_spread * 0.01) + (days_out * 0.005)
            risk_adj_buy_below = m_prob - min_edge

            # Display Conversions
            disp_avg = (w_avg_c * 9/5 + 32) if unit else w_avg_c
            df = pd.DataFrame(weather_results)
            if unit: df["Temp"] = df["Temp"].apply(lambda x: (x * 9/5) + 32)

            col1, col2 = st.columns(2)
            with col1:
                st.subheader(f"🌐 Ensemble Coverage ({u_lab})")
                st.dataframe(df.sort_values("Temp", ascending=False), hide_index=True)
                st.metric("Model Agreement", "Strong" if temp_spread < 1.5 else "Weak", delta=f"{temp_spread:.1f}°C Spread", delta_color="inverse")
                
            with col2:
                st.subheader("📊 Quant Results")
                m1, m2, m3 = st.columns(3)
                m1.metric("Model Prob", f"{int(m_prob*100)}%")
                m2.metric("Market Price", f"${m_price:.2f}")
                m3.metric("Edge", f"{edge*100:+.1f}%")

                st.divider()
                color = "#00ff00" if edge > min_edge else "orange" if edge > 0 else "#ff4b4b"
                status = "🔥 BUY SIGNAL" if edge > min_edge else "⚖️ HOLD/AVOID" if edge > 0 else "🚫 OVERVALUED"
                
                st.markdown(f"### Status: <span style='color:{color}'>{status}</span>", unsafe_allow_html=True)
                st.write(f"**Target Buy Price (Risk-Adj):** ${risk_adj_buy_below:.2f}")
                st.write(f"**Potential Net Profit:** ${((wager_amount/m_price)-wager_amount):.2f}")
        else:
            st.error("No data returned.")
