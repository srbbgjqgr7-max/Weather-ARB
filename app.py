import streamlit as st
import requests
import pandas as pd
import statistics
import plotly.express as px
from geopy.geocoders import Nominatim

# --- PAGE CONFIG ---
st.set_page_config(layout="wide", page_title="Weather Arb Pro 2026")
geolocator = Nominatim(user_agent="weather_arb_final_v3")

# Initialize Session State for Recent Searches
if 'history' not in st.session_state:
    st.session_state.history = []

st.title("🌡️ Weather vs. Polymarket Arbitrage")
st.markdown("Compare the 'Big 8' Global Weather Models against Market Odds.")

# --- SIDEBAR: INPUTS & HISTORY ---
with st.sidebar:
    st.header("📍 Search Location")
    
    # Recent Searches Dropdown
    if st.session_state.history:
        selected_history = st.selectbox("Recent Searches", [""] + st.session_state.history)
        if selected_history:
            address_input = selected_history
        else:
            address_input = st.text_input("Enter City (e.g., London, UK)", "London, UK")
    else:
        address_input = st.text_input("Enter City (e.g., London, UK)", "London, UK")

    # Geocoding Logic with Precision Fix
    location = geolocator.geocode(address_input, timeout=10)
    if location:
        lat = round(location.latitude, 2)
        lon = round(location.longitude, 2)
        st.success(f"Coordinates: {lat}, {lon}")
        # Add to history if new
        if address_input not in st.session_state.history:
            st.session_state.history.insert(0, address_input)
            st.session_state.history = st.session_state.history[:5] # Keep last 5
    else:
        st.error("Location not found. Defaulting to London.")
        lat, lon = 51.51, -0.13

    st.header("🎯 Market Parameters")
    target_temp = st.slider("Polymarket Hurdle (°C)", 10, 45, 30)
    market_price = st.slider("Polymarket 'Yes' Price ($)", 0.01, 0.99, 0.50)
    
    run_btn = st.button("Calculate Edge", type="primary")

# --- SPLIT WINDOW LAYOUT ---
col1, col2 = st.columns(2)

if run_btn:
    models = [
        "ecmwf_ifs025", "gfs_seamless", "icon_seamless", "gem_seamless", 
        "jma_seamless", "bom_access_g_global", "arpege_world", "cma_grapes_global"
    ]
    
    # API Call with refined coordinates to satisfy all 8 models
    url = "https://ensemble-api.open-meteo.com/v1/ensemble"
    params = {
        "latitude": lat, 
        "longitude": lon, 
        "daily": "temperature_2m_max", 
        "models": ",".join(models), 
        "timezone": "auto"
    }

    try:
        response_raw = requests.get(url, params=params, timeout=15)
        
        if response_raw.status_code != 200:
            st.error(f"Weather server rejected request (Error {response_raw.status_code}). Try a broader city name like 'London' instead of a specific airport.")
        else:
            response = response_raw.json()
            weather_data = []
            temps = []
            
            for m in models:
                key = f'temperature_2m_max_{m}'
                if 'daily' in response and key in response['daily']:
                    val = response['daily'][key][0]
                    if val is not None:
                        weather_data.append({"Model": m.split('_')[0].upper(), "Max Temp": val})
                        temps.append(val)

            if not temps:
                st.warning("No data found. Try a major city center.")
            else:
                avg_temp = statistics.mean(temps)
                models_above = len([t for t in temps if t >= target_temp])
                model_prob = models_above / len(temps)
                edge = model_prob - market_price

                # --- LEFT WINDOW: THE MODELS ---
                with col1:
                    st.subheader("🌐 Ensemble Predictions")
                    st.table(pd.DataFrame(weather_data))
                    fig = px.histogram(x=temps, nbins=5, title="Model Temperature Spread", labels={'x': 'Temp °C'})
                    fig.add_vline(x=target_temp, line_dash="dash", line_color="red", annotation_text="Market Hurdle")
                    st.plotly_chart(fig, use_container_width=True)

                # --- RIGHT WINDOW: THE ARBITRAGE ---
                with col2:
                    st.subheader("⚖️ Market Analysis")
                    st.metric("Ensemble Mean", f"{avg_temp:.1f}°C")
                    
                    m_col1, m_col2 = st.columns(2)
                    m_col1.metric("Market Prob", f"{market_price*100:.0f}%")
                    m_col2.metric("Model Prob", f"{model_prob*100:.0f}%")
                    
                    st.divider()
                    
                    if abs(edge) > 0.10:
                        color = "green" if edge > 0 else "red"
                        status = "UNDERVALUED" if edge > 0 else "OVERVALUED"
                        st.markdown(f"### <span style='color:{color}'>{status}</span>", unsafe_content_allowed=True)
                        st.metric("Calculated Edge", f"{edge*100:.1f}%")
                    else:
                        st.info("✅ Market is efficiently priced.")

    except Exception as e:
        st.error(f"Connection Error: {e}")

else:
    with col1: st.info("Search a city and click 'Calculate' to begin.")
    with col2: st.info("Arbitrage analysis will appear here.")
