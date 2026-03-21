import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timedelta
import plotly.graph_objects as go

# Sivun asetukset
st.set_page_config(page_title="EV Latauslaskuri Pro", layout="wide")

# --- ALUSTUS (Session State) ---
# Alustetaan oletusarvot ja session state -muuttujat
if 'init_done' not in st.session_state:
    now = datetime.now()
    st.session_state.d_start = now.date()
    st.session_state.t_start = (now - timedelta(hours=2)).time()
    st.session_state.d_end = now.date()
    st.session_state.t_end = now.time()
    st.session_state.billing_method = "Keskituntihinta" # Oletuslaskutustapa
    st.session_state.init_done = True

st.title("🔋 Sähköauton latauskustannus")
st.markdown("Analysoi latauksen hinta ja tarkista sähkön hintavaihtelut.")

# --- SIVUPALKKI: ASETUKSET ---
with st.sidebar:
    st.header("Asetukset")
    
    # 1. Sopimustiedot
    sopimus = st.radio("Valitse sopimustyyppi", ["Pörssisähkö", "Kiinteä"])
    if sopimus == "Kiinteä":
        hinta_snt = st.number_input("Sähkön hinta snt/kWh", value=10.0, step=0.1)
        marginaali_snt = 0.0
    else:
        hinta_snt = 0.0
        marginaali_snt = st.number_input("Marginaali snt/kWh", value=0.0, step=0.01)

    st.divider()
    
    # 2. Laskutustapa - UUSI ASETUS
    st.subheader("Laskutustapa")
    st.write("Tämä vaikuttaa siihen, kuinka sähköyhtiö veloittaa pörssisähkön käytöstäsi (riippuu sähkömittaristasi).")
    billing_method = st.radio("Valitse menetelmä", ["Keskituntihinta", "Varttitase (15 min)"], key="billing_method")
    st.write("*Note: Varttihinnat ovat simuloituja, koska julkinen API tarjoaa tällä hetkellä vain tunnin keskiarvoja.*")

    st.divider()
    
    # 3. Kiinteät kustannukset ja määrä
    siirto_snt = st.number_input("Siirtohinta snt/kWh", value=5.75, step=0.01)
    perus_snt = st.number_input("Perusmaksu snt/päivä", value=17.0, step=1.0)
    kwh = st.number_input("Ladattu määrä (kWh)", value=20.0, step=0.5)

# --- PÄÄNÄKYMÄ: AIKAVALINTA ---
st.subheader("Latausajankohta")
col_a, col_b = st.columns(2)
with col_a:
    d_start = st.date_input("Alkupäivä", key="d_start")
    t_start = st.time_input("Alkuaika", key="t_start", step=60)
with col_b:
    d_end = st.date_input("Loppupäivä", key="d_end")
    t_end = st.time_input("Loppuaika", key="t_end", step=60)

# Yhdistetään pvm ja kellonaika datetime-olioksi
start_dt = datetime.combine(d_start, t_start)
end_dt = datetime.combine(d_end, t_end)

# --- FUNKTIOT ---
def fetch_prices(s, e):
    # Haetaan tuntikohtaiset hinnat. API palauttaa tuntikohtaiset hinnat.
    url = f"https://sahkotin.fi/prices?start={s.isoformat()}&end={e.isoformat()}&vat"
    try:
        r = requests.get(url, timeout=10)
        data = r.json()
        df = pd.DataFrame(data["prices"])
        df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None)
        
        # KORJAUS: €/MWh -> snt/kWh (jaetaan 10:llä). API palauttaa verollisen hinnan.
        df["snt_per_kwh"] = df["value"] / 10
        df["price_eur"] = df["snt_per_kwh"] / 100 
        return df
    except Exception:
        return pd.DataFrame()

# --- LASKENTA JA TULOKSET ---
if st.button("Laske kustannukset ja näytä raportti", type="primary", use_container_width=True):
    if start_dt >= end_dt:
        st.error("❌ Virhe: Alkuajan on oltava ennen loppuaikaa.")
    else:
        with st.spinner("Haetaan hintatietoja ja analysoidaan..."):
            df = fetch_prices(start_dt, end_dt)
            
            if sopimus == "Pörssisähkö" and df.empty:
                st.error("Hintatietoja ei saatu haettua API:sta.")
            else:
                # Rajataan data latausvälille
                mask_calc = (df['date'] >= start_dt.replace(minute=0)) & (df['date'] <= end_dt)
                df_filtered = df.loc[mask_calc].copy()

                # Kiinteät kustannukset ja latausaika
                latausaika_h = (end_dt - start_dt).total_seconds() / 3600
                siirto_cost_eur = kwh * (siirto_snt / 100)
                days = max(latausaika_h / 24, 0.01)
                perus_cost_eur = (perus_snt / 100) * days
                
                # Sähkökustannus
                if sopimus == "Pörssisähkö":
                    if billing_method == "Keskituntihinta":
                        # Tunnin keskiarvo -logiikka
                        avg_spot_eur = df_filtered["price_eur"].mean() if not df_filtered.empty else 0
                        energy_cost_eur = kwh * (avg_spot_eur + (marginaali_snt / 100))
                    else:
                        # Varttitase -logiikka. Simuloitu hinta.
                        # Lasketaan 15 minuutin pätkien määrä latausajalta. Oletetaan kWh jakautuvan tasaisesti ajassa.
                        total_time_h = (end_dt - start_dt).total_seconds() / 3600
                        energy_cost_eur = kwh * (df_filtered["price_eur"].mean() + (marginaali_snt / 100)) # Simuloitu hinta. Oikea logiikka alla, mutta data on tunnin.
                        
                        # Demonstroimaan logiikan rakennetta real-time dataa varten
                        total_kwh_cost = 0
                        current_time = start_dt
                        while current_time < end_dt:
                            next_block_end = (current_time + timedelta(minutes=15)).replace(minute=(current_time.minute // 15 + 1) * 15 % 60, second=0, microsecond=0)
                            if current_time.minute // 15 + 1 == 4:
                                next_block_end = (current_time + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
                            block_end = min(next_block_end, end_dt)
                            block_duration = (block_end - current_time).total_seconds() / 3600 # hours
                            block_energy = kwh * (block_duration / total_time_h)
                            
                            # Simuloitu hinta: haetaan tunnin keskiarvo kyseiselle vartille.
                            # Real-time-ympäristössä tämä hinta tulisi 15 min API:sta.
                            hour_start = current_time.replace(minute=0, second=0, microsecond=0)
                            hourly_price_row = df_filtered[df_filtered['date'] == hour_start]
                            if not hourly_price_row.empty:
                                hourly_avg_snt = hourly_price_row.iloc[0]['snt_per_kwh']
                            else:
                                hourly_avg_snt = 0
                            
                            block_price_snt = hourly_avg_snt + marginaali_snt
                            total_kwh_cost += block_energy * (block_price_snt / 100)
                            
                            current_time = block_end
                        energy_cost_eur = total_kwh_cost # Tämä tulos on simulaation vuoksi sama kuin aiempi kwh * (mean_price + margin). Logiikka on demonstroitu.

                else:
                    # Kiinteä sopimus
                    energy_cost_eur = kwh * (hinta_snt / 100)

                total_eur = energy_cost_eur + siirto_cost_eur + perus_cost_eur

                # --- VISUALISOINTI ---
                st.divider()
                
                # Metric-kortit
                total_avg_cost_per_kWh_snt = (total_eur / kwh) * 100
                m1, m2, m3 = st.columns(3)
                m1.metric("Kokonaiskustannus", f"{total_eur:.2f} €")
                m2.metric("Keskihinta tälle lataukselle (sis. siirto ja perusmaksut)", f"{total_avg_cost_per_kWh_snt:.2f} snt/kWh")
                m3.metric("Latausaika", f"{int(latausaika_h)}h {int((latausaika_h*60)%60)}min")

                # --- PARANNETTU GRAAFI (on_select ja Tunnin keskiarvo -kerros) ---
                if not df_filtered.empty:
                    st.subheader("Hinnan kehitys (snt/kWh)")
                    
                    # Valmistellaan data graafia varten
                    graph_df = df_filtered.copy()
                    total_fixed_costs_per_kwh_snt = marginaali_snt + siirto_snt
                    graph_df["Hourly_Total_Cost_per_kWh_snt"] = graph_df["snt_per_kwh"] + total_fixed_costs_per_kwh_snt
                    graph_df["total_avg_cost_per_kWh_snt"] = total_avg_cost_per_kWh_snt
                    
                    # Luodaan layered chart
                    fig = go.Figure()
                    
                    # Area fill trace
                    fig.add_trace(go.Scatter(
                        x=graph_df["date"],
                        y=graph_df["Hourly_Total_Cost_per_kWh_snt"],
                        fill='tozeroy', # Fill to the x-axis
                        mode='none', # Don't draw line, just fill
                        name='Area',
                        hoverinfo='skip' # Skip hover on area
                    ))
                    
                    # Line and points trace
                    fig.add_trace(go.Scatter(
                        x=graph_df["date"],
                        y=graph_df["Hourly_Total_Cost_per_kWh_snt"],
                        mode='lines+markers', # Line with points
                        marker=dict(size=8, color='blue'), # Stylized markers
                        line=dict(width=2, color='blue'), # Stylized line
                        name='Kustannus',
                        customdata=graph_df["total_avg_cost_per_kWh_snt"].to_frame(), # Tooltip data
                        hovertemplate="Kello: %{x|%H:%M}<br>Kokonaiskustannus (snt/kWh): %{customdata[0]:.2f}<extra></extra>"
                    ))
                    
                    fig.update_layout(
                        title="Hinnan kehitys latauksen aikana",
                        xaxis_title="Aika",
                        yaxis_title="snt/kWh",
                        template="streamlit"
                    )
                    
                    st.plotly_chart(fig, use_container_width=True, select_event=True, key="price_chart")
                    
                    # --- KLIKKAA LISÄTIEDOT -CONTAINER ---
                    # Listen to selection events on the chart
                    if 'price_chart' in st.session_state and st.session_state.price_chart['selection']:
                        selection = st.session_state.price_chart['selection']
                        if 'pointIndex' in selection['points'][0]:
                            # User selected a point
                            selected_point_index = selection['points'][0]['pointIndex']
                            selected_time = pd.to_datetime(selection['points'][0]['x'])
                            
                            # Get correct hour data based on selected time
                            hour_start = selected_time.replace(minute=0)
                            
                            hourly_price_row = df_filtered[df_filtered['date'] == hour_start]
                            if not hourly_price_row.empty:
                                hourly_price_snt = hourly_price_row.iloc[0]['snt_per_kwh']
                                
                                # Stylized detail container as image 2. Distinct background.
                                with st.container():
                                    st.markdown(f"### Tuntitietojen yksityiskohdat ({hour_start.strftime('%H:%M')})", unsafe_allow_html=True)
                                    with st.markdown("<div style='background-color: #262730; padding: 20px; border-radius: 10px; border: 1px solid #4B4B4B;'>", unsafe_allow_html=True):
                                        
                                        st.write(f"**Tunnin keskihinta:** {hourly_price_snt:.2f} snt/kWh")
                                        
                                        st.write("**Varttihinnat (Simuloitu):**")
                                        for i in range(4):
                                            st.write(f"{hour_start.replace(minute=i*15).strftime('%H:%M')} &nbsp;&nbsp;&nbsp; {hourly_price_snt:.2f} snt/kWh")
                                        
                                        st.write("*Note: Varttihinnat ovat simuloituja, koska julkinen API tarjoaa tällä hetkellä vain tunnin keskiarvoja.*")
                                        
                                    st.markdown("</div>", unsafe_allow_html=True)

                st.subheader("Kustannusten erittely")
                breakdown = pd.DataFrame({
                    "Kohde": ["🔌 Energia", "⛟ Siirto", "🗓️ Perusmaksut"],
                    "Hinta (€)": [f"{energy_cost_eur:.2f} €", f"{siirto_cost_eur:.2f} €", f"{perus_cost_eur:.2f} €"]
                })
                st.table(breakdown)

                # --- RAPORTTI ---
                report_dict = {
                    "Kuvaus": ["Lataustapahtuma"],
                    "Alku": [start_dt.strftime("%d.%m.%Y %H:%M")],
                    "Loppu": [end_dt.strftime("%d.%m.%Y %H:%M")],
                    "Määrä (kWh)": [kwh],
                    "Energia (€)": [round(energy_cost_eur, 2)],
                    "Siirto (€)": [round(siirto_cost_eur, 2)],
                    "Perusmaksu (€)": [round(perus_cost_eur, 2)],
                    "Yhteensä (€)": [round(total_eur, 2)],
                    "Keskihinta (snt/kWh)": [round((total_eur/kwh)*100, 2)]
                }
                df_report = pd.DataFrame(report_dict)
                
                st.download_button(
                    label="📥 Lataa raportti (CSV)",
                    data=df_report.to_csv(index=False, sep=";", encoding="utf-8-sig"),
                    file_name=f"lataus_{start_dt.strftime('%d%m%Y')}.csv",
                    mime="text/csv",
                    use_container_width=True
                )
