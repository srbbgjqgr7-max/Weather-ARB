import streamlit as st
import requests
import pandas as pd
import statistics
import plotly.express as px
from geopy.geocoders import Nominatim
from datetime import datetime, date, timedelta

# --- PAGE CONFIG ---
st.set_page_config(layout="wide", page_title="Weather Arb Quant v2026")
geolocator = Nominatim(user_agent="weather_arb_quant_v2")

st.title("🌩️ Weather Arb: Model Accuracy Scorecard")

# --- SIDEBAR ---
with st.sidebar:
    st.header("📍 Location")
    address = st.text_input("City", "London, UK")
    location = geolocator.geocode(address, timeout=10)
    lat, lon = (round(location.latitude, 2), round(location.longitude, 2)) if location else (51.5, -0.1)
    
    st.header("🎯 Accuracy Window")
    lookback_days = st.slider("Lookback Days", 3, 7, 5)
    run_scorecard = st.button("Generate Accuracy Report", type="primary")

# --- CORE LOGIC ---
if run_scorecard:
    # 1. Define models to test
    models = {"ECMWF": "ecmwf_ifs025", "GFS": "gfs_seamless", "ICON": "icon_seamless", "GEM": "gem_seamless"}
    
    # 2. Set timeframe (last X days ending yesterday)
    end_dt = date.today() - timedelta(days=1)
    start_dt = end_dt - timedelta(days=lookback_days-1)
    
    st.write(f"### 📊 Accuracy Analysis: {start_dt} to {end_dt}")
    
    # 3. Fetch Ground Truth (Actuals)
    actuals_url = f"https://archive-api.open-meteo.com/v1/archive?latitude={lat}&longitude={lon}&start_date={start_dt}&end_date={end_dt}&daily=temperature_2m_max&timezone=auto"
    try:
        actuals_data = requests.get(actuals_url).json()['daily']['temperature_2m_max']
    except:
        st.error("Could not fetch historical ground truth.")
        st.stop()
        
    # 4. Fetch Historical Forecasts for each model
    score_data = []
    
    for name, m_id in models.items():
        # Open-Meteo Archive also stores what the models *predicted* on those dates
        forecast_url = f"https://archive-api.open-meteo.com/v1/archive?latitude={lat}&longitude={lon}&start_date={start_dt}&end_date={end_dt}&daily=temperature_2m_max&models={m_id}&timezone=auto"
        try:
            forecasts = requests.get(forecast_url).json()['daily'][f'temperature_2m_max_{m_id}']
            
            # Calculate Errors
            errors = [abs(f - a) for f, a in zip(forecasts, actuals_data) if f is not None and a is not None]
            mae = statistics.mean(errors) if errors else 99
            
            score_data.append({"Model": name, "Mean Error (°C)": round(mae, 2), "Reliability": "High" if mae < 1.5 else "Medium" if mae < 3 else "Low"})
        except:
            continue

    # 5. Display Results
    if score_data:
        score_df = pd.DataFrame(score_data).sort_values("Mean Error (°C)")
        
        col1, col2 = st.columns([1, 2])
        
        with col1:
            st.subheader("🏆 Leaderboard")
            st.dataframe(score_df, hide_index=True)
            best_model = score_df.iloc[0]['Model']
            st.success(f"**Top Performer:** {best_model}")
            
        with col2:
            st.subheader("📈 Error Distribution")
            fig = px.bar(score_df, x="Model", y="Mean Error (°C)", color="Reliability",
                         color_discrete_map={"High": "green", "Medium": "orange", "Low": "red"})
            st.plotly_chart(fig, use_container_width=True)

        st.info(f"💡 **Strategy Tip:** For your next bet in {address}, consider giving {best_model} a 3x weight instead of 2x.")

else:
    st.info("👈 Choose a lookback window and click 'Generate Accuracy Report' to see which models are currently winning.")
