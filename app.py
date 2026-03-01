import streamlit as st
import requests
import pandas as pd
import statistics
import plotly.express as px
from geopy.geocoders import Nominatim
from datetime import datetime

# --- PAGE CONFIG ---
st.set_page_config(layout="wide", page_title="Weather Arb Pro 2026")
geolocator = Nominatim(user_agent="weather_arb_final_v9")

st.title("🌡️ Weather vs. Polymarket Arbitrage")
st.markdown("Compare the 'Big 8' Global Weather Models against Market Odds.")

# --- SIDEBAR ---
with st.sidebar:
    st.header("📍 Search Location")
    address_input = st.text_input("Enter City", "London, UK")

    location = geolocator.geocode(address_input, timeout=10)
    if location:
        lat_str = "{:.2f}".format(location.latitude)
        lon_str = "{:.2f}".format(location.longitude)
        st.success(f"Coordinates: {lat_str}, {lon_str}")
    else:
        lat_str, lon_str = "51.51", "-0.13"

    st.header("🎯 Market Parameters")
    target_temp = st.slider("Polymarket Hurdle (°C)", 10, 45, 30)
    
    # Selection for Betting Direction
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
    models = ["ecmwf_ifs025", "gfs_seamless", "icon_seamless", "gem_seamless", 
              "jma_seamless", "bom_access_g_global", "arpege_world", "cma_grapes_global"]
    
    weather_data = []
    temps = []
    progress_text = "Fetching Global Models..."
    my_bar = st.progress(0, text=progress_text)

    for i, m in enumerate(models):
        url = f"https://ensemble-api.open-meteo.com/v1/ensemble?latitude={lat_str}&longitude={lon_str}&daily=temperature_2m_max&models={m}&timezone=auto"
        try:
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                temp_key = [k for k in data.get('daily', {}).keys() if 'temperature_2m_max' in k]
                if temp_key:
                    val = data['daily'][temp_key[0]][0]
                    if val is not None:
                        weather_data.append({"Model": m.split('_')[0].upper(), "Max Temp": val})
                        temps.append(val)
        except:
            pass
        my_bar.progress((i + 1) / len(models), text=progress_text)
    
    my_bar.empty()

    if not temps:
        st.error("API Error. Try a broader city name.")
    else:
        # --- CALCULATIONS ---
        avg_temp = statistics.mean(temps)
        last_updated = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Calculate Probabilities
        prob_above = len([t for t in temps if t >= target_temp]) / len(temps)
        prob_below = 1 - prob_above
        
        # Determine Edge based on user selection
        if "Yes" in bet_side:
            current_market_prob = yes_price
            model_prob = prob_above
            label = "Above Hurdle"
        else:
            current_market_prob = no_price
            model_prob = prob_below
            label = "Below Hurdle"
            
        edge = model_prob - current_market_prob

        with col1:
            st.subheader(f"🌐 Ensemble Results ({len(temps)}/8)")
            st.table(pd.DataFrame(weather_data))
            st.caption(f"🕒 Data Last Updated: {last_updated}")
            
            fig = px.histogram(x=temps, nbins=5, title="Model Temperature Spread", labels={'x': 'Temp °C'})
            fig.add_vline(x=target_temp, line_dash="dash", line_color="red", annotation_text="Hurdle")
            st.plotly_chart(fig, width="stretch")

        with col2:
            st.subheader(f"⚖️ {bet_side} Analysis")
            st.metric("Ensemble Mean", f"{avg_temp:.1f}°C")
            
            c1, c2 = st.columns(2)
            c1.metric("Market Price", f"${current_market_prob:.2f}")
            c2.metric("Model Prob", f"{int(model_prob*100)}%")
            
            st.divider()
            
            if edge > 0.05:
                status, color = "UNDERVALUED", "green"
                advice = f"The models suggest '{bet_side}' is more likely than the market reflects."
            elif edge < -0.05:
                status, color = "OVERVALUED", "red"
                advice = f"The market is overestimating the '{bet_side}' outcome."
            else:
                status, color = "EFFICIENT", "gray"
                advice = "The market price closely matches model consensus."
            
            st.markdown(f"### <span style='color:{color}'>{status}</span>", unsafe_allow_html=True)
            st.metric("Calculated Edge", f"{edge*100:.1f}%")
            st.info(f"💡 {advice}")

else:
    with col1: st.info("Search a city and click 'Calculate' to see the Big 8 models.")
    with col2: st.info("Arbitrage calculations will appear here.")
