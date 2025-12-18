import streamlit as st
import plotly.express as px
from datetime import date, timedelta
from garminconnect import Garmin
from google import genai
import pandas as pd

# --- CONFIGURATION ---
st.set_page_config(page_title="Coach AI", page_icon="⚡", layout="centered")

# --- FONCTIONS ---
@st.cache_data(ttl=3600)
def get_data():
    try:
        email = st.secrets["GARMIN_EMAIL"]
        password = st.secrets["GARMIN_PASSWORD"]
        client = Garmin(email, password)
        client.login()
        
        today = date.today()
        # On récupère le résumé du jour
        stats_today = client.get_user_summary(today.isoformat())
        
        # On récupère l'historique
        data_list = []
        for i in range(6, -1, -1):
            d = today - timedelta(days=i)
            d_str = d.isoformat()
            try:
                day_data = client.get_user_summary(d_str)
                data_list.append({
                    "Date": d.strftime("%d/%m"),
                    "Pas": day_data.get('dailySteps', 0) or 0,
                    "Cœur Repos": day_data.get('restingHeartRate', 0) or 0,
                    "Stress": day_data.get('averageStressLevel', 0) or 0,
                    "Body Battery": day_data.get('bodyBatteryMostRecentLevel', 0) or 0
                })
            except:
                continue
                
        return stats_today, pd.DataFrame(data_list)
    except Exception as e:
        return None, str(e)

# --- INTERFACE ---
st.title(f"⚡ Mon Coach - {date.today().strftime('%d/%m')}")

with st.spinner('Synchronisation...'):
    stats, df_history = get_data()

# Gestion des erreurs de connexion
if isinstance(df_history, str):
    st.error(f"Erreur technique : {df_history}")
    st.stop()

# --- AFFICHAGE DES CHIFFRES (DEBUG) ---
# On utilise des .get() sécurisés pour éviter les bugs si la donnée manque
pas = stats.get('dailySteps', 0)
sommeil_sec = stats.get('sleepDurationInSeconds', 0)
stress = stats.get('averageStressLevel', 'N/A')
body_bat = stats.get('bodyBatteryMostRecentLevel', 'N/A')

# Calcul du sommeil en heures
if sommeil_sec:
    heures = int(sommeil_sec // 3600)
    minutes = int((sommeil_sec % 3600) // 60)
    sommeil_txt = f"{heures}h{minutes}"
else:
    sommeil_txt = "Pas de données"

# Les Colonnes
col1, col2 = st.columns(2)
col1.metric("👣 Pas", pas)
col2.metric("💤 Sommeil", sommeil_txt)

col3, col4 = st.columns(2)
col3.metric("⚡ Stress", f"{stress}/100")
col4.metric("🔋 Body Battery", body_bat)

st.markdown("---")

# --- GRAPHIQUE ---
if not df_history.empty:
    tab1, tab2 = st.tabs(["Pas", "Cœur"])
    with tab1:
        st.plotly_chart(px.bar(df_history, x='Date', y='Pas'), use_container_width=True)
    with tab2:
        st.plotly_chart(px.line(df_history, x='Date', y='Cœur Repos', markers=True, color_discrete_sequence=['red']), use_container_width=True)

# --- ZONE DÉTECTIVE (POUR COMPRENDRE LE PROBLÈME) ---
with st.expander("🔍 VOIR LES DONNÉES BRUTES (DEBUG)"):
    st.write("Voici exactement ce que Garmin renvoie pour aujourd'hui :")
    st.json(stats)
