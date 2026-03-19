import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timedelta

st.set_page_config(page_title="EV Latauskustannus", layout="centered")

st.title("🔋 Sähköauton latauskustannus")

# --- INPUT ---
sopimus = st.selectbox("Sopimus", ["Pörssisähkö", "Kiinteä"])

# Kiinteä hinta (snt/kWh)
hinta_snt = 0
if sopimus == "Kiinteä":
    hinta_snt = st.number_input("Sähkön hinta snt/kWh", value=10.0)

# Pörssisähkö marginaali (snt/kWh)
marginaali_snt = 0
if sopimus == "Pörssisähkö":
    marginaali_snt = st.number_input("Marginaali snt/kWh", value=0.50)

# Siirto (snt/kWh)
siirto_snt = st.number_input("Siirtohinta snt/kWh", value=5.0)

# Perusmaksu (snt/päivä)
perusmaksu_snt = st.number_input("Perusmaksu snt/päivä", value=20.0)

start = st.datetime_input("Alku", datetime.now() - timedelta(hours=2))
end = st.datetime_input("Loppu", datetime.now())

kwh = st.number_input("kWh", value=20.0)

# 🔧 timezone fix
start = start.replace(tzinfo=None)
end = end.replace(tzinfo=None)


# --- API ---
def fetch_prices():
    # Sahkotin API palauttaa hinnat sentteinä, muunnetaan ne tässä euroiksi sisäistä käsittelyä varten
    url = f"https://sahkotin.fi/prices?start={start.isoformat()}&end={end.isoformat()}&vat"
    
    r = requests.get(url)
    data = r.json()

    prices = []
    times = []

    for p in data["prices"]:
        prices.append(p["value"] / 100)  # snt -> €
        times.append(p["date"])

    df = pd.DataFrame({
        "time": pd.to_datetime(times).tz_localize(None),
        "price": prices
    })

    return df

def calc(df):
    df = df[(df["time"] >= start) & (df["time"] <= end)]

    if len(df) == 0:
        return 0

    energy = kwh / len(df)
    total_energy_cost = 0
    
    # Muunnetaan marginaali euroiksi laskentaan
    marginaali_eur = marginaali_snt / 100

    for _, r in df.iterrows():
        # r["price"] on jo euroina fetch_prices-funktiosta
        total_energy_cost += (r["price"] + marginaali_eur) * energy

    # Siirto euroina
    siirto_cost = (siirto_snt / 100) * kwh

    # Perusmaksu euroina suhteessa aikaan
    days = (end - start).total_seconds() / 86400
    perus_cost = (perusmaksu_snt / 100) * days

    total = total_energy_cost + siirto_cost + perus_cost

    return total

# --- BUTTON ---
if st.button("Laske"):

    progress = st.progress(0)
    st.write("🔋 Lasketaan...")

    if sopimus == "Pörssisähkö":
        try:
            progress.progress(30)
            df = fetch_prices()

            progress.progress(70)
            cost = calc(df)
        except Exception as e:
            st.error(f"Hintadatan haku epäonnistui: {e}")
            st.stop()

    else:
        # Kiinteän hinnan laskenta euroina
        energy_cost = kwh * (hinta_snt / 100)
        siirto_cost = kwh * (siirto_snt / 100)

        days = (end - start).total_seconds() / 86400
        perus_cost = (perusmaksu_snt / 100) * days

        cost = energy_cost + siirto_cost + perus_cost

    progress.progress(100)

    st.success(f"Kustannus yhteensä: {cost:.2f} €")

    # --- CSV ---
    df_out = pd.DataFrame({
        "alku": [start],
        "loppu": [end],
        "kwh": [kwh],
        "yhteensa_eur": [round(cost, 2)]
    })

    st.download_button(
        "Lataa CSV",
        df_out.to_csv(index=False),
        "lataus.csv"
    )
