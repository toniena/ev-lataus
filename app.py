import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timedelta

st.set_page_config(page_title="EV Latauskustannus", layout="centered")

st.title("🔋 Sähköauton latauskustannus")

# --- INPUT ---
sopimus = st.selectbox("Sopimus", ["Pörssisähkö", "Kiinteä"])

# Kiinteä hinta
hinta = 0
if sopimus == "Kiinteä":
    hinta = st.number_input("Sähkön hinta €/kWh", value=0.10)

# Pörssisähkö lisät
marginaali = 0
if sopimus == "Pörssisähkö":
    marginaali = st.number_input("Marginaali €/kWh", value=0.005)

# Siirto
siirto = st.number_input("Siirtohinta €/kWh", value=0.05)

# Perusmaksu (päiväkohtainen)
perusmaksu = st.number_input("Perusmaksu €/päivä", value=0.20)

start = st.datetime_input("Alku", datetime.now() - timedelta(hours=2))
end = st.datetime_input("Loppu", datetime.now())

start = start.replace(tzinfo=None)
end = end.replace(tzinfo=None)

kwh = st.number_input("kWh", value=20.0)
# 🔧 timezone fix
start = start.replace(tzinfo=None)
end = end.replace(tzinfo=None)


# --- API ---
def fetch_prices():
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

    for _, r in df.iterrows():
        total_energy_cost += (r["price"] + marginaali) * energy

    # Siirto
    siirto_cost = siirto * kwh

    # Perusmaksu suhteessa aikaan
    days = (end - start).total_seconds() / 86400
    perus_cost = perusmaksu * days

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
        except:
            st.error("Hintadatan haku epäonnistui")
            st.stop()

    else:
        energy_cost = kwh * hinta
        siirto_cost = siirto * kwh

        days = (end - start).total_seconds() / 86400
        perus_cost = perusmaksu * days

        cost = energy_cost + siirto_cost + perus_cost

    progress.progress(100)

    st.success(f"Kustannus: {cost:.2f} €")

    # --- CSV ---
    df_out = pd.DataFrame({
        "alku": [start],
        "loppu": [end],
        "kwh": [kwh],
        "€": [cost]
    })

    st.download_button(
        "Lataa CSV",
        df_out.to_csv(index=False),
        "lataus.csv"
    )
