import streamlit as st
import requests
import pandas as pd
import statistics
import plotly.express as px
from geopy.geocoders import Nominatim

# --- PAGE CONFIG ---
st.set_page_config(layout="wide", page_title="Weather Arb Dashboard")
# Initialize Geocoder with a custom user agent
geolocator = Nominatim(user_agent="weather_arb_app_v2_2026")

st.title("🌡️ Weather vs. Polymarket Arbitrage")
st.markdown("Compare the 'Big 8' Global Weather Models against Market Odds.")

# --- SIDEBAR: INPUTS & SEARCH ---
with st.sidebar:
    st.header("📍 Search Location")
    address = st.text_input("Enter City (e.g., London, UK)", "London, UK")
    
    # Geocoding Logic with Rounding Fix
    try:
        location = geolocator.geocode(address, timeout=10)
        if location:
            # FIX: Rounding to 2 decimal places prevents Error 400
            lat = round(location.latitude, 2)
            lon = round(location.longitude, 2)
            st.success(f"Location Found: {lat}, {lon}")
        else:
            st.error("Location not found. Using default (London).")
            lat, lon = 51.50, -0.12
    except:
        st.error("Geocoding service busy. Using default (London).")
        lat, lon = 51.50, -0.12

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
    params = {
        "latitude": lat, 
        "longitude": lon, 
        "daily": "temperature_2m_max", 
        "models": ",".join(models), 
        "timezone": "auto"
    }

    try:
        # Added timeout to prevent hanging
        response_raw = requests.get(url, params=params, timeout=15)
        
        if response_raw.status_code != 200:
            st.error(f"Weather server rejected request (Error {response_raw.status_code}). Try a different city.")
        else:
            response = response_raw.json()
            weather_data = []
            temps = []
            
            # Robust extraction loop
            for m in models:
                key = f'temperature_2m_max_{m}'
                if 'daily' in response and key in response['daily']:
                    val = response['daily'][key][0]
                    if val is not None:
                        weather_data.append({"Model": m.split('_')[0].upper(), "Max Temp": val})
                        temps.append(val)

            if not temps:
                st.warning("No model data available for this coordinate. Try a major city like 'Paris' or 'Tokyo'.")
            else:
                # --- CALCULATIONS ---
                avg_temp = statistics.mean(temps)
                models_above = len([t for t in temps if t >= target_temp])
                model_prob = models_above / len(temps)
                edge = model_prob - market_price

                # --- LEFT WINDOW: THE MODELS ---
                with col1:
                    st.subheader("🌐 Ensemble Predictions")
                    st.table(pd.DataFrame(weather_data))
                    
                    fig = px.histogram(x=temps, nbins=5, title="Model Distribution", labels={'x': 'Temp °C'})
                    fig.add_vline(x=target_temp, line_dash="dash", line_color="red", annotation_text="Market Target")
                    st.plotly_chart(fig, use_container_width=True)

                # --- RIGHT WINDOW: THE ARBITRAGE ---
                with col2:
                    st.subheader("⚖️ Market Analysis")
                    st.metric("Ensemble Mean", f"{avg_temp:.1f}°C")
                    
                    c1, c2 = st.columns(2)
                    c1.metric("Market Prob", f"{market_price*100:.0f}%")
                    c2.metric("Model Prob", f"{model_prob*100:.0f}%")
                    
                    st.divider()
                    
                    if abs(edge) > 0.10:
                        color = "green" if edge > 0 else "red"
                        status = "UNDERVALUED" if edge > 0 else "OVERVALUED"
                        st.markdown(f"### <span style='color:{color}'>{status}</span>", unsafe_content_allowed=True)
                        st.metric("Calculated Edge", f"{edge*100:.1f}%")
                    else:
                        st.write("✅ Market is efficiently priced.")

    except Exception as e:
        st.error(f"Connection Error: {e}")

else:
    with col1: st.info("Search a city and click 'Calculate' to see weather models.")
    with col2: st.info("Market arbitrage analysis will appear here.")
