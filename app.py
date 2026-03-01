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
geolocator = Nominatim(user_agent="weather_arb_v15_final_fix")

st.title("🌡️ Weather vs. Polymarket Arbitrage")
st.markdown("Global Ensemble Models + **Weighted Mean & Break-even Analysis**")

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
    if location:
        lat, lon = round(location.latitude, 2), round(location.longitude, 2)
        st.success(f"Coordinates: {lat}, {lon}")
    else:
        lat, lon = 51.5, -0.1

    st.header("🎯 Market Parameters")
    target_temp = st.slider("Polymarket Hurdle (°C)", 10.0, 45.0, 30.0, step=0.5)
    
    bet_side = st.radio("Analyzing Side:", ["Yes (Strictly Above >)", "No (Lower or Equal ≤)"])
    
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
    weighted_temps = []
    weighted_votes_above = []
    total_possible_weight = 0
    
    progress_bar = st.progress(0, text=f"Fetching Models for {date_str}...")

    for i, (name, config) in enumerate(model_config.items()):
        api_id, weight = config["id"], config["weight"]
        coords_to_try = [(lat, lon), (round(lat, 1), round(lon, 1))]
        
        for try_lat, try_lon in coords_to_try:
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
                            weighted_temps.append(val * weight)
                            
                            # LOGIC: 'Yes' only wins if strictly GREATER than target
                            is_above = 1 if val > target_temp else 0
                            weighted_votes_above.append(is_above * weight)
                            
                            total_possible_weight += weight
                            break
            except:
                continue
        progress_bar.progress((i + 1) / len(model_config))
    
    progress_bar.empty()

    if not weather_results:
        st.error(f"No model data found for {date_str}.")
    else:
        # --- CALCULATIONS ---
        weighted_avg_temp = sum(weighted_temps) / total_possible_weight
        prob_above = round(sum(weighted_votes_above) / total_possible_weight, 2)
        prob_below = 1.0 - prob_above
        
        curr_mkt = yes_price if "Yes" in bet_side else no_price
        mod_prob = prob_above if "Yes" in bet_side else prob_below
        
        # Calculate Edge and Break-even
        edge = mod_prob - curr_mkt
        break_even = mod_prob
        
        # Profit Calculations
        total_payout = wager_amount / curr_mkt
        net_profit = total_payout - wager_amount

        with col1:
            st.subheader(f"🌐 Ensemble Spread ({date_str})")
            fig_hist = px.histogram(pd.DataFrame(weather_results), x="Max Temp", nbins=8, 
                                   labels={'Max Temp': 'Temp °C'}, color_discrete_sequence=['#636EFA'])
            fig_hist.add_vline(x=target_temp, line_dash="dash", line_color="red", annotation_text="Hurdle")
            st.plotly_chart(fig_hist, use_container_width=True)
            st.table(pd.DataFrame(weather_results))

        with col2:
            st.subheader("📊 Weighted Average Figure")
            # Gauge Figure
            fig_gauge = go.Figure(go.Indicator(
                mode = "gauge+number",
                value = weighted_avg_temp,
                title = {'text': "Weighted Mean Max Temp (°C)", 'font': {'size': 18}},
                gauge = {
                    'axis': {'range': [None, 45]},
                    'bar': {'color': "#636EFA"},
                    'threshold': {'line': {'color': "red", 'width': 4}, 'thickness': 0.75, 'value': target_temp}
                }
            ))
            fig_gauge.update_layout(height=300, margin=dict(l=20, r=20, t=50, b=20))
            st.plotly_chart(fig_gauge, use_container_width=True)

            # Metrics Row
            m1, m2, m3 = st.columns(3)
            m1.metric("Model Prob", f"{int(mod_prob*100)}%")
            m2.metric("Market Price", f"${curr_mkt:.2f}")
            m3.metric("Edge", f"{edge*100:.1f}%")
            
            st.divider()
            
            # Status and Profit
            color = "green" if edge > 0.05 else "red" if edge < -0.05 else "gray"
            status = "UNDERVALUED" if edge > 0.05 else "OVERVALUED" if edge < -0.05 else "EFFICIENT"
            st.markdown(f"### Status: <span style='color:{color}'>{status}</span>", unsafe_allow_html=True)
            
            p_col1, p_col2 = st.columns(2)
            with p_col1:
                st.write(f"Potential **Net Profit**: **${net_profit:.2f}**")
                st.write(f"Total Payout: **${total_payout:.2f}**")
            
            with p_col2:
                st.write(f"🎯 **Break-even Price**: **${break_even:.2f}**")
                st.info(f"Avoid buying if price > ${break_even:.2f}")

else:
    st.info(f"👈 Select your target date and click 'Calculate'.")
