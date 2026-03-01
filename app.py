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

st.title("🌡️ Weather Arb: Pro Consensus Terminal")
st.markdown("Advanced Model Distribution & Risk Guard Analysis")

# --- SIDEBAR ---
with st.sidebar:
    st.header("📍 Location & Date")
    address = st.text_input("Target City", "London, UK")
    selected_date = st.date_input("Forecast Date", value=date.today() + timedelta(days=1))
    
    unit = st.toggle("Display in Fahrenheit", value=False)
    u_lab = "°F" if unit else "°C"
    
    if unit:
        target_temp = st.slider(f"Polymarket Hurdle ({u_lab})", 14.0, 115.0, 77.0, step=1.0)
        actual_target_c = (target_temp - 32) * 5/9
    else:
        target_temp = st.slider(f"Polymarket Hurdle ({u_lab})", -10.0, 45.0, 25.0, step=0.5)
        actual_target_c = target_temp

    st.header("🎯 Market Parameters")
    bet_side = st.radio(
        "Your Polymarket Position:", 
        ["Yes (Expect temp ≤ Hurdle)", "No (Expect temp > Hurdle)"],
        help="Select 'No' if you believe the actual temperature will exceed the limit."
    )
    
    col_p1, col_p2 = st.columns(2)
    yes_p = col_p1.number_input("'Yes' Price", 0.01, 0.99, 0.15, step=0.01)
    no_p = col_p2.number_input("'No' Price", 0.01, 0.99, 0.85, step=0.01)
    
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
            df = pd.DataFrame(weather_results)
            
            # --- CALCULATIONS ---
            total_w = df["Weight"].sum()
            p_above = sum(df[df["Temp"] > actual_target_c]["Weight"]) / total_w
            p_below = 1.0 - p_above
            
            if "No" in bet_side:
                m_prob = p_above
                m_price = no_p
            else:
                m_prob = p_below
                m_price = yes_p
            
            edge = m_prob - m_price
            edge_cents = int(edge * 100)
            
            # Outlier Detection
            min_forecast_c = df["Temp"].min()
            coldest_model = df.loc[df["Temp"].idxmin()]["Model"]
            safety_margin = min_forecast_c - actual_target_c

            # UI Display Unit Conversion
            if unit:
                df_disp = df.copy()
                df_disp["Temp"] = df_disp["Temp"].apply(lambda x: (x * 9/5) + 32)
                disp_margin = safety_margin * 1.8
            else:
                df_disp = df
                disp_margin = safety_margin

            col1, col2 = st.columns(2)
            
            with col1:
                st.subheader("🌐 Model Distribution")
                st.dataframe(df_disp.sort_values("Temp", ascending=False), hide_index=True)
                
                count_above = len(df[df["Temp"] > actual_target_c])
                st.write(f"📊 **{count_above} out of {len(df)} models** estimate the temperature will be **ABOVE** {target_temp}{u_lab}.")
                
                # --- RISK GUARD EDIT ---
                st.divider()
                if safety_margin > 0 and "No" in bet_side:
                    st.success(f"🛡️ **Risk Guard: Maximum Confidence**\n\nEvery model is ABOVE hurdle. Coldest: {coldest_model} at {disp_margin:+.1f}{u_lab} margin.")
                elif "No" in bet_side:
                    st.error(f"⚠️ **Risk Guard: Vulnerable**\n\n{coldest_model} predicts a temp {abs(disp_margin):.1f}{u_lab} BELOW your hurdle.")

            with col2:
                st.subheader("📊 Profit/Loss Analysis")
                m1, m2, m3 = st.columns(3)
                m1.metric("Model Win Prob", f"{int(m_prob*100)}%")
                m2.metric("Market Price", f"${m_price:.2f}")
                m3.metric("Edge (Cents)", f"{edge_cents}¢")

                st.divider()
                color = "#00ff00" if edge > 0.05 else "orange" if edge > 0 else "#ff4b4b"
                status = "🔥 POSITIVE EDGE" if edge > 0.05 else "⚖️ NEUTRAL/THIN" if edge > 0 else "🚫 NO EDGE"
                st.markdown(f"### Strategy Status: <span style='color:{color}'>{status}</span>", unsafe_allow_html=True)
                
                if edge_cents > 5:
                    st.toast(f"Value Alert: {edge_cents}¢ Edge Detected!")

                st.write(f"**Potential Net Profit:** ${((wager_amount/m_price)-wager_amount):.2f}")
                st.info(f"Market expects {int(m_price*100)}% chance. Models expect {int(m_prob*100)}% chance.")
        else:
            st.error("No model data found.")
