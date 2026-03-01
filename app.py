import streamlit as st
import requests
import pandas as pd
import statistics
import plotly.express as px
from geopy.geocoders import Nominatim

# --- PAGE CONFIG ---
st.set_page_config(layout="wide", page_title="Weather Arb Dashboard")
geolocator = Nominatim(user_agent="weather_arb_app_2026")

st.title("🌡️ Weather vs. Polymarket Arbitrage")
st.markdown("Compare the 'Big 8' Global Weather Models against Market Odds.")

# --- SIDEBAR: INPUTS & SEARCH ---
with st.sidebar:
    st.header("📍 Search Location")
    address = st.text_input("Enter City (e.g., London, UK)", "New York, USA")
    
    # Geocoding Logic
    location = geolocator.geocode(address)
    if location:
        lat, lon = location.latitude, location.longitude
        st.success(f"Location Found: {lat:.2f}, {lon:.2f}")
    else:
        st.error("Location not found.")
        lat, lon = 40.71, -74.00

    st.header("🎯 Market Parameters")
    target_temp = st.slider("Polymarket Hurdle (°C)", 10, 45, 30)
    market_price = st.slider("Polymarket 'Yes' Price ($)", 0.01, 0.99, 0.50)
    
    run_btn = st.button("Calculate Edge", type="primary")

# --- SPLIT WINDOW LAYOUT ---
col1, col2 = st.columns(2)

if run_btn:
    # 1. FETCH WEATHER DATA
    models = [
        "ecmwf_ifs025", "gfs_seamless", "icon_seamless", "gem_seamless", 
        "jma_seamless", "bom_access_g_global", "arpege_world", "cma_grapes_global"
    ]
    
    url = "https://ensemble-api.open-meteo.com/v1/ensemble"
    params = {"latitude": lat, "longitude": lon, "daily": "temperature_2m_max", 
              "models": ",".join(models), "timezone": "auto"}

    try:
        response = requests.get(url).json()
        weather_data = []
        temps = []
        
        for m in models:
            t = response['daily'][f'temperature_2m_max_{m}'][0]
            weather_data.append({"Model": m.split('_')[0].upper(), "Max Temp": t})
            temps.append(t)

        # 2. CALCULATE PROBABILITY
        avg_temp = statistics.mean(temps)
        models_above = len([t for t in temps if t >= target_temp])
        model_prob = models_above / len(models)
        edge = model_prob - market_price

        # --- LEFT WINDOW: THE MODELS ---
        with col1:
            st.subheader("🌐 Ensemble Predictions")
            st.table(pd.DataFrame(weather_data))
            
            # Distribution Chart
            fig = px.histogram(x=temps, nbins=5, title="Model Distribution")
            fig.add_vline(x=target_temp, line_dash="dash", line_color="red")
            st.plotly_chart(fig, use_container_width=True)

        # --- RIGHT WINDOW: THE ARBITRAGE ---
        with col2:
            st.subheader("⚖️ Market Analysis")
            st.metric("Ensemble Mean", f"{avg_temp:.1f}°C")
            
            st.write(f"**Market Probability:** {market_price*100:.0f}%")
            st.write(f"**Model Probability:** {model_prob*100:.0f}%")
            
            st.divider()
            
            if abs(edge) > 0.10:
                color = "green" if edge > 0 else "red"
                st.markdown(f"### EDGE: <span style='color:{color}'>{edge*100:.1f}%</span>", unsafe_content_allowed=True)
                st.write("Suggests market is " + ("undervaluing" if edge > 0 else "overvaluing") + " the heat.")
            else:
                st.write("✅ No significant edge detected.")

    except Exception as e:
        st.error(f"API Error: {e}")
