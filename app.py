import streamlit as st
import requests
import pandas as pd
import statistics
import plotly.express as px
from geopy.geocoders import Nominatim
from datetime import datetime, date, timedelta
import time

# --- PAGE CONFIG ---
st.set_page_config(layout="wide", page_title="Weather Arb Pro 2026")
geolocator = Nominatim(user_agent="weather_arb_v16_kelly")

st.title("🌡️ Weather vs. Polymarket Arbitrage")
st.markdown("Global Ensemble Models + Date Selection + Kelly Criterion Management")

# --- SIDEBAR ---
with st.sidebar:
    st.header("📍 Location & Date")
    address_input = st.text_input("Enter City", "London, UK")
    
    max_forecast_date = date.today() + timedelta(days=14)
    selected_date = st.date_input(
        "Forecast Date", 
        value=date.today() + timedelta(days=1),
        min_value=date.today(),
        max_value=max_forecast_date
    )

    location = geolocator.geocode(address_input, timeout=10)
    lat, lon = (round(location.latitude, 2), round(location.longitude, 2)) if location else (51.5, -0.1)

    st.header("🎯 Market Parameters")
    target_temp = st.slider("Polymarket Hurdle (°C)", 10, 45, 30)
    bet_side = st.radio("Analyzing Side:", ["Yes (Strictly Above >)", "No (Lower or Equal ≤)"])
    
    c_p1, c_p2 = st.columns(2)
    yes_price = c_p1.number_input("'Yes' Price", 0.01, 0.99, 0.50)
    no_price = c_p2.number_input("'No' Price", 0.01, 0.99, 0.50)

    st.header("💰 Kelly Bankroll Management")
    total_bankroll = st.number_input("Total Bankroll ($)", 100, 1000000, 1000)
    kelly_fraction = st.select_slider(
        "Kelly Multiplier (Aggression)", 
        options=[0.1, 0.25, 0.5, 1.0], 
        value=0.25,
        help="0.25 (Quarter Kelly) is recommended for safety."
    )

    run_btn = st.button("Calculate Optimal Bet", type="primary")

# --- MAIN APP LOGIC ---
col1, col2 = st.columns(2)

if run_btn:
    date_str = selected_date.strftime("%Y-%m-%d")
    model_config = {
        "ECMWF": {"id": "ecmwf_ifs025", "weight": 2.0},
        "GFS": {"id": "gfs_seamless", "weight": 2.0},
        "ICON": {"id": "icon_seamless", "weight": 1.0},
        "GEM": {"id": "gem_seamless", "weight": 1.0},
        "JMA": {"id": "jma_seamless", "weight": 1.0},
        "BOM": {"id": "bom_access_g_global", "weight": 1.0},
        "ARPEGE": {"id": "arpege_world", "weight": 1.0},
        "CMA": {"id": "cma_grapes_global", "weight": 1.0}
    }
    
    weather_results, weighted_votes_above, total_weight = [], [], 0
    progress_bar = st.progress(0, text=f"Analyzing {date_str}...")

    for i, (name, config) in enumerate(model_config.items()):
        api_id, weight = config["id"], config["weight"]
        coords_to_try = [(lat, lon), (round(lat, 1), round(lon, 1))]
        for t_lat, t_lon in coords_to_try:
            url = f"https://ensemble-api.open-meteo.com/v1/ensemble?latitude={t_lat}&longitude={t_lon}&daily=temperature_2m_max&models={api_id}&timezone=auto&start_date={date_str}&end_date={date_str}"
            try:
                resp = requests.get(url, timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    temp_key = [k for k in data.get('daily', {}).keys() if 'temperature_2m_max' in k]
                    if temp_key:
                        val = data['daily'][temp_key[0]][0]
                        if val is not None:
                            weather_results.append({"Model": name, "Max Temp": val, "Weight": weight})
                            weighted_votes_above.append((1 if val > target_temp else 0) * weight)
                            total_weight += weight
                            break
            except: continue
        progress_bar.progress((i + 1) / len(model_config))
    progress_bar.empty()

    if weather_results:
        avg_temp = statistics.mean([r["Max Temp"] for r in weather_results])
        prob_above = round(sum(weighted_votes_above) / total_weight, 2)
        prob_below = 1.0 - prob_above
        
        curr_mkt = yes_price if "Yes" in bet_side else no_price
        mod_prob = prob_above if "Yes" in bet_side else prob_below
        edge = mod_prob - curr_mkt

        # --- KELLY CRITERION FORMULA ---
        # f* = (p * (b - 1) - q) / (b - 1)
        # In Prediction Markets: b = 1 / price
        # Simplified for binary markets: f* = (Probability - Price) / (1 - Price)
        if edge > 0:
            raw_kelly = (mod_prob - curr_mkt) / (1 - curr_mkt)
            suggested_stake_pct = raw_kelly * kelly_fraction
            suggested_bet = total_bankroll * suggested_stake_pct
        else:
            suggested_stake_pct = 0
            suggested_bet = 0

        with col1:
            st.subheader(f"🌐 {date_str} Ensemble")
            st.table(pd.DataFrame(weather_results))
            fig = px.histogram(x=[r["Max Temp"] for r in weather_results], nbins=8, title="Model Spread")
            fig.add_vline(x=target_temp, line_dash="dash", line_color="red")
            st.plotly_chart(fig, width="stretch")

        with col2:
            st.subheader(f"⚖️ Kelly Analysis: {bet_side}")
            m1, m2 = st.columns(2)
            m1.metric("Market Price", f"${curr_mkt:.2f}")
            m2.metric("Weighted Prob", f"{int(mod_prob*100)}%")
            
            st.divider()
            color = "green" if edge > 0.05 else "red" if edge < -0.05 else "gray"
            st.markdown(f"### <span style='color:{color}'>{'UNDERVALUED' if edge > 0.05 else 'OVERVALUED' if edge < -0.05 else 'EFFICIENT'}</span>", unsafe_allow_html=True)
            st.metric("Calculated Edge", f"{edge*100:.1f}%")

            st.subheader("🎯 Suggested Wager")
            if suggested_bet > 0:
                st.write(f"Based on a **{kelly_fraction}x Kelly** strategy:")
                st.metric("Optimal Bet Size", f"${suggested_bet:.2f}", f"{suggested_stake_pct*100:.1f}% of Bank")
                st.success(f"Strategy: Risk ${suggested_bet:.2f} to grow bankroll at the optimal long-term rate.")
            else:
                st.warning("Strategy: No Edge detected. Do not place this bet.")

else:
    st.info("👈 Enter Bankroll and click 'Calculate Optimal Bet'.")
