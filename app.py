import streamlit as st
import requests
import pandas as pd
import statistics
import plotly.express as px
from geopy.geocoders import Nominatim
from datetime import datetime

# --- PAGE CONFIG ---
st.set_page_config(layout="wide", page_title="Weather Arb Pro 2026")
geolocator = Nominatim(user_agent="weather_arb_final_v10")

st.title("🌡️ Weather vs. Polymarket Arbitrage")
st.markdown("Compare the 'Big 8' Global Weather Models against Market Odds.")

# --- SIDEBAR ---
with st.sidebar:
    st.header("📍 Search Location")
    address_input = st.text_input("Enter City", "London, UK")

    location = geolocator.geocode(address_input, timeout=10)
    if location:
        lat, lon = round(location.latitude, 2), round(location.longitude, 2)
        st.success(f"Coordinates: {lat}, {lon}")
    else:
        lat, lon = 51.51, -0.13

    st.header("🎯 Market Parameters")
    target_temp = st.slider("Polymarket Hurdle (°C)", 10, 45, 30)
    bet_side = st.radio("Which side are you analyzing?", ["Yes (Above)", "No (Below)"])
    
    col_p1, col_p2 = st.columns(2)
    with col_p1:
        yes_price = st.number_input("'Yes' Price ($)", 0.01, 0.99, 0.50, step=0.01)
    with col_p2:
        no_price = st.number_input("'No' Price ($)", 0.01, 0.99, 0.50, step=0.01)

    run_btn = st.button("Calculate Edge", type="primary")

# --- MAIN APP LOGIC ---
col1, col2 = st.columns(2)

if run_btn:
    # List of the 8 core global models
    models = [
        "ecmwf_ifs025", "gfs_seamless", "icon_seamless", "gem_seamless", 
        "jma_seamless", "bom_access_g_global", "arpege_world", "cma_grapes_global"
    ]
    
    # BATCH REQUEST: Fetching all 8 at once to avoid rate limits
    url = "https://ensemble-api.open-meteo.com/v1/ensemble"
    params = {
        "latitude": lat,
        "longitude": lon,
        "daily": "temperature_2m_max",
        "models": ",".join(models),
        "timezone": "auto"
    }

    try:
        response = requests.get(url, params=params, timeout=15)
        if response.status_code == 200:
            data = response.json()
            weather_results = []
            temps = []
            
            # Extract daily data for each model
            if 'daily' in data:
                for m in models:
                    key = f"temperature_2m_max_{m}"
                    if key in data['daily']:
                        val = data['daily'][key][0]
                        if val is not None:
                            weather_results.append({"Model": m.split('_')[0].upper(), "Max Temp": val})
                            temps.append(val)
            
            if not temps:
                st.error("Data received but contained no temperatures. Try a major city name.")
            else:
                # --- CALCULATIONS ---
                avg_temp = statistics.mean(temps)
                last_updated = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                prob_above = len([t for t in temps if t >= target_temp]) / len(temps)
                prob_below = 1 - prob_above
                
                # Logic for Bet Selection
                current_market_prob = yes_price if "Yes" in bet_side else no_price
                model_prob = prob_above if "Yes" in bet_side else prob_below
                edge = model_prob - current_market_prob

                # --- DISPLAY ---
                with col1:
                    st.subheader(f"🌐 Ensemble Results ({len(temps)}/8)")
                    st.table(pd.DataFrame(weather_results))
                    st.caption(f"🕒 Last Updated: {last_updated}")
                    
                    fig = px.histogram(x=temps, nbins=5, title="Model Spread", labels={'x': 'Temp °C'})
                    fig.add_vline(x=target_temp, line_dash="dash", line_color="red")
                    st.plotly_chart(fig, width="stretch")

                with col2:
                    st.subheader(f"⚖️ {bet_side} Analysis")
                    st.metric("Ensemble Mean", f"{avg_temp:.1f}°C")
                    
                    c1, c2 = st.columns(2)
                    c1.metric("Market Price", f"${current_market_prob:.2f}")
                    c2.metric("Model Prob", f"{int(model_prob*100)}%")
                    
                    st.divider()
                    
                    color = "green" if edge > 0.05 else "red" if edge < -0.05 else "gray"
                    status = "UNDERVALUED" if edge > 0.05 else "OVERVALUED" if edge < -0.05 else "EFFICIENT"
                    
                    st.markdown(f"### <span style='color:{color}'>{status}</span>", unsafe_allow_html=True)
                    st.metric("Calculated Edge", f"{edge*100:.1f}%")

        else:
            st.error(f"Weather server error ({response.status_code}). Try again in 30 seconds.")
            
    except Exception as e:
        st.error(f"Connection error: {e}")

else:
    with col1: st.info("Enter location and click Calculate.")
    with col2: st.info("Results will appear here.")
