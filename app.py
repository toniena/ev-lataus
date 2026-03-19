import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timedelta

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
st.markdown("Laske latauksen tarkka hinta ja tarkastele hintavaihteluita.")

# --- SIVUPALKKI / SYÖTTEET ---
with st.sidebar:
    st.header("Asetukset")
    sopimus = st.radio("Sähkösopimus", ["Pörssisähkö", "Kiinteä"])
    
    if sopimus == "Kiinteä":
        hinta_snt = st.number_input("Sähkön hinta snt/kWh", value=10.0, step=0.1)
        marginaali_snt = 0
    else:
        hinta_snt = 0
        marginaali_snt = st.number_input("Marginaali snt/kWh", value=0.50, step=0.01)

    siirto_snt = st.number_input("Siirtohinta snt/kWh", value=5.0, step=0.1)
    perus_snt = st.number_input("Perusmaksu snt/päivä", value=20.0, step=1.0)
    kwh = st.number_input("Ladattu määrä (kWh)", value=20.0, step=1.0)

# --- PÄÄNÄKYMÄ: AIKAVALINTA ---
col_a, col_b = st.columns(2)
with col_a:
    d_start = st.date_input("Alkupäivä", key="d_start")
    t_start = st.time_input("Alkuaika", key="t_start", step=60)
with col_b:
    d_end = st.date_input("Loppupäivä", key="d_end")
    t_end = st.time_input("Loppuaika", key="t_end", step=60)

start = datetime.combine(d_start, t_start)
end = datetime.combine(d_end, t_end)

# --- FUNKTIOT ---
def fetch_prices(s, e):
    url = f"https://sahkotin.fi/prices?start={s.isoformat()}&end={e.isoformat()}&vat"
    try:
        r = requests.get(url, timeout=10)
        data = r.json()
        df = pd.DataFrame(data["prices"])
        df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None)
        df["price_eur"] = df["value"] / 100 # snt -> €
        return df
    except:
        return pd.DataFrame()

# --- LASKENTA JA GRAFIIKKA ---
if st.button("Laske ja näytä raportti", type="primary", use_container_width=True):
    if start >= end:
        st.error("Alkuajan on oltava ennen loppuaikaa!")
    else:
        # Pörssisähkön haku
        df = fetch_prices(start, end)
        
        if sopimus == "Pörssisähkö" and df.empty:
            st.error("Hintatietoja ei löytynyt valitulle välille.")
        else:
            # Laskelmat
            if sopimus == "Pörssisähkö":
                # Rajataan data tarkalle minuuttivälille
                mask = (df['date'] >= start) & (df['date'] <= end)
                df_filtered = df.loc[mask].copy()
                
                # Keskiarvo ja sähkön hinta
                avg_spot_eur = df_filtered["price_eur"].mean()
                energy_cost_eur = kwh * (avg_spot_eur + (marginaali_snt / 100))
            else:
                avg_spot_eur = hinta_snt / 100
                energy_cost_eur = kwh * avg_spot_eur

            siirto_cost_eur = kwh * (siirto_snt / 100)
            days = max((end - start).total_seconds() / 86400, 0.01)
            perus_cost_eur = (perus_snt / 100) * days
            total_eur = energy_cost_eur + siirto_cost_eur + perus_cost_eur

            # --- VISUALISOINTI ---
            st.divider()
            
            # Metric-kortit
            m1, m2, m3 = st.columns(3)
            m1.metric("Kokonaiskustannus", f"{total_eur:.2f} €")
            m2.metric("Keskihinta (sis. siirto)", f"{(total_eur/kwh)*100:.2f} snt/kWh")
            m3.metric("Latausaika", f"{int((end-start).total_seconds()/3600)}h {int(((end-start).total_seconds()%3600)/60)}min")

            # Graafi (vain pörssisähkölle järkevä)
            if sopimus == "Pörssisähkö":
                st.subheader("Sähkön hintakehitys latauksen aikana")
                chart_data = df_filtered.rename(columns={"date": "Aika", "price_eur": "Hinta (€/kWh)"})
                st.area_chart(chart_data, x="Aika", y="Hinta (€/kWh)")

            # Kustannuserittely taulukkona
            st.subheader("Kustannuserittely")
            breakdown = pd.DataFrame({
                "Erä": ["Energia", "Siirto", "Perusmaksut"],
                "Hinta (€)": [round(energy_cost_eur, 2), round(siirto_cost_eur, 2), round(perus_cost_eur, 2)]
            })
            st.table(breakdown)

            # --- "HIENOMPI" RAPORTTI ---
            report_data = {
                "Tapahtuma": "Sähköauton lataus",
                "Alku": start.strftime("%d.%m.%Y %H:%M"),
                "Loppu": end.strftime("%d.%m.%Y %H:%M"),
                "Määrä (kWh)": kwh,
                "Energia (€)": round(energy_cost_eur, 2),
                "Siirto (€)": round(siirto_cost_eur, 2),
                "Perusmaksu (€)": round(perus_cost_eur, 2),
                "Yhteensä (€)": round(total_eur, 2),
                "Keskihinta (snt/kWh)": round((total_eur/kwh)*100, 2)
            }
            
            df_report = pd.DataFrame([report_data])
            
            st.download_button(
                label="📥 Lataa yksityiskohtainen raportti (CSV)",
                data=df_report.to_csv(index=False, sep=";", encoding="utf-8-sig"),
                file_name=f"latausraportti_{start.strftime('%d%m%y')}.csv",
                mime="text/csv"
            )import streamlit as st
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
