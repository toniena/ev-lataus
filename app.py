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

# --- ALUSTUS (Session State) ---
if 'history' not in st.session_state:
    st.session_state.history = []

if 'init_done' not in st.session_state:
    now = datetime.now()
    st.session_state.d_start = now.date()
    st.session_state.t_start = (now - timedelta(hours=2)).time()
    st.session_state.d_end = now.date()
    st.session_state.t_end = now.time()
    st.session_state.init_done = True

# --- PDF GENEROINTI -FUNKTIO ---
def create_pdf(data):
    pdf = FPDF()
    pdf.add_page()
    
    # Otsikko
    pdf.set_font("helvetica", "B", 24)
    pdf.set_text_color(0, 102, 204)
    pdf.cell(0, 20, "LATAUSKUITTI", ln=True, align="C")
    
    pdf.set_font("helvetica", "", 12)
    pdf.set_text_color(0, 0, 0)
    pdf.ln(10)
    
    # Perustiedot taulukkona
    pdf.set_fill_color(245, 245, 245)
    pdf.set_font("helvetica", "B", 12)
    pdf.cell(95, 10, " Lataustapahtuma", border=1, fill=True)
    pdf.cell(95, 10, f" Pvm: {data['Pvm']}", border=1, ln=True, fill=True)
    
    pdf.set_font("helvetica", "", 12)
    pdf.cell(95, 10, f" Alku: {data['Alku']}", border=1)
    pdf.cell(95, 10, f" Loppu: {data['Loppu']}", border=1, ln=True)
    pdf.cell(95, 10, f" Ladattu määrä:", border=1)
    pdf.cell(95, 10, f" {data['kWh']} kWh", border=1, ln=True)
    pdf.ln(15)
    
    # Kustannuserittely
    pdf.set_font("helvetica", "B", 14)
    pdf.cell(0, 10, "Kustannuserittely", ln=True)
    pdf.set_draw_color(0, 102, 204)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(5)
    
    pdf.set_font("helvetica", "", 12)
    pdf.cell(100, 10, "Sahkoenergia (sis. marginaali):")
    pdf.cell(0, 10, f"{data['Sahko (EUR)']:.2f} EUR", ln=True, align="R")
    
    pdf.cell(100, 10, "Siirtomaksu:")
    pdf.cell(0, 10, f"{data['Siirto (EUR)']:.2f} EUR", ln=True, align="R")
    
    pdf.cell(100, 10, "Perusmaksut:")
    pdf.cell(0, 10, f"{data['Perus (EUR)']:.2f} EUR", ln=True, align="R")
    
    pdf.ln(5)
    pdf.set_font("helvetica", "B", 16)
    pdf.cell(100, 15, "YHTEENSA:")
    pdf.cell(0, 15, f"{data['Yhteensa (EUR)']:.2f} EUR", ln=True, align="R")
    
    # Piirakkakaavio
    labels = ['Energia', 'Siirto', 'Perus']
    sizes = [max(data['Sahko (EUR)'], 0.01), max(data['Siirto (EUR)'], 0.01), max(data['Perus (EUR)'], 0.01)]
    colors = ['#0066cc', '#3399ff', '#99ccff']
    
    plt.figure(figsize=(4, 4))
    plt.pie(sizes, labels=labels, autopct='%1.1f%%', startangle=140, colors=colors)
    plt.axis('equal')
    
    img_buf = io.BytesIO()
    plt.savefig(img_buf, format='png', bbox_inches='tight', transparent=True)
    img_buf.seek(0)
    plt.close()
    
    pdf.image(img_buf, x=55, y=pdf.get_y() + 10, w=100)
    
    return bytes(pdf.output())

# --- FUNKTIOT ---
def fetch_prices(s, e):
    url = f"https://sahkotin.fi/prices?start={s.isoformat()}&end={e.isoformat()}&vat"
    try:
        r = requests.get(url, timeout=10)
        data = r.json()
        df = pd.DataFrame(data["prices"])
        df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None)
        df["snt_per_kwh"] = df["value"] / 10 
        df["price_eur"] = df["snt_per_kwh"] / 100 
        return df
    except:
        return pd.DataFrame()

# --- UI ---
st.title("🔋 Sähköauton latauskustannus")

with st.sidebar:
    st.header("Asetukset")
    sopimus = st.radio("Sähkösopimus", ["Pörssisähkö", "Kiinteä"])
    if sopimus == "Kiinteä":
        hinta_snt = st.number_input("Sähkön hinta snt/kWh", value=10.0, step=0.1)
        marginaali_snt = 0.0
