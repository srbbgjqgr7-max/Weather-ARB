        # --- CALCULATIONS ---
        weighted_avg_temp = sum(weighted_temps) / total_possible_weight
        prob_above = round(sum(weighted_votes_above) / total_possible_weight, 2)
        prob_below = 1.0 - prob_above
        
        curr_mkt = yes_price if "Yes" in bet_side else no_price
        mod_prob = prob_above if "Yes" in bet_side else prob_below
        
        # Calculate Edge
        edge = mod_prob - curr_mkt
        
        # Break-even Price is the raw model probability
        break_even = mod_prob
        
        # CORRECTED PROFIT LOGIC
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
            # --- GAUGE FIGURE ---
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

            # --- STATS ---
            m1, m2, m3 = st.columns(3)
            m1.metric("Model Prob", f"{int(mod_prob*100)}%")
            m2.metric("Market Price", f"${curr_mkt:.2f}")
            m3.metric("Edge", f"{edge*100:.1f}%")
            
            st.divider()
            
            # --- STATUS AND PROFIT DISPLAY ---
            color = "green" if edge > 0.05 else "red" if edge < -0.05 else "gray"
            status = "UNDERVALUED" if edge > 0.05 else "OVERVALUED" if edge < -0.05 else "EFFICIENT"
            
            st.markdown(f"### Status: <span style='color:{color}'>{status}</span>", unsafe_allow_html=True)
            
            # Highlighted Metrics
            p_col1, p_col2 = st.columns(2)
            p_col1.write(f"Potential **Net Profit**: **${net_profit:.2f}**")
            p_col1.write(f"Total Payout: **${total_payout:.2f}**")
            
            # BREAK-EVEN METRIC
            p_col2.write(f"🎯 **Break-even Price**: **${break_even:.2f}**")
            p_col2.info(f"Do not buy {bet_side} if the price is above ${break_even:.2f}.")
