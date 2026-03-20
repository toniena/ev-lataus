import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timedelta
import plotly.graph_objects as go
import matplotlib.pyplot as plt
from fpdf import FPDF
import io

# Sivun asetukset
st.set_page_config(page_title="EV Latauslaskuri Pro", layout="wide")

# --- ALUSTUS ---
if 'history' not in st.session_state:
    st.session_state.history = []

# --- PDF GENEROINTI -FUNKTIO ---
def create_pdf(data):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("helvetica", "B", 20)
    
    # Otsikko
    pdf.cell(0, 20, "LATAUSKUITTI", ln=True, align="C")
    pdf.set_font("helvetica", "", 12)
    pdf.ln(10)
    
    # Tiedot
    pdf.set_fill_color(240, 240, 240)
    pdf.cell(95, 10, f"Pvm: {data['Pvm']}", border=1, fill=True)
    pdf.cell(95, 10, f"Ladattu määrä: {data['kWh']} kWh", border=1, ln=True, fill=True)
    pdf.cell(95, 10, f"Alku: {data['Alku']}", border=1)
    pdf.cell(95, 10, f"Loppu: {data['Loppu']}", border=1, ln=True)
    pdf.ln(10)
    
    # Kustannuserittely
    pdf.set_font("helvetica", "B", 14)
    pdf.cell(0, 10, "Kustannuserittely", ln=True)
    pdf.set_font("helvetica", "", 12)
    
    pdf.cell(100, 10, "Sahkoenergia (sis. marginaali):")
    pdf.cell(0, 10, f"{data['Sahko (EUR)']:.2f} EUR", ln=True, align="R")
    
    pdf.cell(100, 10, "Siirtomaksu:")
    pdf.cell(0, 10, f"{data['Siirto (EUR)']:.2f} EUR", ln=True, align="R")
    
    pdf.cell(100, 10, "Perusmaksut:")
    pdf.cell(0, 10, f"{data['Perus (EUR)']:.2f} EUR", ln=True, align="R")
    
    pdf.set_draw_color(0, 0, 0)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    
    pdf.set_font("helvetica", "B", 14)
    pdf.cell(100, 15, "YHTEENSA:")
    pdf.cell(0, 15, f"{data['Yhteensa (EUR)']:.2f} EUR", ln=True, align="R")
    pdf.ln(5)
    
    # Grafiikka: Tehdään piirakkakaavio
    labels = ['Energia', 'Siirto', 'Perus']
    sizes = [data['Sahko (EUR)'], data['Siirto (EUR)'], data['Perus (EUR)']]
    colors = ['#ff9999','#66b3ff','#99ff99']
    
    fig, ax = plt.subplots(figsize=(4, 4))
    ax.pie(sizes, labels=labels, autopct='%1.1f%%', startangle=140, colors=colors)
    ax.axis('equal')
    
    # Tallennetaan kuva puskuriin
    img_buf = io.BytesIO()
    plt.savefig(img_buf, format='png', bbox_inches='tight')
    img_buf.seek(0)
    plt.close(fig)
    
    # Lisätään kuva PDF:ään
    pdf.image(img_buf, x=55, y=pdf.get_y(), w=100)
    
    return pdf.output()

# --- SIVUPALKKI JA AIKAVALINTA (Kuten aiemmin) ---
with st.sidebar:
    st.header("Asetukset")
    sopimus = st.radio("Sähkösopimus", ["Pörssisähkö", "Kiinteä"])
    hinta_snt = st.number_input("Sähkön hinta snt/kWh", value=10.0) if sopimus == "Kiinteä" else 0.0
    marginaali_snt = st.number_input("Marginaali snt/kWh", value=0.0) if sopimus == "Pörssisähkö" else 0.0
    siirto_snt = st.number_input("Siirtohinta snt/kWh", value=5.75)
    perus_snt = st.number_input("Perusmaksu snt/päivä", value=17.0)
    kwh_input = st.number_input("Ladattu määrä (kWh)", value=20.0)

st.subheader("Latausajankohta")
col_a, col_b = st.columns(2)
with col_a:
    d_start = st.date_input("Alkupäivä", datetime.now())
    t_start = st.time_input("Alkuaika", (datetime.now() - timedelta(hours=2)).time(), step=60)
with col_b:
    d_end = st.date_input("Loppupäivä", datetime.now())
    t_end = st.time_input("Loppuaika", datetime.now().time(), step=60)

start_dt = datetime.combine(d_start, t_start)
end_dt = datetime.combine(d_end, t_end)

# --- LASKENTA ---
if st.button("Laske ja luo kuitti", type="primary", use_container_width=True):
    # (Tässä välissä on sama fetch_prices ja laskentalogiikka kuin edellisessä viestissä)
    # Simuloidaan tässä nyt lopputuloksia koodin lyhentämiseksi:
    
    # --- API kutsu ja laskenta ---
    url = f"https://sahkotin.fi/prices?start={start_dt.isoformat()}&end={end_dt.isoformat()}&vat"
    r = requests.get(url)
    if r.status_code == 200:
        data_api = r.json()
        prices = [p["value"]/10 for p in data_api["prices"]]
        avg_price = sum(prices)/len(prices) if prices else 0
        
        energy_eur = kwh_input * ((avg_price + marginaali_snt) / 100)
        siirto_eur = kwh_input * (siirto_snt / 100)
        days = max((end_dt - start_dt).total_seconds() / 86400, 0.01)
        perus_eur = (perus_snt / 100) * days
        total_eur = energy_eur + siirto_eur + perus_eur
        
        kuitti_data = {
            "Pvm": start_dt.strftime("%d.%m.%Y"),
            "Alku": start_dt.strftime("%H:%M"),
            "Loppu": end_dt.strftime("%H:%M"),
            "kWh": kwh_input,
            "Sahko (EUR)": energy_eur,
            "Siirto (EUR)": siirto_eur,
            "Perus (EUR)": perus_eur,
            "Yhteensa (EUR)": total_eur
        }
        
        st.session_state.history.append(kuitti_data)
        
        st.success(f"Laskettu! Kokonaishinta: {total_eur:.2f} €")
        
        # --- PDF LATAUSNAPPI ---
        pdf_bytes = create_pdf(kuitti_data)
        st.download_button(
            label="📄 Lataa PDF-kuitti",
            data=pdf_bytes,
            file_name=f"kuitti_{start_dt.strftime('%d%m%Y')}.pdf",
            mime="application/pdf",
            use_container_width=True
        )

# --- HISTORIA (Näytetään kuten aiemmin) ---
if st.session_state.history:
    st.divider()
    st.header("📜 Historia")
    st.write(pd.DataFrame(st.session_state.history))
    
