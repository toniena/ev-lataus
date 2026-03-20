import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timedelta

# Sivun asetukset
st.set_page_config(page_title="EV Latauslaskuri Pro", layout="wide")

# --- ALUSTUS (Session State) ---
if 'init_done' not in st.session_state:
    now = datetime.now()
    st.session_state.d_start = now.date()
    st.session_state.t_start = (now - timedelta(hours=2)).time()
    st.session_state.d_end = now.date()
    st.session_state.t_end = now.time()
    st.session_state.init_done = True

st.title("🔋 Sähköauton latauskustannus")
st.markdown("Analysoi latauksen hinta ja tarkista pörssisähkön tuntihinnat.")

# --- SIVUPALKKI: ASETUKSET ---
with st.sidebar:
    st.header("Sopimustiedot")
    sopimus = st.radio("Valitse sopimustyyppi", ["Pörssisähkö", "Kiinteä"])
    
    if sopimus == "Kiinteä":
        hinta_snt = st.number_input("Sähkön hinta snt/kWh", value=10.0, step=0.1)
        marginaali_snt = 0.0
    else:
        hinta_snt = 0.0
        # OLETUS: 0.0
        marginaali_snt = st.number_input("Marginaali snt/kWh", value=0.0, step=0.01)

    st.divider()
    # OLETUS: 5.75
    siirto_snt = st.number_input("Siirtohinta snt/kWh", value=5.75, step=0.01)
    # OLETUS: 17.00
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
        
        # KORJAUS: €/MWh -> snt/kWh (jaetaan 10:llä)
        df["snt_per_kwh"] = df["value"] / 10
        df["price_eur"] = df["snt_per_kwh"] / 100 
        return df
    except Exception:
        return pd.DataFrame()

# --- LASKENTA ---
if st.button("Laske kustannukset ja hae pörssihinnat", type="primary", use_container_width=True):
    if start_dt >= end_dt:
        st.error("❌ Virhe: Alkuajan on oltava ennen loppuaikaa.")
    else:
        with st.spinner("Haetaan tuntihintoja..."):
            df = fetch_prices(start_dt, end_dt)
            
            if sopimus == "Pörssisähkö" and df.empty:
                st.error("Hintatietoja ei saatu haettua.")
            else:
                # Rajataan data latausvälille
                mask_calc = (df['date'] >= start_dt.replace(minute=0)) & (df['date'] <= end_dt)
                df_filtered = df.loc[mask_calc].copy()

                if sopimus == "Pörssisähkö":
                    avg_spot_eur = df_filtered["price_eur"].mean() if not df_filtered.empty else 0
                    energy_cost_eur = kwh * (avg_spot_eur + (marginaali_snt / 100))
                else:
                    avg_spot_eur = hinta_snt / 100
                    energy_cost_eur = kwh * avg_spot_eur

                siirto_cost_eur = kwh * (siirto_snt / 100)
                latausaika_h = (end_dt - start_dt).total_seconds() / 3600
                days = max(latausaika_h / 24, 0.01)
                perus_cost_eur = (perus_snt / 100) * days
                
                total_eur = energy_cost_eur + siirto_cost_eur + perus_cost_eur

                # --- VISUALISOINTI ---
                st.divider()
                
                m1, m2, m3 = st.columns(3)
                m1.metric("Yhteensä (€)", f"{total_eur:.2f} €")
                m2.metric("Keskihinta (sis. siirto)", f"{(total_eur/kwh)*100:.2f} snt/kWh")
                m3.metric("Kesto", f"{int(latausaika_h)}h {int((latausaika_h*60)%60)}min")

                if not df_filtered.empty:
                    st.subheader("Pörssisähkön tuntihinnat (snt/kWh)")
                    chart_df = df_filtered.rename(columns={"date": "Aika", "snt_per_kwh": "snt/kWh"})
                    st.line_chart(chart_df, x="Aika", y="snt/kWh")
                    
                    with st.expander("Tarkista tuntihinnat"):
                        st.dataframe(chart_df[["Aika", "snt/kWh"]].sort_values("Aika"), hide_index=True)

                st.subheader("Kustannusten erittely")
                breakdown = pd.DataFrame({
                    "Kohde": ["🔌 Energia", "⛟ Siirto", "🗓️ Perusmaksut"],
                    "Hinta (€)": [f"{energy_cost_eur:.2f} €", f"{siirto_cost_eur:.2f} €", f"{perus_cost_eur:.2f} €"]
                })
                st.table(breakdown)

                # --- RAPORTTI ---
                report_dict = {
                    "Alku": [start_dt.strftime("%d.%m.%Y %H:%M")],
                    "Loppu": [end_dt.strftime("%d.%m.%Y %H:%M")],
                    "Määrä (kWh)": [kwh],
                    "Energia (€)": [round(energy_cost_eur, 2)],
                    "Siirto (€)": [round(siirto_cost_eur, 2)],
                    "Perus (€)": [round(perus_cost_eur, 2)],
                    "Yhteensä (€)": [round(total_eur, 2)],
                    "Keskihinta (snt/kWh)": [round((total_eur/kwh)*100, 2)]
                }
                st.download_button(
                    label="📥 Lataa raportti (CSV)",
                    data=pd.DataFrame(report_dict).to_csv(index=False, sep=";", encoding="utf-8-sig"),
                    file_name=f"lataus_{start_dt.strftime('%d%m%Y')}.csv",
                    mime="text/csv",
                    use_container_width=True
                )
                
