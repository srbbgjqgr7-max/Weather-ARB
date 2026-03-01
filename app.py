import streamlit as st
import requests
import pandas as pd
import statistics
import plotly.express as px
from geopy.geocoders import Nominatim
from datetime import datetime, date, timedelta

# --- PAGE CONFIG ---
st.set_page_config(layout="wide", page_title="Weather Arb Quant Pro")
geolocator = Nominatim(user_agent="weather_arb_ultimate_v2")

# --- INITIAL MODEL CONFIG ---
MODEL_LIST = {
    "ECMWF": "ecmwf_ifs025", "GFS": "gfs_seamless", "ICON": "icon_seamless",
    "GEM": "gem_seamless", "JMA": "jma_seamless", "BOM": "bom_access_g_global",
    "ARPEGE": "arpege_world", "CMA": "cma_grapes_global"
}

st.title("🌡️ Weather Arb: Dynamic Quant Terminal")

# --- SHARED SIDEBAR ---
with st.sidebar:
    st.header("📍 Global Settings")
    address = st.text_input("Target City", "London, UK")
    location = geolocator.geocode(address, timeout=10)
    lat, lon = (round(location.latitude, 2), round(location.longitude, 2)) if location else (51.5, -0.1)
    
    st.header("⚙️ Risk Strategy")
    use_kelly = st.toggle("Enable Kelly Criterion", value=True)
    if use_kelly:
        bankroll = st.number_input("Total Bankroll ($)", 100, 1000000, 1000)
        kelly_fraction = st.select_slider("Kelly Multiplier", options=[0.1, 0.25, 0.5, 1.0], value=0.25)
    else:
        unit_size = st.number_input("Fixed Bet Size ($)", 1, 10000, 100)

    st.header("🧠 Weighting Engine")
    auto_weight = st.toggle("Enable Dynamic Weighting", value=True, help="Automatically increases weights for models with low historical error.")

# --- DYNAMIC WEIGHTING LOGIC ---
weights = {m: 1.0 for m in MODEL_LIST} # Default equal weights

if auto_weight:
    with st.status("Calculating Dynamic Weights...", expanded=False):
        end_d = date.today() - timedelta(days=1)
        start_d = end_d - timedelta(days=4)
        try:
            # Get Ground Truth
            act_url = f"https://archive-api.open-meteo.com/v1/archive?latitude={lat}&longitude={lon}&start_date={start_d}&end_date={end_d}&daily=temperature_2m_max&timezone=auto"
            actuals = requests.get(act_url).json()['daily']['temperature_2m_max']
            
            for name, m_id in MODEL_LIST.items():
                f_url = f"https://archive-api.open-meteo.com/v1/archive?latitude={lat}&longitude={lon}&start_date={start_d}&end_date={end_d}&daily=temperature_2m_max&models={m_id}&timezone=auto"
                f_data = requests.get(f_url).json()['daily'][f"temperature_2m_max_{m_id}"]
                mae = statistics.mean([abs(f - a) for f, a in zip(f_data, actuals) if f and a])
                # Accuracy Boost: Models with error < 1°C get 3x weight, < 2.5°C get 2x weight
                weights[name] = 3.0 if mae < 1.0 else 2.0 if mae < 2.5 else 1.0
        except:
            st.warning("Could not calculate dynamic weights. Using defaults.")

# --- TABS ---
tab1, tab2 = st.tabs(["🚀 Arbitrage Engine", "📊 Accuracy Scorecard"])

# --- TAB 1: ARBITRAGE ---
with tab1:
    col_a, col_b = st.columns([1, 2])
    with col_a:
        target_date = st.date_input("Forecast Date", value=date.today() + timedelta(days=1))
        target_temp = st.slider("Hurdle (°C)", 10.0, 45.0, 30.0, step=0.5)
        bet_side = st.radio("Bet Side:", ["Yes (> Target)", "No (≤ Target)"])
        y_price = st.number_input("'Yes' Price", 0.01, 0.99, 0.50)
        n_price = st.number_input("'No' Price", 0.01, 0.99, 0.50)
        run_arb = st.button("Calculate Edge", type="primary")

    if run_arb:
        date_str = target_date.strftime("%Y-%m-%d")
        weather_results, weighted_votes_above, total_weight = [], [], 0
        
        for name, m_id in MODEL_LIST.items():
            url = f"https://ensemble-api.open-meteo.com/v1/ensemble?latitude={lat}&longitude={lon}&daily=temperature_2m_max&models={m_id}&timezone=auto&start_date={date_str}&end_date={date_str}"
            try:
                val = requests.get(url).json()['daily'][f"temperature_2m_max_{m_id}"][0]
                if val is not None:
                    w = weights[name]
                    weather_results.append({"Model": name, "Temp": val, "Weight": w})
                    weighted_votes_above.append((1 if val > target_temp else 0) * w)
                    total_weight += w
            except: continue

        if weather_results:
            prob_yes = round(sum(weighted_votes_above) / total_weight, 4)
            mod_prob = prob_yes if "Yes" in bet_side else (1.0 - prob_yes)
            curr_mkt = y_price if "Yes" in bet_side else n_price
            edge = mod_prob - curr_mkt

            with col_b:
                st.subheader("⚖️ Analysis Results")
                res_1, res_2, res_3 = st.columns(3)
                res_1.metric("Weighted Prob", f"{mod_prob*100:.1f}%")
                res_2.metric("Market Price", f"${curr_mkt:.2f}")
                res_3.metric("Edge", f"{edge*100:.1f}%")

                if edge > 0:
                    if use_kelly:
                        raw_k = (mod_prob - curr_mkt) / (1 - curr_mkt)
                        stake = bankroll * raw_k * kelly_fraction
                        st.success(f"🔥 Positive Edge! Optimal Kelly Stake: **${stake:.2f}**")
                    else:
                        st.success(f"🔥 Positive Edge! Suggested Fixed Stake: **${unit_size:.2f}**")
                else:
                    st.error("❄️ Negative Edge. Avoid this bet.")

                st.divider()
                st.write("**Current Model Weights:**", weights)
                st.dataframe(pd.DataFrame(weather_results), hide_index=True)

# --- TAB 2: SCORECARD ---
with tab2:
    st.subheader("🏆 Accuracy Leaderboard")
    if st.button("Refresh Audit"):
        st.rerun()
    # Display the weights used based on the last audit
    st.write("Weights are assigned based on Mean Absolute Error (MAE) from the last 4 days.")
