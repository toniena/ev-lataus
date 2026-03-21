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

if 'init_done' not in st.session_state:
    now = datetime.now()
    st.session_state.d_start = now.date()
    st.session_state.t_start = (now - timedelta(hours=2)).time()
    st.session_state.d_end = now.date()
    st.session_state.t_end = now.time()
    st.session_state.init_done = True

# --- PDF GENEROINTI ---
def create_pdf(data):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("helvetica", "B", 24)
    pdf.set_text_color(0, 102, 204)
    pdf.cell(0, 20, "LATAUSKUITTI", ln=True, align="C")
    pdf.set_font("helvetica", "", 12)
    pdf.ln(10)
    pdf.cell(95, 10, f" Pvm: {data['Pvm']}", border=1)
    pdf.cell(95, 10, f" Ladattu: {data['kWh']} kWh", border=1, ln=True)
    pdf.ln(10)
    pdf.set_font("helvetica", "B", 14)
    pdf.cell(0, 10, "Kustannuserittely (sis. ALV 25,5%)", ln=True)
    pdf.set_font("helvetica", "", 12)
    pdf.cell(100, 10, "Sahkoenergia:")
    pdf.cell(0, 10, f"{data['Sahko (EUR)']:.2f} EUR", ln=True, align="R")
    pdf.cell(100, 10, "Siirto ja muut:")
    pdf.cell(0, 10, f"{data['Siirto (EUR)'] + data['Perus (EUR)']:.2f} EUR", ln=True, align="R")
    pdf.set_font("helvetica", "B", 14)
    pdf.cell(100, 15, "YHTEENSA:")
    pdf.cell(0, 15, f"{data['Yhteensa (EUR)']:.2f} EUR", ln=True, align="R")
    return bytes(pdf.output())

# --- FUNKTIOT ---
def fetch_prices(s, e):
    # Haetaan raakadata ilman API:n omaa ALV-käsittelyä, lasketaan 25.5% itse
    url = f"https://sahkotin.fi/prices?start={s.isoformat()}&end={e.isoformat()}"
    try:
        r = requests.get(url, timeout=10)
        data = r.json()
        df = pd.DataFrame(data["prices"])
        df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None)
        
        # Laskenta: €/MWh -> snt/kWh + ALV 25.5%
        df["snt_per_kwh_alv"] = (df["value"] / 10) * 1.255
        df["price_eur"] = df["snt_per_kwh_alv"] / 100 
        return df
    except:
        return pd.DataFrame()

# --- UI ---
st.title("🔋 Sähköauton latauskustannus")
st.info("💡 Varttitason hinnoittelu käytössä. ALV 25,5 % laskettu pörssihinnan päälle.")

with st.sidebar:
    st.header("Asetukset")
    sopimus = st.radio("Sähkösopimus", ["Pörssisähkö", "Kiinteä"])
    marginaali_snt = st.number_input("Marginaali snt/kWh (sis. ALV)", value=0.0, step=0.01) if sopimus == "Pörssisähkö" else 0.0
    hinta_kiintea = st.number_input("Kiinteä hinta snt/kWh (sis. ALV)", value=10.0) if sopimus == "Kiinteä" else 0.0
    siirto_snt = st.number_input("Siirtohinta snt/kWh (sis. ALV)", value=5.75, step=0.01)
    perus_snt = st.number_input("Perusmaksu snt/päivä", value=17.0, step=1.0)
    kwh_input = st.number_input("Ladattu määrä (kWh)", value=20.0, step=0.5)

st.subheader("Latausajankohta")
c1, c2 = st.columns(2)
with c1:
    d_start = st.date_input("Alkupäivä", key="d_start")
    t_start = st.time_input("Alkuaika", key="t_start", step=60)
with c2:
    d_end = st.date_input("Loppupäivä", key="d_end")
    t_end = st.time_input("Loppuaika", key="t_end", step=60)

start_dt = datetime.combine(d_start, t_start)
end_dt = datetime.combine(d_end, t_end)

if st.button("Laske kustannukset", type="primary", use_container_width=True):
    with st.spinner("Haetaan varttitason dataa..."):
        df = fetch_prices(start_dt, end_dt)
        if df.empty and sopimus == "Pörssisähkö":
            st.error("Hintatietoja ei löytynyt valitulle välille.")
        else:
            # Rajataan data
            mask = (df['date'] >= start_dt - timedelta(minutes=14)) & (df['date'] <= end_dt)
            df_f = df.loc[mask].copy().sort_values("date")
            
            h_kesto = (end_dt - start_dt).total_seconds() / 3600
            siirto_eur = kwh_input * (siirto_snt / 100)
            perus_eur = (perus_snt / 100) * (h_kesto / 24)
            
            if sopimus == "Pörssisähkö":
                # Lasketaan keskiarvo kaikista saatavilla olevista varttipisteistä
                avg_spot = df_f["price_eur"].mean() if not df_f.empty else 0
                energy_eur = kwh_input * (avg_spot + (marginaali_snt / 100))
            else:
                energy_eur = kwh_input * (hinta_kiintea / 100)

            total_eur = energy_eur + siirto_eur + perus_eur
            avg_total = (total_eur / kwh_input) * 100

            st.session_state.latest_result = {
                "Pvm": start_dt.strftime("%d.%m.%Y"), "Alku": start_dt.strftime("%H:%M"), "Loppu": end_dt.strftime("%H:%M"),
                "kWh": kwh_input, "Sahko (EUR)": energy_eur, "Siirto (EUR)": siirto_eur, "Perus (EUR)": perus_eur,
                "Yhteensa (EUR)": total_eur, "snt/kWh": avg_total
            }
            st.session_state.history.append(st.session_state.latest_result)

            st.divider()
            m1, m2, m3 = st.columns(3)
            m1.metric("Yhteensä", f"{total_eur:.2f} €")
            m2.metric("Keskihinta (sis. ALV)", f"{avg_total:.2f} snt/kWh")
            m3.metric("Kesto", f"{int(h_kesto)}h {int((h_kesto*60)%60)}min")

            if not df_f.empty:
                st.subheader("Hintagraafi (sis. ALV 25,5%)")
                graph_df = df_f.copy()
                graph_df["Total_snt"] = graph_df["snt_per_kwh_alv"] + marginaali_snt + siirto_snt
                
                # Ryhmittely tunneittain tooltipiä varten
                graph_df['hour_group'] = graph_df['date'].dt.floor('H')
                graph_df['min'] = graph_df['date'].dt.minute
                
                # Lasketaan tunnin keskiarvot
                graph_df['h_avg_porssi'] = graph_df.groupby('hour_group')['snt_per_kwh_alv'].transform('mean')
                graph_df['h_avg_total'] = graph_df.groupby('hour_group')['Total_snt'].transform('mean')
                
                # Valmistellaan varttien arvot sarakkeiksi (00, 15, 30, 45)
                v_porssi = graph_df.pivot(index='hour_group', columns='min', values='snt_per_kwh_alv')
                v_total = graph_df.pivot(index='hour_group', columns='min', values='Total_snt')
                
                # Täytetään puuttuvat sarakkeet NaN:lla jos niitä ei ole ollenkaan
                for m in [0, 15, 30, 45]:
                    if m not in v_porssi.columns: v_porssi[m] = pd.NA
                    if m not in v_total.columns: v_total[m] = pd.NA
                
                v_porssi = v_porssi.rename(columns={0:'s00', 15:'s15', 30:'s30', 45:'s45'})
                v_total = v_total.rename(columns={0:'t00', 15:'t15', 30:'t30', 45:'t45'})
                
                # Yhdistetään takaisin päälomakkeeseen
                graph_df = graph_df.merge(v_porssi[['s00','s15','s30','s45']], left_on='hour_group', right_index=True)
                graph_df = graph_df.merge(v_total[['t00','t15','t30','t45']], left_on='hour_group', right_index=True)

                fig = go.Figure()
                fig.add_trace(go.Scatter(
                    x=graph_df["date"], y=graph_df["Total_snt"],
                    fill='tozeroy', mode='lines+markers', line=dict(color='#00CC96', width=2),
                    marker=dict(size=6),
                    customdata=graph_df[["h_avg_porssi", "h_avg_total", "s00","t00","s15","t15","s30","t30","s45","t45"]].values,
                    hovertemplate=(
                        "<b>Tunnin keskihinta (Pörssi | Kokonaishinta)</b><br>" +
                        "%{x|%H}.00 &nbsp;&nbsp; %{customdata[0]:.3f} | %{customdata[1]:.2f} snt/kWh<br><br>" +
                        "<b>Varttihinnat (Pörssi | Kokonaishinta)</b><br>" +
                        "%{x|%H}.00 &nbsp;&nbsp; %{customdata[2]:.3f} | %{customdata[3]:.2f} snt/kWh<br>" +
                        "%{x|%H}.15 &nbsp;&nbsp; %{customdata[4]:.3f} | %{customdata[5]:.2f} snt/kWh<br>" +
                        "%{x|%H}.30 &nbsp;&nbsp; %{customdata[6]:.3f} | %{customdata[7]:.2f} snt/kWh<br>" +
                        "%{x|%H}.45 &nbsp;&nbsp; %{customdata[8]:.3f} | %{customdata[9]:.2f} snt/kWh" +
                        "<extra></extra>"
                    )
                ))
                
                # Latauksen keskihinnan punainen viiva
                fig.add_shape(type="line", x0=graph_df["date"].min(), y0=avg_total, x1=graph_df["date"].max(), y1=avg_total,
                              line=dict(color="Red", width=2, dash="dash"))
                
                fig.update_layout(xaxis_title="Aika", yaxis_title="snt/kWh", template="plotly_dark", hovermode="x unified")
                st.plotly_chart(fig, use_container_width=True)

# LATAUSNAPIT JA HISTORIA
if 'latest_result' in st.session_state:
    st.subheader("Lataa raportit")
    c_dl1, c_dl2 = st.columns(2)
    with c_dl1:
        st.download_button("📄 PDF-kuitti", create_pdf(st.session_state.latest_result), f"kuitti_{datetime.now().strftime('%d%m%Y')}.pdf", "application/pdf", use_container_width=True)
    with c_dl2:
        csv = pd.DataFrame([st.session_state.latest_result]).to_csv(index=False, sep=";", encoding="utf-8-sig")
        st.download_button("📊 CSV-raportti", csv, "raportti.csv", "text/csv", use_container_width=True)

if st.session_state.history:
    st.divider()
    st.subheader("📜 Historia")
    st.dataframe(pd.DataFrame(st.session_state.history), use_container_width=True, hide_index=True)
