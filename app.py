import streamlit as st
import plotly.express as px
from datetime import date, timedelta
from garminconnect import Garmin
from google import genai
import pandas as pd

st.set_page_config(page_title="Coach AI", page_icon="⚡", layout="centered")

# --- STYLE ---
hide_streamlit_style = """
            <style>
            #MainMenu {visibility: hidden;}
            footer {visibility: hidden;}
            header {visibility: hidden;}
            .stMetric {background-color: #f0f2f6; padding: 10px; border-radius: 10px;}
            </style>
            """
st.markdown(hide_streamlit_style, unsafe_allow_html=True)

# --- FONCTIONS ---
@st.cache_data(ttl=3600)
def get_data():
    try:
        email = st.secrets["GARMIN_EMAIL"]
        password = st.secrets["GARMIN_PASSWORD"]
        client = Garmin(email, password)
        client.login()
        
        today = date.today()
        stats_today = client.get_user_summary(today.isoformat())
        
        data_list = []
        for i in range(6, -1, -1):
            d = today - timedelta(days=i)
            d_str = d.isoformat()
            try:
                day_data = client.get_user_summary(d_str)
                
                # --- SÉCURISATION DES DONNÉES ---
                # Pas
                steps = day_data.get('totalSteps', 0) or day_data.get('dailySteps', 0) or 0
                # Body Battery (Le correctif est ici !)
                bb = day_data.get('bodyBatteryMostRecentValue', 0) or day_data.get('bodyBatteryMostRecentLevel', 0) or 0
                
                data_list.append({
                    "Date": d.strftime("%d/%m"),
                    "Pas": steps,
                    "Cœur Repos": day_data.get('restingHeartRate', 0) or 0,
                    "Body Battery": bb
                })
            except:
                continue
                
        return stats_today, pd.DataFrame(data_list)
    except Exception as e:
        return None, str(e)

# --- APP ---
st.title(f"⚡ Coach - {date.today().strftime('%d/%m')}")

with st.spinner('Synchronisation...'):
    stats, df_history = get_data()

if isinstance(df_history, str):
    st.error(f"Erreur : {df_history}")
    st.stop()

# --- AFFICHAGE DONNÉES DU JOUR ---

# 1. Pas
pas = stats.get('totalSteps', stats.get('dailySteps', 0))

# 2. Sommeil
sommeil_sec = stats.get('sleepDurationInSeconds', stats.get('sleepingSeconds', 0))
if sommeil_sec:
    heures = int(sommeil_sec // 3600)
    minutes = int((sommeil_sec % 3600) // 60)
    sommeil_txt = f"{heures}h{minutes}"
else:
    sommeil_txt = "--"

# 3. Stress
stress = stats.get('averageStressLevel', '--')

# 4. Body Battery (CORRECTION ICI AUSSI)
body_bat = stats.get('bodyBatteryMostRecentValue', stats.get('bodyBatteryMostRecentLevel', '--'))

# --- METRIQUES ---
col1, col2 = st.columns(2)
col1.metric("👣 Pas", pas)
col2.metric("💤 Sommeil", sommeil_txt)

col3, col4 = st.columns(2)
col3.metric("⚡ Stress", f"{stress}/100")
col4.metric("🔋 Body Battery", body_bat)

st.markdown("---")

# --- ONGLETS ---
tab1, tab2, tab3 = st.tabs(["Activité", "Santé", "Coach IA"])

with tab1:
    if not df_history.empty:
        st.caption("Évolution des Pas")
        fig = px.bar(df_history, x='Date', y='Pas', color='Pas', color_continuous_scale='Blues')
        st.plotly_chart(fig, use_container_width=True)

with tab2:
    if not df_history.empty:
        st.caption("Body Battery (Énergie)")
        # On affiche la Body Battery en vert
        fig = px.line(df_history, x='Date', y='Body Battery', markers=True, color_discrete_sequence=['#2ecc71'])
        fig.update_layout(yaxis_range=[0, 100])
        st.plotly_chart(fig, use_container_width=True)

with tab3:
    if st.button("Lancer l'analyse IA"):
        with st.spinner("Analyse..."):
            try:
                client_ai = genai.Client(api_key=st.secrets["GEMINI_KEY"])
                prompt = f"Coach sportif. Données: Pas={pas}, Sommeil={sommeil_txt}, Stress={stress}, BodyBattery={body_bat}. Historique: {df_history.to_string()}. Donne un conseil court et motivant."
                response = client_ai.models.generate_content(model="gemini-1.5-flash", contents=prompt)
                st.info(response.text)
            except Exception as e:
                st.error(f"Erreur IA: {e}")

# Je laisse le Debug au cas où, mais fermé par défaut
with st.expander("🛠️ Debug Technique"):
    st.json(stats)
