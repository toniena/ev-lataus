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
    
    # KORJAUS: Muutetaan bytearray -> bytes mobiiliyhteensopivuutta varten
    return bytes(pdf.output())

# --- FUNKTIOT ---
def fetch_prices(s, e):
    url = f"https://sahkotin.fi/prices?start={s.isoformat()}&end={e.isoformat()}&vat"
    try:
        r = requests.get(url, timeout=10)
        data = r.json()
        df = pd.DataFrame(data["prices"])
        df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None)
        # KORJAUS: €/MWh -> snt/kWh (jaetaan 10:llä). API palauttaa verollisen hinnan.
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
    else:
        hinta_snt = 0.0
        # OLETUS: 0.0
        marginaali_snt = st.number_input("Marginaali snt/kWh", value=0.0, step=0.01)

    st.divider()
    
    # OLETUS: 5.75
    siirto_snt = st.number_input("Siirtohinta snt/kWh", value=5.75, step=0.01)
    # OLETUS: 17.00
    perus_snt = st.number_input("Perusmaksu snt/päivä", value=17.0, step=1.0)
    kwh_input = st.number_input("Ladattu määrä (kWh)", value=20.0, step=0.5)

# --- PÄÄNÄKYMÄ: AIKAVALINTA ---
st.subheader("Latausajankohta")
col1, col2 = st.columns(2)
with col1:
    d_start = st.date_input("Alkupäivä", key="d_start")
    t_start = st.time_input("Alkuaika", key="t_start", step=60)
with col2:
    d_end = st.date_input("Loppupäivä", key="d_end")
    t_end = st.time_input("Loppuaika", key="t_end", step=60)

# Yhdistetään pvm ja kellonaika datetime-olioksi
start_dt = datetime.combine(d_start, t_start)
end_dt = datetime.combine(d_end, t_end)

# --- LASKENTA ---
if st.button("Laske kustannukset", type="primary", use_container_width=True):
    if start_dt >= end_dt:
        st.error("❌ Virhe: Alkuajan on oltava ennen loppuaikaa.")
    else:
        with st.spinner("Haetaan pörssidataa..."):
            df = fetch_prices(start_dt, end_dt)
            
            if sopimus == "Pörssisähkö" and df.empty:
                st.error("Hintatietoja ei saatu haettua API:sta.")
            else:
                # Rajataan data latausvälille
                mask_calc = (df['date'] >= start_dt.replace(minute=0)) & (df['date'] <= end_dt)
                df_filtered = df.loc[mask_calc].copy()

                # Kiinteät kustannukset ja latausaika
                latausaika_h = (end_dt - start_dt).total_seconds() / 3600
                siirto_cost_eur = kwh_input * (siirto_snt / 100)
                days = max(latausaika_h / 24, 0.01)
                perus_cost_eur = (perus_snt / 100) * days
                
                # Sähkökustannus
                if sopimus == "Pörssisähkö":
                    avg_spot_eur = df_filtered["price_eur"].mean() if not df_filtered.empty else 0
                    energy_cost_eur = kwh_input * (avg_spot_eur + (marginaali_snt / 100))
                else:
                    avg_spot_eur = hinta_snt / 100
                    energy_cost_eur = kwh_input * avg_spot_eur

                total_eur = energy_cost_eur + siirto_cost_eur + perus_cost_eur
                total_avg_cost_per_kWh_snt = (total_eur / kwh_input) * 100

                # TALLENNUS HISTORIAAN
                kuitti_data = {
                    "Pvm": start_dt.strftime("%d.%m.%Y"),
                    "Alku": start_dt.strftime("%H:%M"),
                    "Loppu": end_dt.strftime("%H:%M"),
                    "kWh": kwh_input,
                    "Sahko (EUR)": energy_eur,
                    "Siirto (EUR)": siirto_cost_eur,
                    "Perus (EUR)": perus_cost_eur,
                    "Yhteensa (EUR)": total_eur,
                    "snt/kWh": total_avg_cost_per_kWh_snt
                }
                st.session_state.history.append(kuitti_data)
                st.session_state.latest_result = kuitti_data

                # --- VISUALISOINTI ---
                st.divider()
                
                # Metric-kortit
                m1, m2, m3 = st.columns(3)
                m1.metric("Kokonaiskustannus", f"{total_eur:.2f} €")
                m2.metric("Keskihinta (sis. siirto)", f"{total_avg_cost_per_kWh_snt:.2f} snt/kWh")
                m3.metric("Latauksen kesto", f"{int(latausaika_h)}h {int((latausaika_h*60)%60)}min")

                if not df_filtered.empty:
                    st.subheader("Hinnan kehitys (snt/kWh)")
                    
                    graph_df = df_filtered.copy()
                    # Lasketaan tuntikohtainen snt/kWh (Spot + Marginaali + Siirto)
                    graph_df["Total_snt"] = graph_df["snt_per_kwh"] + marginaali_snt + siirto_snt
                    
                    # Lasketaan tunnin keskiarvo kunkin pisteen kohdalle (vaikka olisi 15min dataa)
                    graph_df['hour_group'] = graph_df['date'].dt.floor('H')
                    graph_df['hourly_avg'] = graph_df.groupby('hour_group')['Total_snt'].transform('mean')
                    
                    fig = go.Figure()
                    
                    # Piirretään viiva ja pisteet
                    fig.add_trace(go.Scatter(
                        x=graph_df["date"], 
                        y=graph_df["Total_snt"],
                        fill='tozeroy', 
                        mode='lines+markers',
                        line=dict(color='#00CC96', width=2),
                        marker=dict(size=8, symbol='circle'),
                        name="Kustannus",
                        customdata=graph_df[["hourly_avg"]].values, # Tooltip data
                        hovertemplate=(
                            "<b>Aika:</b> %{x|%H:%M}<br>" +
                            "<b>15 min hinta:</b> %{y:.2f} snt/kWh<br>" +
                            "<b>Tunnin keskihinta:</b> %{customdata[0]:.2f} snt/kWh" +
                            "<extra></extra>"
                        )
                    ))
                    
                    # --- UUSI: LATAUKSEN KESKIHINNAN KATKOVIIVA ---
                    fig.add_shape(type="line",
                                  x0=graph_df["date"].min(), y0=total_avg_cost_per_kWh_snt,
                                  x1=graph_df["date"].max(), y1=total_avg_cost_per_kWh_snt,
                                  line=dict(color="Red", width=3, dash="dash"), # Punainen katkoviiva
                                  name="Latauksen keskihinta"
                    )
                    
                    # Lisätään teksti katkoviivalle
                    fig.add_trace(go.Scatter(
                        x=[graph_df["date"].max()], 
                        y=[total_avg_cost_per_kWh_snt], 
                        text=[f"Latauksen keskihinta: {total_avg_cost_per_kWh_snt:.2f} snt/kWh"], 
                        mode="text", 
                        textposition="top left", 
                        showlegend=False, 
                        hoverinfo='skip'
                    ))
                    
                    fig.update_layout(
                        xaxis_title="Kellonaika", 
                        yaxis_title="snt/kWh", 
                        template="plotly_dark",
                        hovermode="x unified",
                        margin=dict(l=0, r=0, t=40, b=0)
                    )
                    
                    # Näytetään graafi
                    event = st.plotly_chart(fig, use_container_width=True, on_select="rerun", key="chart")
                    
                    # Klikkaus-yksityiskohdat
                    if event and event.selection and event.selection.points:
                        pt = event.selection.points[0]
                        row = graph_df.iloc[pt['pointIndex']]
                        with st.container(border=True):
                            st.markdown(f"#### 🔍 Yksityiskohdat: {row['date'].strftime('%H:%M')}")
                            c1, c2 = st.columns(2)
                            c1.write(f"**Pörssihinta (sis. ALV):** {row['snt_per_kwh']:.3f} snt/kWh")
                            c1.write(f"**Tunnin keskiarvo:** {row['hourly_avg']:.2f} snt/kWh")
                            c2.metric("Kokonaiskustannus (sis. siirto)", f"{row['Total_snt']:.2f} snt")
                            st.caption("Klikkaamalla graafia näet tarkat luvut tässä.")

# --- LATAUSNAPIT (Jos laskenta tehty) ---
if 'latest_result' in st.session_state:
    st.subheader("Lataa tiedostot")
    dl1, dl2 = st.columns(2)
    
    with dl1:
        # PDF Lataus
        pdf_file = create_pdf(st.session_state.latest_result)
        st.download_button(
            label="📄 Lataa PDF-kuitti",
            data=pdf_file,
            file_name=f"kuitti_{st.session_state.latest_result['Pvm']}.pdf",
            mime="application/pdf",
            use_container_width=True
        )
    
    with dl2:
        # CSV Lataus (yksittäinen raportti)
        df_single = pd.DataFrame([st.session_state.latest_result])
        st.download_button(
            label="📊 Lataa CSV-raportti",
            data=df_single.to_csv(index=False, sep=";", encoding="utf-8-sig"),
            file_name=f"raportti_{st.session_state.latest_result['Pvm']}.csv",
            mime="text/csv",
            use_container_width=True
        )

# --- HISTORIA ---
if st.session_state.history:
    st.divider()
    st.subheader("📜 Historia")
    hist_df = pd.DataFrame(st.session_state.history)
    st.dataframe(hist_df, use_container_width=True, hide_index=True)
    
    st.download_button(
        label="📥 Lataa koko historia (CSV)",
        data=hist_df.to_csv(index=False, sep=";", encoding="utf-8-sig"),
        file_name="lataushistoria.csv",
        mime="text/csv",
        use_container_width=True
    )
