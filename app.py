import streamlit as st
import requests
import pandas as pd
import statistics
import plotly.express as px
from geopy.geocoders import Nominatim

# --- PAGE CONFIG ---
st.set_page_config(layout="wide", page_title="Weather Arb Pro 2026")
geolocator = Nominatim(user_agent="weather_arb_final_v6")

if 'history' not in st.session_state:
    st.session_state.history = []

st.title("🌡️ Weather vs. Polymarket Arbitrage")
st.markdown("Compare the 'Big 8' Global Weather Models against Market Odds.")

# --- SIDEBAR ---
with st.sidebar:
    st.header("📍 Search Location")
    
    address_input = st.text_input("Enter City", "London, UK")

    location = geolocator.geocode(address_input, timeout=10)
    if location:
        # We format as strings first to ensure NO extra trailing digits are sent
        lat_str = "{:.2f}".format(location.latitude)
        lon_str = "{:.2f}".format(location.longitude)
        st.success(f"Coordinates: {lat_str}, {lon_str}")
    else:
        st.error("Location not found. Using default.")
        lat_str, lon_str = "51.51", "-0.13"

    st.header("🎯 Market Parameters")
    target_temp = st.slider("Polymarket Hurdle (°C)", 10, 45, 30)
    market_price = st.slider("Polymarket 'Yes' Price ($)", 0.01, 0.99, 0.50)
    run_btn = st.button("Calculate Edge", type="primary")

# --- MAIN APP LOGIC ---
col1, col2 = st.columns(2)

if run_btn:
    # We use the most stable identifiers for these 8 models
    models = [
        "ecmwf_ifs025", "gfs_seamless", "icon_seamless", "gem_seamless", 
        "jma_seamless", "bom_access_g_global", "arpege_world", "cma_grapes_global"
    ]
    
    weather_data = []
    temps = []

    progress_text = "Contacting Global Weather Centers..."
    my_bar = st.progress(0, text=progress_text)

    for i, m in enumerate(models):
        # NEW URL STRATEGY: We build the URL manually to ensure zero formatting errors
        url = f"https://ensemble-api.open-meteo.com/v1/ensemble?latitude={lat_str}&longitude={lon_str}&daily=temperature_2m_max&models={m}&timezone=auto"
        
        try:
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                # Dynamically find the key because the API sometimes changes the suffix
                daily_keys = data.get('daily', {}).keys()
                temp_key = [k for k in daily_keys if 'temperature_2m_max' in k]
                
                if temp_key:
                    val = data['daily'][temp_key[0]][0]
                    if val is not None:
                        weather_data.append({"Model": m.split('_')[0].upper(), "Max Temp": val})
                        temps.append(val)
        except Exception as e:
            pass # Skip failed models silently
        
        my_bar.progress((i + 1) / len(models), text=progress_text)
    
    my_bar.empty()

    if not temps:
        st.error("The weather server is rejecting these coordinates. Try searching for a different nearby city (e.g., 'Watford' or 'Croydon') to reset the grid locator.")
    else:
        avg_temp = statistics.mean(temps)
        model_prob = len([t for t in temps if t >= target_temp]) / len(temps)
        edge = model_prob - market_price

        with col1:
            st.subheader(f"🌐 Ensemble Results ({len(temps)}/8)")
            st.table(pd.DataFrame(weather_data))
            fig = px.histogram(x=temps, nbins=5, title="Model Spread", labels={'x': 'Temp °C'})
            fig.add_vline(x=target_temp, line_dash="dash", line_color="red")
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            st.subheader("⚖️ Market Analysis")
            st.metric("Ensemble Mean", f"{avg_temp:.1f}°C")
            
            c1, c2 = st.columns(2)
            c1.metric("Market Prob", f"{market_price*100:.0f}%")
            c2.metric("Model Prob", f"{model_prob*100:.0f}%")
            
            st.divider()
            
            color = "green" if edge > 0 else "red" if edge < 0 else "gray"
            status = "UNDERVALUED" if edge > 0 else "OVERVALUED" if edge < 0 else "EFFICIENT"
            
            st.markdown(f"### <span style='color:{color}'>{status}</span>", unsafe_content_allowed=True)
            st.metric("Calculated Edge", f"{edge*100:.1f}%")

else:
    with col1: st.info("Search a city and click 'Calculate' to begin.")
    with col2: st.info("Arbitrage analysis will appear here.")
