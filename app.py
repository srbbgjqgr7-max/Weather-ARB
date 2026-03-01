import streamlit as st
import requests
import pandas as pd
import statistics
import plotly.express as px
from geopy.geocoders import Nominatim
from datetime import datetime
import time

# --- PAGE CONFIG ---
st.set_page_config(layout="wide", page_title="Weather Arb Pro 2026")
geolocator = Nominatim(user_agent="weather_arb_v13_payout")

st.title("🌡️ Weather vs. Polymarket Arbitrage")
st.markdown("Global Ensemble Models + Weighted Probability + Risk/Reward Analysis")

# --- SIDEBAR ---
with st.sidebar:
    st.header("📍 Search Location")
    address_input = st.text_input("Enter City", "London, UK")

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

    run_btn = st.button("Calculate Edge & Payout", type="primary")

# --- MAIN APP LOGIC ---
col1, col2 = st.columns(2)

if run_btn:
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
    
    progress_bar = st.progress(0, text="Fetching Weighted Ensemble...")

    for i, (name, config) in enumerate(model_config.items()):
        api_id = config["id"]
        weight = config["weight"]
        coords_to_try = [(lat, lon), (round(lat, 1), round(lon, 1))]
        
        for try_lat, try_lon in coords_to_try:
            url = f"https://ensemble-api.open-meteo.com/v1/ensemble?latitude={try_lat}&longitude={try_lon}&daily=temperature_2m_max&models={api_id}&timezone=auto"
            try:
                resp = requests.get(url, timeout=8)
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
        st.error("API Error. Please try a different location.")
    else:
        # --- CALCULATIONS ---
        avg_temp = statistics.mean([r["Max Temp"] for r in weather_results])
        prob_above = round(sum(weighted_votes) / total_possible_weight, 2)
        prob_below = 1 - prob_above
        
        curr_mkt = yes_price if "Yes" in bet_side else no_price
        mod_prob = prob_above if "Yes" in bet_side else prob_below
        edge = mod_prob - curr_mkt

        # --- PAYOUT LOGIC ---
        # Payout = Wager / Price (e.g., $100 / $0.50 = $200 total return)
        total_payout = wager_amount / curr_mkt
        net_profit = total_payout - wager_amount
        roi = (net_profit / wager_amount) * 100

        with col1:
            st.subheader(f"🌐 Ensemble Results ({len(weather_results)}/8)")
            st.table(pd.DataFrame(weather_results))
            
            fig = px.histogram(x=[r["Max Temp"] for r in weather_results], nbins=8, title="Model Spread", labels={'x': 'Temp °C'})
            fig.add_vline(x=target_temp, line_dash="dash", line_color="red")
            st.plotly_chart(fig, width="stretch")

        with col2:
            st.subheader(f"⚖️ Betting Analysis: {bet_side}")
            
            m1, m2 = st.columns(2)
            m1.metric("Market Price", f"${curr_mkt:.2f}")
            m2.metric("Weighted Prob", f"{int(mod_prob*100)}%")
            
            st.divider()
            
            # Status and Edge
            color = "green" if edge > 0.05 else "red" if edge < -0.05 else "gray"
            status = "UNDERVALUED" if edge > 0.05 else "OVERVALUED" if edge < -0.05 else "EFFICIENT"
            st.markdown(f"### <span style='color:{color}'>{status}</span>", unsafe_allow_html=True)
            st.metric("Calculated Edge", f"{edge*100:.1f}%")

            # Risk/Reward Section
            st.subheader("💰 Risk/Reward ($)")
            p_col1, p_col2, p_col3 = st.columns(3)
            p_col1.metric("Total Return", f"${total_payout:.2f}")
            p_col2.metric("Net Profit", f"${net_profit:.2f}")
            p_col3.metric("ROI", f"{int(roi)}%")

            if edge > 0.10:
                st.success(f"✅ Strong Arbitrage! Betting ${wager_amount} yields a potential profit of ${net_profit:.2f}.")
            elif edge < -0.10:
                st.error("❌ High Risk. Market is significantly overpriced compared to models.")

else:
    st.info("👈 Set your parameters and click 'Calculate Edge & Payout'.")
