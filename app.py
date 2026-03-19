import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timedelta

st.set_page_config(page_title="EV Latauskustannus", layout="centered")

st.title("🔋 Sähköauton latauskustannus")

# --- INPUT ---
sopimus = st.selectbox("Sopimus", ["Pörssisähkö", "Kiinteä"])

hinta = 0
if sopimus == "Kiinteä":
    hinta = st.number_input("Hinta €/kWh", value=0.10)

start = st.datetime_input("Alku", datetime.now() - timedelta(hours=2))
end = st.datetime_input("Loppu", datetime.now())

kwh = st.number_input("kWh", value=20.0)

# --- API ---
def fetch_prices():
    url = f"https://sahkotin.fi/prices?start={start.isoformat()}&end={end.isoformat()}&vat"
    r = requests.get(url)
    data = r.json()

    prices = []
    times = []

    for p in data["prices"]:
        prices.append(p["value"] / 100)
        times.append(p["date"])

    df = pd.DataFrame({
        "time": pd.to_datetime(times),
        "price": prices
    })

    return df

# --- CALC ---
def calc(df):
    df = df[(df["time"] >= start) & (df["time"] <= end)]

    if len(df) == 0:
        return 0

    energy = kwh / len(df)
    total = 0

    for _, r in df.iterrows():
        total += r["price"] * energy

    return total

# --- BUTTON ---
if st.button("Laske"):

    progress = st.progress(0)
    st.write("🔋 Lasketaan...")

    if sopimus == "Pörssisähkö":
        progress.progress(30)
        df = fetch_prices()

        progress.progress(70)
        cost = calc(df)
    else:
        cost = kwh * hinta

    progress.progress(100)

    st.success(f"Kustannus: {cost:.2f} €")

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
