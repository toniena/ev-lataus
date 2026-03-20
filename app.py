import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timedelta
import plotly.graph_objects as go

# Sivun asetukset
st.set_page_config(page_title="EV Latauslaskuri Pro", layout="wide")

# --- ALUSTUS (Session State) ---
if 'history' not in st.session_state:
    st.session_state.history = []

if 'init_done' not in st.session_state:
    now = datetime.now()
    st.session_state.d_start = now.date()
    st.session_state.t_start = (now - timedelta(hours=2)).time()
    st.session_state.d_end = now.date()
    st.session_state.t_end = now.time()
    st.session_state.billing_method = "Keskituntihinta"
    st.session_state.init_done = True

st.title("🔋 Sähköauton latauskustannus")
st.markdown("Analysoi latauksen hinta, tarkista pörssisähkön tuntihinnat ja seuraa historiaa.")

# --- SIVUPALKKI: ASETUKSET ---
with st.sidebar:
    st.header("Asetukset")
    
    sopimus = st.radio("Sähkösopimus", ["Pörssisähkö", "Kiinteä"])
    if sopimus == "Kiinteä":
        hinta_snt = st.number_input("Sähkön hinta snt/kWh", value=10.0, step=0.1)
        marginaali_snt = 0.0
    else:
        hinta_snt = 0.0
        marginaali_snt = st.number_input("Marginaali snt/kWh", value=0.0, step=0.01)

    st.divider()
    
    st.subheader("Laskutustapa")
    billing_method = st.radio("Valitse menetelmä", ["Keskituntihinta", "Varttitase (15 min)"], key="billing_method")
    
    st.divider()
    
    siirto_snt = st.number_input("Siirtohinta snt/kWh", value=5.75, step=0.01)
    perus_snt = st.number_input("Perusmaksu snt/päivä", value=17.0, step=1.0)
    kwh_input = st.number_input("Ladattu määrä (kWh)", value=20.0, step=0.5)

# --- PÄÄNÄKYMÄ: AIKAVALINTA ---
st.subheader("Latausajankohta")
col_a, col_b = st.columns(2)
with col_a:
    d_start = st.date_input("Alkupäivä", key="d_start")
    t_start = st.time_input("Alkuaika", key="t_start", step=60)
with col_b:
    d_end = st.date_input("Loppupäivä", key="d_end")
    t_end = st.time_input("Loppuaika", key="t_end", step=60)

start_dt = datetime.combine(d_start, t_start)
end_dt = datetime.combine(d_end, t_end)

# --- FUNKTIOT ---
def fetch_prices(s, e):
    url = f"https://sahkotin.fi/prices?start={s.isoformat()}&end={e.isoformat()}&vat"
    try:
        r = requests.get(url, timeout=10)
        data = r.json()
        df = pd.DataFrame(data["prices"])
        df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None)
        df["snt_per_kwh"] = df["value"] / 10 # €/MWh -> snt/kWh
        df["price_eur"] = df["snt_per_kwh"] / 100 
        return df
    except Exception:
        return pd.DataFrame()

# --- LASKENTA ---
if st.button("Laske kustannukset ja tallenna historiaan", type="primary", use_container_width=True):
    if start_dt >= end_dt:
        st.error("❌ Virhe: Alkuajan on oltava ennen loppuaikaa.")
    else:
        with st.spinner("Lasketaan..."):
            df = fetch_prices(start_dt, end_dt)
            
            if sopimus == "Pörssisähkö" and df.empty:
                st.error("Hintatietoja ei saatu haettua.")
            else:
                # Rajataan data latausvälille
                mask_calc = (df['date'] >= start_dt.replace(minute=0)) & (df['date'] <= end_dt)
                df_filtered = df.loc[mask_calc].copy()

                latausaika_h = (end_dt - start_dt).total_seconds() / 3600
                siirto_cost_eur = kwh_input * (siirto_snt / 100)
                days = max(latausaika_h / 24, 0.01)
                perus_cost_eur = (perus_snt / 100) * days
                
                if sopimus == "Pörssisähkö":
                    # Laskenta (tunnin keskiarvoon pohjautuva simulaatio)
                    avg_spot_eur = df_filtered["price_eur"].mean() if not df_filtered.empty else 0
                    energy_cost_eur = kwh_input * (avg_spot_eur + (marginaali_snt / 100))
                else:
                    energy_cost_eur = kwh_input * (hinta_snt / 100)

                total_eur = energy_cost_eur + siirto_cost_eur + perus_cost_eur
                avg_total_snt = (total_eur / kwh_input) * 100

                # TALLENNUS HISTORIAAN
                st.session_state.history.append({
                    "Pvm": start_dt.strftime("%d.%m.%Y"),
                    "Alku": start_dt.strftime("%H:%M"),
                    "Loppu": end_dt.strftime("%H:%M"),
                    "kWh": kwh_input,
                    "Sähkö (€)": round(energy_cost_eur, 2),
                    "Siirto (€)": round(siirto_cost_eur, 2),
                    "Yhteensä (€)": round(total_eur, 2),
                    "snt/kWh": round(avg_total_snt, 2)
                })

                # --- VISUALISOINTI ---
                st.divider()
                m1, m2, m3 = st.columns(3)
                m1.metric("Yhteensä (€)", f"{total_eur:.2f} €")
                m2.metric("Keskihinta (sis. siirto)", f"{avg_total_snt:.2f} snt/kWh")
                m3.metric("Kesto", f"{int(latausaika_h)}h {int((latausaika_h*60)%60)}min")

                if not df_filtered.empty:
                    st.subheader("Kustannusrakenne latauksen aikana (snt/kWh)")
                    graph_df = df_filtered.copy()
                    # Lasketaan tuntikohtainen snt/kWh (Spot + Marginaali + Siirto)
                    graph_df["Total_snt"] = graph_df["snt_per_kwh"] + marginaali_snt + siirto_snt
                    
                    fig = go.Figure()
                    fig.add_trace(go.Scatter(
                        x=graph_df["date"], y=graph_df["Total_snt"],
                        fill='tozeroy', mode='lines+markers',
                        line=dict(color='#FF4B4B', width=3),
                        marker=dict(size=8),
                        name="Kokonaiskustannus",
                        hovertemplate="Aika: %{x|%H:%M}<br>Hinta: %{y:.2f} snt/kWh<extra></extra>"
                    ))
                    fig.update_layout(xaxis_title="Kellonaika", yaxis_title="snt/kWh", template="plotly_dark", hovermode="x unified")
                    
                    # Interaktiivinen klikkaus (vaatii Streamlit 1.35+)
                    event = st.plotly_chart(fig, use_container_width=True, on_select="rerun", key="chart")
                    
                    if event and event.selection and event.selection.points:
                        pt = event.selection.points[0]
                        sel_time = pd.to_datetime(pt['x'])
                        hour_data = graph_df[graph_df['date'] == sel_time.replace(minute=0)]
                        if not hour_data.empty:
                            row = hour_data.iloc[0]
                            with st.container(border=True):
                                st.markdown(f"#### 🔍 Tiedot klo {row['date'].strftime('%H:00')}")
                                c1, c2 = st.columns(2)
                                c1.write(f"**Tunnin pörssihinta:** {row['snt_per_kwh']:.3f} snt/kWh")
                                c1.write(f"**Varttihinnat (keskiarvo):**")
                                for m in [0, 15, 30, 45]:
                                    st.write(f"- {row['date'].replace(minute=m).strftime('%H:%M')}: {row['snt_per_kwh']:.3f} snt")
                                c2.metric("Tunnin kokonaishinta", f"{row['Total_snt']:.2f} snt")
                                st.caption("Varttihinnat perustuvat tunnin keskiarvoon.")

# --- HISTORIA-OSIO ---
st.divider()
st.header("📜 Lataushistoria")

if st.session_state.history:
    hist_df = pd.DataFrame(st.session_state.history)
    
    # Näytetään yhteenveto historiasta
    h_col1, h_col2, h_col3 = st.columns(3)
    h_col1.metric("Latauskertoja", len(hist_df))
    h_col2.metric("Ladattu yhteensä", f"{hist_df['kWh'].sum():.1f} kWh")
    h_col3.metric("Kulut yhteensä", f"{hist_df['Yhteensä (€)'].sum():.2f} €")

    st.dataframe(hist_df, use_container_width=True, hide_index=True)
    
    col_h1, col_h2 = st.columns(2)
    with col_h1:
        st.download_button(
            "📥 Lataa koko historia (CSV)",
            hist_df.to_csv(index=False, sep=";", encoding="utf-8-sig"),
            "lataushistoria.csv",
            mime="text/csv",
            use_container_width=True
        )
    with col_h2:
        if st.button("🗑️ Tyhjennä historia", use_container_width=True):
            st.session_state.history = []
            st.rerun()
else:
    st.info("Ei vielä tallennettuja latauksia. Laske kustannus tallentaaksesi tiedot historiaan.")
    
