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

# --- PDF GENEROINTI ---
def create_pdf(data):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("helvetica", "B", 24)
    pdf.set_text_color(0, 102, 204)
    pdf.cell(0, 20, "LATAUSKUITTI", ln=True, align="C")
    
    pdf.set_font("helvetica", "", 12)
    pdf.set_text_color(0, 0, 0)
    pdf.ln(10)
    
    pdf.set_fill_color(245, 245, 245)
    pdf.set_font("helvetica", "B", 12)
    pdf.cell(95, 10, " Lataustapahtuma", border=1, fill=True)
    pdf.cell(95, 10, f" Pvm: {data['Pvm']}", border=1, ln=True, fill=True)
    
    pdf.set_font("helvetica", "", 12)
    pdf.cell(95, 10, f" Alku: {data['Alku']}", border=1)
    pdf.cell(95, 10, f" Loppu: {data['Loppu']}", border=1, ln=True)
    pdf.cell(95, 10, f" Ladattu määrä: {data['kWh']} kWh", border=1, ln=True)
    pdf.ln(15)
    
    pdf.set_font("helvetica", "B", 14)
    pdf.cell(0, 10, "Kustannuserittely (sis. ALV)", ln=True)
    pdf.set_draw_color(0, 102, 204)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(5)
    
    pdf.set_font("helvetica", "", 12)
    pdf.cell(100, 10, "Sahkoenergia:")
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
    plt.figure(figsize=(4, 4))
    plt.pie(sizes, labels=labels, autopct='%1.1f%%', startangle=140, colors=['#0066cc', '#3399ff', '#99ccff'])
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
        # snt/kWh. API palauttaa luvun, joka on 10x snt/kWh (eli €/MWh)
        df["snt_per_kwh"] = df["value"] / 10 
        df["price_eur"] = df["snt_per_kwh"] / 100 
        return df
    except:
        return pd.DataFrame()

# --- UI ---
st.title("🔋 Sähköauton latauskustannus")
st.info("💡 Kaikki sovelluksen hinnat on ilmoitettu sisältäen ALV:n (25,5 %).")

with st.sidebar:
    st.header("Asetukset")
    sopimus = st.radio("Sähkösopimus", ["Pörssisähkö", "Kiinteä"])
    if sopimus == "Kiinteä":
        hinta_snt = st.number_input("Sähkön hinta snt/kWh (sis. ALV)", value=10.0, step=0.1)
        marginaali_snt = 0.0
    else:
        hinta_snt = 0.0
        marginaali_snt = st.number_input("Marginaali snt/kWh (sis. ALV)", value=0.0, step=0.01)

    st.divider()
    siirto_snt = st.number_input("Siirtohinta snt/kWh (sis. ALV)", value=5.75, step=0.01)
    perus_snt = st.number_input("Perusmaksu snt/päivä (sis. ALV)", value=17.0, step=1.0)
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

# --- LASKENTA ---
if st.button("Laske kustannukset", type="primary", use_container_width=True):
    if start_dt >= end_dt:
        st.error("❌ Virhe: Alkuajan on oltava ennen loppuaikaa.")
    else:
        with st.spinner("Haetaan pörssidataa..."):
            df = fetch_prices(start_dt, end_dt)
            if df.empty and sopimus == "Pörssisähkö":
                st.error("Hintatietoja ei saatu haettua.")
            else:
                mask_calc = (df['date'] >= start_dt.replace(minute=0)) & (df['date'] <= end_dt)
                df_filtered = df.loc[mask_calc].copy().sort_values("date")

                latausaika_h = (end_dt - start_dt).total_seconds() / 3600
                siirto_cost_eur = kwh_input * (siirto_snt / 100)
                perus_cost_eur = (perus_snt / 100) * (latausaika_h / 24)
                
                if sopimus == "Pörssisähkö":
                    avg_spot_eur = df_filtered["price_eur"].mean() if not df_filtered.empty else 0
                    energy_cost_eur = kwh_input * (avg_spot_eur + (marginaali_snt / 100))
                else:
                    energy_cost_eur = kwh_input * (hinta_snt / 100)

                total_eur = energy_cost_eur + siirto_cost_eur + perus_cost_eur
                total_avg_snt = (total_eur / kwh_input) * 100

                kuitti_data = {
                    "Pvm": start_dt.strftime("%d.%m.%Y"), "Alku": start_dt.strftime("%H:%M"), "Loppu": end_dt.strftime("%H:%M"),
                    "kWh": kwh_input, "Sahko (EUR)": energy_cost_eur, "Siirto (EUR)": siirto_cost_eur,
                    "Perus (EUR)": perus_cost_eur, "Yhteensa (EUR)": total_eur, "snt/kWh": total_avg_snt
                }
                st.session_state.history.append(kuitti_data)
                st.session_state.latest_result = kuitti_data

                st.divider()
                m1, m2, m3 = st.columns(3)
                m1.metric("Kokonaiskustannus", f"{total_eur:.2f} €")
                m2.metric("Keskihinta (sis. ALV + kulut)", f"{total_avg_snt:.2f} snt/kWh")
                m3.metric("Kesto", f"{int(latausaika_h)}h {int((latausaika_h*60)%60)}min")

                if not df_filtered.empty:
                    st.subheader("Hinnan kehitys (snt/kWh, sis. ALV)")
                    graph_df = df_filtered.copy()
                    graph_df["Total_snt"] = graph_df["snt_per_kwh"] + marginaali_snt + siirto_snt
                    graph_df['hour_group'] = graph_df['date'].dt.floor('H')
                    
                    # Lasketaan tunnin keskiarvot (sis. ALV)
                    graph_df['hourly_spot_avg'] = graph_df.groupby('hour_group')['snt_per_kwh'].transform('mean')
                    graph_df['hourly_total_avg'] = graph_df.groupby('hour_group')['Total_snt'].transform('mean')
                    
                    graph_df['min'] = graph_df['date'].dt.minute
                    
                    # Varttidatan käsittely (NaN palautettu)
                    # Pivotoidaan arvot, mutta EI täytetä automaattisesti jos data puuttuu
                    v_total = graph_df.pivot(index='hour_group', columns='min', values='Total_snt')
                    v_spot = graph_df.pivot(index='hour_group', columns='min', values='snt_per_kwh')
                    
                    # Varmistetaan että sarakkeet 0, 15, 30, 45 löytyvät, mutta jätetään ne NaNiksi jos tietoa ei ole
                    for m in [0, 15, 30, 45]:
                        if m not in v_total.columns: 
                            v_total[m] = pd.NA
                            v_spot[m] = pd.NA
                    
                    v_total = v_total.rename(columns={0:'t00', 15:'t15', 30:'t30', 45:'t45'})
                    v_spot = v_spot.rename(columns={0:'s00', 15:'s15', 30:'s30', 45:'s45'})
                    
                    graph_df = graph_df.merge(v_total[['t00', 't15', 't30', 't45']], left_on='hour_group', right_index=True)
                    graph_df = graph_df.merge(v_spot[['s00', 's15', 's30', 's45']], left_on='hour_group', right_index=True)

                    fig = go.Figure()
                    fig.add_trace(go.Scatter(
                        x=graph_df["date"], y=graph_df["Total_snt"],
                        fill='tozeroy', mode='lines+markers', line=dict(color='#00CC96', width=2), marker=dict(size=8),
                        customdata=graph_df[["hourly_spot_avg", "hourly_total_avg", 
                                            "s00", "t00", "s15", "t15", "s30", "t30", "s45", "t45"]].values,
                        hovertemplate=(
                            "<b>Tunnin keskiarvo (Pörssi | Sis. kulut) sis. ALV</b><br>" +
                            "%{x|%H}.00 &nbsp;&nbsp; %{customdata[0]:.3f} | %{customdata[1]:.2f} snt/kWh<br><br>" +
                            "<b>Varttihinnat (Pörssi | Sis. kulut) sis. ALV</b><br>" +
                            "%{x|%H}.00 &nbsp;&nbsp; %{customdata[2]:.3f} | %{customdata[3]:.2f} snt/kWh<br>" +
                            "%{x|%H}.15 &nbsp;&nbsp; %{customdata[4]:.3f} | %{customdata[5]:.2f} snt/kWh<br>" +
                            "%{x|%H}.30 &nbsp;&nbsp; %{customdata[6]:.3f} | %{customdata[7]:.2f} snt/kWh<br>" +
                            "%{x|%H}.45 &nbsp;&nbsp; %{customdata[8]:.3f} | %{customdata[9]:.2f} snt/kWh" +
                            "<extra></extra>"
                        )
                    ))
                    fig.add_shape(type="line", x0=graph_df["date"].min(), y0=total_avg_snt, x1=graph_df["date"].max(), y1=total_avg_snt, line=dict(color="Red", width=3, dash="dash"))
                    fig.update_layout(xaxis_title="Aika", yaxis_title="snt/kWh", template="plotly_dark", hovermode="x unified")
                    st.plotly_chart(fig, use_container_width=True)

# --- LATAUSNAPIT ---
if 'latest_result' in st.session_state:
    st.subheader("Lataa tiedostot")
    dl1, dl2 = st.columns(2)
    with dl1:
        pdf_file = create_pdf(st.session_state.latest_result)
        st.download_button(label="📄 Lataa PDF-kuitti", data=pdf_file, file_name=f"kuitti_{st.session_state.latest_result['Pvm']}.pdf", mime="application/pdf", use_container_width=True)
    with dl2:
        st.download_button(label="📊 Lataa CSV-raportti", data=pd.DataFrame([st.session_state.latest_result]).to_csv(index=False, sep=";", encoding="utf-8-sig"), file_name=f"raportti_{st.session_state.latest_result['Pvm']}.csv", mime="text/csv", use_container_width=True)

# --- HISTORIA ---
if st.session_state.history:
    st.divider()
    st.subheader("📜 Historia")
    hist_df = pd.DataFrame(st.session_state.history)
    st.dataframe(hist_df, use_container_width=True, hide_index=True)
    st.download_button(label="📥 Lataa koko historia (CSV)", data=hist_df.to_csv(index=False, sep=";", encoding="utf-8-sig"), file_name="lataushistoria.csv", mime="text/csv", use_container_width=True)
