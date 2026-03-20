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
    sizes = [data['Sahko (EUR)'], data['Siirto (EUR)'], data['Perus (EUR)']]
    colors = ['#0066cc', '#3399ff', '#99ccff']
    
    plt.figure(figsize=(4, 4))
    plt.pie(sizes, labels=labels, autopct='%1.1f%%', startangle=140, colors=colors)
    plt.axis('equal')
    
    img_buf = io.BytesIO()
    plt.savefig(img_buf, format='png', bbox_inches='tight', transparent=True)
    img_buf.seek(0)
    plt.close()
    
    pdf.image(img_buf, x=55, y=pdf.get_y() + 10, w=100)
    
    # KORJAUS: Muutetaan bytearray -> bytes
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
    hinta_snt = st.number_input("Sähkön hinta snt/kWh", value=10.0) if sopimus == "Kiinteä" else 0.0
    marginaali_snt = st.number_input("Marginaali snt/kWh", value=0.0) if sopimus == "Pörssisähkö" else 0.0
    siirto_snt = st.number_input("Siirtohinta snt/kWh", value=5.75)
    perus_snt = st.number_input("Perusmaksu snt/päivä", value=17.0)
    kwh_input = st.number_input("Ladattu määrä (kWh)", value=20.0)

st.subheader("Latausajankohta")
col1, col2 = st.columns(2)
with col1:
    d_start = st.date_input("Alkupäivä", key="d_start")
    t_start = st.time_input("Alkuaika", key="t_start", step=60)
with col2:
    d_end = st.date_input("Loppupäivä", key="d_end")
    t_end = st.time_input("Loppuaika", key="t_end", step=60)

start_dt = datetime.combine(d_start, t_start)
end_dt = datetime.combine(d_end, t_end)

if st.button("Laske kustannukset ja luo kuitti", type="primary", use_container_width=True):
    if start_dt >= end_dt:
        st.error("Alkuajan on oltava ennen loppuaikaa!")
    else:
        df = fetch_prices(start_dt, end_dt)
        if df.empty and sopimus == "Pörssisähkö":
            st.error("Datan haku epäonnistui.")
        else:
            # Laskenta
            latausaika_h = (end_dt - start_dt).total_seconds() / 3600
            siirto_eur = kwh_input * (siirto_snt / 100)
            perus_eur = (perus_snt / 100) * (latausaika_h / 24)
            
            if sopimus == "Pörssisähkö":
                mask = (df['date'] >= start_dt - timedelta(minutes=14)) & (df['date'] <= end_dt)
                df_filtered = df.loc[mask].copy()
                avg_spot = df_filtered["price_eur"].mean() if not df_filtered.empty else 0
                energy_eur = kwh_input * (avg_spot + (marginaali_snt / 100))
            else:
                energy_eur = kwh_input * (hinta_snt / 100)
                df_filtered = pd.DataFrame()

            total_eur = energy_eur + siirto_eur + perus_eur
            
            # Tallennus
            kuitti_data = {
                "Pvm": start_dt.strftime("%d.%m.%Y"),
                "Alku": start_dt.strftime("%H:%M"),
                "Loppu": end_dt.strftime("%H:%M"),
                "kWh": kwh_input,
                "Sahko (EUR)": energy_eur,
                "Siirto (EUR)": siirto_eur,
                "Perus (EUR)": perus_eur,
                "Yhteensa (EUR)": total_eur,
                "snt/kWh": (total_eur/kwh_input)*100
            }
            st.session_state.history.append(kuitti_data)
            
            # Tulokset
            st.divider()
            m1, m2, m3 = st.columns(3)
            m1.metric("Yhteensä", f"{total_eur:.2f} €")
            m2.metric("Keskihinta", f"{(total_eur/kwh_input)*100:.2f} snt/kWh")
            m3.metric("Kesto", f"{int(latausaika_h)}h {int((latausaika_h*60)%60)}min")

            # Graafi
            if not df_filtered.empty:
                graph_df = df_filtered.copy()
                graph_df["Total_snt"] = graph_df["snt_per_kwh"] + marginaali_snt + siirto_snt
                fig = go.Figure()
                fig.add_trace(go.Scatter(x=graph_df["date"], y=graph_df["Total_snt"], fill='tozeroy', mode='lines+markers', line=dict(color='#0066cc')))
                fig.update_layout(title="Hinnan kehitys (snt/kWh)", template="plotly_dark")
                st.plotly_chart(fig, use_container_width=True)

            # PDF Nappi
            pdf_file = create_pdf(kuitti_data)
            st.download_button(
                label="📄 Lataa PDF-kuitti",
                data=pdf_file,
                file_name=f"kuitti_{start_dt.strftime('%d%m%Y')}.pdf",
                mime="application/pdf",
                use_container_width=True
            )

# --- HISTORIA ---
if st.session_state.history:
    st.divider()
    st.subheader("📜 Historia")
    st.dataframe(pd.DataFrame(st.session_state.history), use_container_width=True)
    
