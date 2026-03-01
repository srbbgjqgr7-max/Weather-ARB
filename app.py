import streamlit as st
import requests
import pandas as pd
import statistics
import plotly.express as px
import plotly.graph_objects as go
from geopy.geocoders import Nominatim
from datetime import datetime, date, timedelta
import time

# --- PAGE CONFIG ---
st.set_page_config(layout="wide", page_title="Weather Arb Pro 2026")
geolocator = Nominatim(user_agent="weather_arb_v18_consensus")

st.title("🌡️ Weather vs. Polymarket Arbitrage")
st.markdown("Global Ensemble Models + Kelly Criterion + Consensus Analytics")

# --- SIDEBAR ---
with st.sidebar:
    st.header("📍 Location & Date")
    address_input = st.text_input("Enter City", "London, UK")
    selected_date = st.date_input("Forecast Date", value=date.today() + timedelta(days=1))

    location = geolocator.geocode(address_input, timeout=10)
    lat, lon = (round(location.latitude, 2), round(location.longitude, 2)) if location else (51.5, -0.1)

    st.header("🎯 Market Parameters")
    target_temp = st.slider("Polymarket Hurdle (°C)", 10.0, 45.0, 30.0, step=0.5)
    bet_side = st.radio("Analyzing Side:", ["Yes (Strictly Above >)", "No (Lower or Equal ≤)"])
    
    c_p1, c_p2 = st.columns(2)
    yes_price = c_p1.number_input("'Yes' Price", 0.01, 0.99, 0.50)
    no_price = c_p2.number_input("'No' Price", 0.01, 0.99, 0.50)

    st.header("💰 Bankroll")
    total_bankroll = st.number_input("Total Bankroll ($)", 100, 1000000, 1000)
    kelly_fraction = st.select_slider("Kelly Multiplier", options=[0.1, 0.25, 0.5, 1.0], value=0.25)

    run_btn = st.button("Calculate Optimal Bet", type="primary")

# --- MAIN APP LOGIC ---
if run_btn:
    date_str = selected_date.strftime("%Y-%m-%d")
    model_config = {
        "ECMWF": {"id": "ecmwf_ifs025", "weight": 2.0}, "GFS": {"id": "gfs_seamless", "weight": 2.0},
        "ICON": {"id": "icon_seamless", "weight": 1.0}, "GEM": {"id": "gem_seamless", "weight": 1.0},
        "JMA": {"id": "jma_seamless", "weight": 1.0}, "BOM": {"id": "bom_access_g_global", "weight": 1.0},
        "ARPEGE": {"id": "arpege_world", "weight": 1.0}, "CMA": {"id": "cma_grapes_global", "weight": 1.0}
    }
    
    weather_results, total_weight, votes_yes, votes_no = [], 0, 0, 0
    progress_bar = st.progress(0, text="Syncing Models...")

    for i, (name, config) in enumerate(model_config.items()):
        url = f"https://ensemble-api.open-meteo.com/v1/ensemble?latitude={lat}&longitude={lon}&daily=temperature_2m_max&models={config['id']}&timezone=auto&start_date={date_str}&end_date={date_str}"
        try:
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                val = resp.json()['daily'].get(f"temperature_2m_max_{config['id']}", [None])[0]
                if val is not None:
                    weather_results.append({"Model": name, "Max Temp": val, "Weight": config['weight']})
                    if val > target_temp: votes_yes += config['weight']
                    else: votes_no += config['weight']
                    total_weight += config['weight']
        except: continue
        progress_bar.progress((i + 1) / len(model_config))
    progress_bar.empty()

    if weather_results:
        col1, col2, col3 = st.columns([1, 1, 1])
        
        # --- PROBABILITIES ---
        prob_yes = votes_yes / total_weight
        prob_no = 1.0 - prob_yes
        curr_mkt = yes_price if "Yes" in bet_side else no_price
        mod_prob = prob_yes if "Yes" in bet_side else prob_no
        edge = mod_prob - curr_mkt
        
        with col1:
            st.subheader("📊 Model Consensus")
            fig_donut = go.Figure(data=[go.Pie(labels=['Yes (> Target)', 'No (≤ Target)'], 
                                             values=[votes_yes, votes_no], hole=.6,
                                             marker_colors=['#00CC96', '#EF553B'])])
            fig_donut.update_layout(showlegend=False, height=300, margin=dict(t=0, b=0, l=0, r=0))
            st.plotly_chart(fig_donut, use_container_width=True)
            st.write(f"**Agreement:** {max(prob_yes, prob_no)*100:.0f}% of weighted ensemble.")

        with col2:
            st.subheader("⚖️ Edge Analysis")
            st.metric("Model Prob", f"{mod_prob*100:.1f}%")
            st.metric("Market Price", f"${curr_mkt:.2f}")
            
            if mod_prob > curr_mkt:
                st.success(f"Positive Edge: {edge*100:.1f}%")
                # Kelly Calculation
                raw_kelly = (mod_prob - curr_mkt) / (1 - curr_mkt)
                suggested_bet = total_bankroll * raw_kelly * kelly_fraction
                st.metric("Suggested Stake", f"${suggested_bet:.2f}")
            else:
                st.error(f"Negative Edge: {edge*100:.1f}%")
                st.write("Kelly Criterion suggests no bet ($0.00).")

        with col3:
            st.subheader("🌡️ Data Summary")
            st.dataframe(pd.DataFrame(weather_results), hide_index=True)
            avg_t = statistics.mean([r["Max Temp"] for r in weather_results])
            st.metric("Ensemble Mean", f"{avg_t:.1f}°C")

else:
    st.info("👈 Enter market data and click 'Calculate Optimal Bet'.")
