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
geolocator = Nominatim(user_agent="weather_arb_v14_dates")

st.title("🌡️ Weather vs. Polymarket Arbitrage")
st.markdown("Global Ensemble Models + Date Selection + Weighted Probability")

# --- SIDEBAR ---
with st.sidebar:
    st.header("📍 Location & Date")
    address_input = st.text_input("Enter City", "London, UK")
    
    # Date Selection Widget
    # Note: Ensemble forecasts usually go out 14-16 days.
    max_forecast_date = date.today() + timedelta(days=14)
    selected_date = st.date_input(
        "Forecast Date", 
        value=date.today() + timedelta(days=1),
        min_value=date.today(),
        max_value=max_forecast_date
    )

    location = geolocator.geocode(address_input, timeout=10)
    if location:
        lat, lon = round(location.latitude, 2), round(location.longitude, 2)
        st.success(f"Coordinates: {lat}, {lon}")
    else:
        lat, lon = 51.5, -0.1

    st.header("🎯 Market Parameters")
    target_temp = st.slider("Polymarket Hurdle (°C)", 10, 45, 30)
    bet_side = st.radio("Analyzing Side:", ["Yes (Above)", "No (Below)"])
    
    c_p1, c_p2 = st.columns(2)
    yes_price = c_p1.number_input("'Yes' Price", 0.01, 0.99, 0.50)
    no_price = c_p2.number_input("'No' Price", 0.01, 0.99, 0.50)

    st.header("💰 Wager Settings")
    wager_amount = st.number_input("Wager Amount ($)", 10, 10000, 100)

    run_btn = st.button("Calculate Edge", type="primary")

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
    
    weather_results = []
    weighted_votes = []
    total_possible_weight = 0
    
    progress_bar = st.progress(0, text=f"Fetching Models for {date_str}...")

    for i, (name, config) in enumerate(model_config.items()):
        api_id = config["id"]
        weight = config["weight"]
        
        # Grid-snapping coords
        coords_to_try = [(lat, lon), (round(lat, 1), round(lon, 1))]
        
        for try_lat, try_lon in coords_to_try:
            # We add start_date and end_date to the API call
            url = (f"https://ensemble-api.open-meteo.com/v1/ensemble?"
                   f"latitude={try_lat}&longitude={try_lon}&daily=temperature_2m_max&"
                   f"models={api_id}&timezone=auto&start_date={date_str}&end_date={date_str}")
            try:
                resp = requests.get(url, timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    temp_key = [k for k in data.get('daily', {}).keys() if 'temperature_2m_max' in k]
                    if temp_key:
                        val = data['daily'][temp_key[0]][0]
                        if val is not None:
                            weather_results.append({"Model": name, "Max Temp": val, "Weight": weight})
                            is_above = 1 if val >= target_temp else 0
                            weighted_votes.append(is_above * weight)
                            total_possible_weight += weight
                            break
            except:
                continue
        progress_bar.progress((i + 1) / len(model_config))
    
    progress_bar.empty()

    if not weather_results:
        st.error(f"No model data found for {date_str}. Ensemble forecasts are typically available for the next 14 days.")
    else:
        # --- CALCULATIONS ---
        avg_temp = statistics.mean([r["Max Temp"] for r in weather_results])
        prob_above = round(sum(weighted_votes) / total_possible_weight, 2)
        prob_below = 1 - prob_above
        
        curr_mkt = yes_price if "Yes" in bet_side else no_price
        mod_prob = prob_above if "Yes" in bet_side else prob_below
        edge = mod_prob - curr_mkt

        # Risk/Reward
        total_payout = wager_amount / curr_mkt
        net_profit = total_payout - wager_amount

        with col1:
            st.subheader(f"🌐 {date_str} Results ({len(weather_results)}/8)")
            st.table(pd.DataFrame(weather_results))
            
            fig = px.histogram(x=[r["Max Temp"] for r in weather_results], nbins=8, 
                               title=f"Ensemble Spread for {date_str}", labels={'x': 'Temp °C'})
            fig.add_vline(x=target_temp, line_dash="dash", line_color="red")
            st.plotly_chart(fig, width="stretch")

        with col2:
            st.subheader(f"⚖️ Betting Analysis: {bet_side}")
            m1, m2 = st.columns(2)
            m1.metric("Market Price", f"${curr_mkt:.2f}")
            m2.metric("Weighted Prob", f"{int(mod_prob*100)}%")
            
            st.divider()
            
            color = "green" if edge > 0.05 else "red" if edge < -0.05 else "gray"
            status = "UNDERVALUED" if edge > 0.05 else "OVERVALUED" if edge < -0.05 else "EFFICIENT"
            st.markdown(f"### <span style='color:{color}'>{status}</span>", unsafe_allow_html=True)
            st.metric("Calculated Edge", f"{edge*100:.1f}%")

            st.subheader("💰 Risk/Reward")
            p1, p2 = st.columns(2)
            p1.metric("Potential Profit", f"${net_profit:.2f}")
            p2.metric("ROI", f"{int((net_profit/wager_amount)*100)}%")

else:
    st.info(f"👈 Select a target date (up to 14 days out) and click 'Calculate'.")
