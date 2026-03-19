import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timedelta, time

st.set_page_config(page_title="EV Latauskustannus", layout="centered")

# --- ALUSTUS (Session State) ---
# Alustetaan oletusajat vain kerran, jotta ne eivät nollaudu joka välissä
if 'init_done' not in st.session_state:
    now = datetime.now()
    st.session_state.d_start = now.date()
    st.session_state.t_start = (now - timedelta(hours=2)).time()
    st.session_state.d_end = now.date()
    st.session_state.t_end = now.time()
    st.session_state.init_done = True

st.title("🔋 Sähköauton latauskustannus")

# --- INPUT ---
sopimus = st.selectbox("Sopimus", ["Pörssisähkö", "Kiinteä"])

col1, col2 = st.columns(2)
with col1:
    hinta_label = "Sähkön hinta snt/kWh" if sopimus == "Kiinteä" else "Marginaali snt/kWh"
    hinta_val = 10.0 if sopimus == "Kiinteä" else 0.50
    # Käytetään avainta (key), jotta arvo pysyy muistissa
    lisa_hinta_snt = st.number_input(hinta_label, value=hinta_val)

with col2:
    siirto_snt = st.number_input("Siirtohinta snt/kWh", value=5.0)

perus_col1, perus_col2 = st.columns(2)
with perus_col1:
    perusmaksu_snt = st.number_input("Perusmaksu snt/päivä", value=20.0)
with perus_col2:
    kwh = st.number_input("Ladattu määrä (kWh)", value=20.0)

st.divider()

# --- AJANKOHTA (Pysyvä valinta) ---
st.subheader("Valitse aikaväli")
t_col1, t_col2 = st.columns(2)

with t_col1:
    # d_start ja t_start tallentuvat session_stateen automaattisesti 'key'-parametrilla
    d_start = st.date_input("Alkupäivä", key="d_start")
    t_start = st.time_input("Alkuaika", key="t_start", step=60)

with t_col2:
    d_end = st.date_input("Loppupäivä", key="d_end")
    t_end = st.time_input("Loppuaika", key="t_end", step=60)

# Yhdistetään valinnat
start = datetime.combine(d_start, t_start)
end = datetime.combine(d_end, t_end)

# --- API ---
def fetch_prices(start_dt, end_dt):
    url = f"https://sahkotin.fi/prices?start={start_dt.isoformat()}&end={end_dt.isoformat()}&vat"
    try:
        r = requests.get(url, timeout=10)
        data = r.json()
        
        prices = [p["value"] / 100 for p in data["prices"]] # snt -> €
        times = [p["date"] for p in data["prices"]]

        return pd.DataFrame({
            "time": pd.to_datetime(times).tz_localize(None),
            "price": prices
        })
    except:
        return pd.DataFrame()

def calc(df, start_dt, end_dt):
    df_filtered = df[(df["time"] >= start_dt) & (df["time"] <= end_dt)]
    if len(df_filtered) == 0:
        return 0

    energy_per_hour = kwh / len(df_filtered)
    marginaali_eur = (lisa_hinta_snt if sopimus == "Pörssisähkö" else 0) / 100
    
    # Energian hinta
    if sopimus == "Pörssisähkö":
        total_energy_cost = sum((df_filtered["price"] + marginaali_eur) * energy_per_hour)
    else:
        total_energy_cost = kwh * (lisa_hinta_snt / 100)

    # Siirto ja perusmaksu
    siirto_cost = (siirto_snt / 100) * kwh
    days = max((end_dt - start_dt).total_seconds() / 86400, 0.01)
    perus_cost = (perusmaksu_snt / 100) * days

    return total_energy_cost + siirto_cost + perus_cost

# --- BUTTON ---
if st.button("Laske kustannus", type="primary"):
    if start >= end:
        st.error("Alkuajan on oltava ennen loppuaikaa!")
    else:
        with st.spinner("Haetaan hintoja..."):
            if sopimus == "Pörssisähkö":
                df = fetch_prices(start, end)
                if df.empty:
                    st.error("Hintojen haku epäonnistui.")
                    st.stop()
                cost = calc(df, start, end)
            else:
                cost = calc(None, start, end)

        st.success(f"Yhteensä: {cost:.2f} €")
        
        # Lisätietona keskihinta
        st.info(f"Keskihinta tälle lataukselle: {(cost/kwh)*100:.2f} snt/kWh (sis. siirron)")

        # Latauslinkki
        df_csv = pd.DataFrame({"alku": [start], "loppu": [end], "kwh": [kwh], "eur": [round(cost, 2)]})
        st.download_button("Lataa raportti (CSV)", df_csv.to_csv(index=False), "latausraportti.csv")
