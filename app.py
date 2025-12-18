import streamlit as st
import plotly.express as px
from datetime import date, timedelta
from garminconnect import Garmin
from google import genai
import pandas as pd

st.set_page_config(page_title="Coach AI", page_icon="⚡", layout="centered")

# --- CSS POUR FAIRE JOLI ---
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
                # ICI : On cherche 'totalSteps' OU 'dailySteps'
                steps = day_data.get('totalSteps', 0) or day_data.get('dailySteps', 0) or 0
                
                data_list.append({
                    "Date": d.strftime("%d/%m"),
                    "Pas": steps,
                    "Cœur Repos": day_data.get('restingHeartRate', 0) or 0,
                    "Stress": day_data.get('averageStressLevel', 0) or 0,
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

# --- RÉCUPÉRATION INTELLIGENTE DES DONNÉES ---
# 1. PAS : On cherche totalSteps (votre trouvaille) en priorité
pas = stats.get('totalSteps', stats.get('dailySteps', 0))

# 2. SOMMEIL : On cherche plusieurs noms possibles
sommeil_sec = stats.get('sleepDurationInSeconds', stats.get('sleepingSeconds', 0))

# 3. Calcul du sommeil en texte (7h30)
if sommeil_sec:
    heures = int(sommeil_sec // 3600)
    minutes = int((sommeil_sec % 3600) // 60)
    sommeil_txt = f"{heures}h{minutes}"
else:
    sommeil_txt = "--" # Pas de données

# 4. AUTRES
stress = stats.get('averageStressLevel', '--')
body_bat = stats.get('bodyBatteryMostRecentLevel', '--')

# --- AFFICHAGE ---
col1, col2 = st.columns(2)
col1.metric("👣 Pas", pas)
col2.metric("💤 Sommeil", sommeil_txt)

col3, col4 = st.columns(2)
col3.metric("⚡ Stress", f"{stress}/100")
col4.metric("🔋 Body Battery", body_bat)

st.markdown("---")

# --- GRAPHIQUES ---
tab1, tab2, tab3 = st.tabs(["Activité", "Santé", "Coach IA"])

with tab1:
    if not df_history.empty:
        fig = px.bar(df_history, x='Date', y='Pas', color='Pas', color_continuous_scale='Blues')
        st.plotly_chart(fig, use_container_width=True)

with tab2:
    if not df_history.empty:
        st.caption("Fréquence Cardiaque au Repos")
        fig = px.line(df_history, x='Date', y='Cœur Repos', markers=True, color_discrete_sequence=['#FF4B4B'])
        fig.update_layout(yaxis_range=[40, 80])
        st.plotly_chart(fig, use_container_width=True)

with tab3:
    if st.button("Lancer l'analyse IA"):
        with st.spinner("Analyse..."):
            try:
                client_ai = genai.Client(api_key=st.secrets["GEMINI_KEY"])
                prompt = f"Coach sportif. Données: Pas={pas}, Sommeil={sommeil_txt}, Stress={stress}. Historique semaine: {df_history.to_string()}. Donne un conseil court."
                response = client_ai.models.generate_content(model="gemini-1.5-flash", contents=prompt)
                st.info(response.text)
            except Exception as e:
                st.error(f"Erreur IA: {e}")

# Debugeur (Je le laisse au cas où le sommeil soit encore caché)
with st.expander("Debug Données"):
    st.json(stats)
