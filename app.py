import streamlit as st
import asyncio
import aiohttp
import pandas as pd
import plotly.express as px
from geopy.geocoders import Nominatim
from datetime import datetime, date, timedelta

# --- PAGE CONFIG ---
st.set_page_config(layout="wide", page_title="Weather Arb Quant Pro")
geolocator = Nominatim(user_agent="weather_arb_v2026_final")

st.title("🌡️ Weather Arb: Pro Consensus Terminal")

# --- SIDEBAR ---
with st.sidebar:
    st.header("📍 Location & Date")
    address = st.text_input("Target City", "London, UK")
    selected_date = st.date_input("Forecast Date", value=date.today() + timedelta(days=1))
    
    unit = st.toggle("Display in Fahrenheit", value=False)
    u_lab = "°F" if unit else "°C"
    
    if unit:
        target_temp = st.slider(f"Market Hurdle ({u_lab})", 14.0, 115.0, 77.0, step=1.0)
        actual_target_c = (target_temp - 32) * 5/9
    else:
        target_temp = st.slider(f"Market Hurdle ({u_lab})", -10.0, 45.0, 25.0, step=0.5)
        actual_target_c = target_temp

    st.header("🎯 Market Parameters")
    bet_side = st.radio("My Polymarket Side:", ["Yes (Expect BELOW)", "No (Expect ABOVE)"])
    no_p = st.number_input("'No' Price", 0.01, 0.99, 0.85, step=0.01)
    yes_p = st.number_input("'Yes' Price", 0.01, 0.99, 0.15, step=0.01)
    
    wager_amount = st.number_input("Wager ($)", 1, 10000, 100)
    run_btn = st.button("Run Pro Analysis", type="primary")

# --- ASYNC FETCHING ---
async def fetch_model(session, name, m_id, weight, lat, lon, date_str):
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&daily=temperature_2m_max&models={m_id}&timezone=auto&start_date={date_str}&end_date={date_str}"
    try:
        async with session.get(url, timeout=10) as resp:
            data = await resp.json()
            val = data['daily']['temperature_2m_max'][0]
            return {"Model": name, "Temp": val, "Weight": weight}
    except: return None

async def run_ensemble(lat, lon, date_str):
    # Location-aware weights (Simplified logic)
    is_europe = 35 < lat < 70 and -10 < lon < 30
    model_cfg = {
        "ECMWF": ("ecmwf_ifs025", 2.5), 
        "GFS": ("gfs_seamless", 2.0),
        "ICON": ("icon_seamless", 2.0 if is_europe else 1.5),
        "ARPEGE": ("arpege_world", 1.5 if is_europe else 1.0)
    }
    async with aiohttp.ClientSession() as session:
        tasks = [fetch_model(session, n, m[0], m[1], lat, lon, date_str) for n, m in model_cfg.items()]
        return [r for r in await asyncio.gather(*tasks) if r]

# --- MAIN ANALYSIS ---
if run_btn:
    loc = geolocator.geocode(address)
    if loc:
        weather_results = asyncio.run(run_ensemble(loc.latitude, loc.longitude, selected_date.strftime("%Y-%m-%d")))
        
        if weather_results:
            df = pd.DataFrame(weather_results)
            # Calculations
            total_w = df["Weight"].sum()
            p_above = sum(df[df["Temp"] > actual_target_c]["Weight"]) / total_w
            m_prob = p_above if "No" in bet_side else (1.0 - p_above)
            m_price = no_p if "No" in bet_side else yes_p
            edge = m_prob - m_price
            
            # --- NEW IMPROVEMENTS ---
            min_temp = df["Temp"].min()
            max_temp = df["Temp"].max()
            cold_outlier = df.loc[df["Temp"].idxmin()]["Model"]
            
            col1, col2 = st.columns(2)
            with col1:
                st.subheader("📡 Multi-Model Feed")
                st.dataframe(df, hide_index=True)
                st.warning(f"❄️ **Coldest Outlier:** {cold_outlier} ({min_temp}°C)")
            
            with col2:
                st.subheader("🛡️ Risk Guard")
                m1, m2 = st.columns(2)
                m1.metric("Win Probability", f"{int(m_prob*100)}%")
                m2.metric("Edge", f"{edge*100:+.1f}%")
                
                st.divider()
                if min_temp > actual_target_c and "No" in bet_side:
                    st.success("✅ **Safety Check:** Every single model predicts a temp ABOVE your hurdle.")
                elif "No" in bet_side:
                    st.error(f"⚠️ **Danger:** {cold_outlier} predicts a temp BELOW your hurdle.")

        else: st.error("No data.")
