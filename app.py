import streamlit as st
import plotly.express as px
import pydeck as pdk
from datetime import date, timedelta
from garminconnect import Garmin
from google import genai
import pandas as pd
import time

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

# --- UTILITAIRES ---
def format_duration(seconds):
    if not seconds: return "--"
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    if h > 0: return f"{h}h {m}m"
    return f"{m}m"

def get_activity_icon(type_key):
    type_key = str(type_key).lower()
    if "running" in type_key: return "🏃"
    if "cycling" in type_key: return "🚴"
    if "swimming" in type_key: return "🏊"
    if "walking" in type_key: return "🚶"
    return "🏅"

# --- CONNEXION ET DONNÉES ---
@st.cache_data(ttl=3600)
def get_global_data():
    email = st.secrets["GARMIN_EMAIL"]
    password = st.secrets["GARMIN_PASSWORD"]
    
    # Reconnexion Tenace
    client = None
    for i in range(3):
        try:
            client = Garmin(email, password)
            client.login()
            break
        except:
            time.sleep(3)
    
    if client is None: return None, "Erreur connexion", None, None

    try:
        today = date.today()
        # 1. Résumé du jour
        stats_today = client.get_user_summary(today.isoformat())
        
        # 2. Historique 7 jours
        data_list = []
        for i in range(6, -1, -1):
            d = today - timedelta(days=i)
            d_str = d.isoformat()
            try:
                day_data = client.get_user_summary(d_str)
                steps = day_data.get('totalSteps', 0) or day_data.get('dailySteps', 0) or 0
                bb = day_data.get('bodyBatteryMostRecentValue', 0) or day_data.get('bodyBatteryMostRecentLevel', 0) or 0
                data_list.append({"Date": d.strftime("%d/%m"), "Pas": steps, "Body Battery": bb})
            except:
                continue
        
        # 3. HISTORIQUE LONG (Depuis le 1er Septembre 2025)
        start_date = date(2025, 9, 1)
        all_activities = client.get_activities_by_date(start_date.isoformat(), today.isoformat())
        
        return stats_today, pd.DataFrame(data_list), all_activities, client
        
    except Exception as e:
        return None, str(e), None, None

# --- FONCTION CARTE GPS ---
def get_gps_data(client, activity_id):
    try:
        details = client.get_activity_details(activity_id)
        if 'geoPolylineDTO' in details and 'polyline' in details['geoPolylineDTO']:
            raw_points = details['geoPolylineDTO']['polyline']
            path_data = [{"path": [[p['longitude'], p['latitude']] for p in raw_points]}]
            mid_point = raw_points[len(raw_points)//2]
            center = [mid_point['longitude'], mid_point['latitude']]
            return path_data, center
    except:
        pass
    return None, None

# --- CHARGEMENT ---
st.title("Hey Alexis !")

with st.spinner('Analyse de ton historique depuis Septembre...'):
    stats, df_history, activities, client = get_global_data()

if isinstance(df_history, str):
    st.error(f"⚠️ {df_history}")
    if st.button("Recharger"): st.rerun()
    st.stop()

# --- KPI DU JOUR ---
pas = stats.get('totalSteps', stats.get('dailySteps', 0))
sommeil_sec = stats.get('sleepDurationInSeconds', stats.get('sleepingSeconds', 0))
sommeil_txt = format_duration(sommeil_sec)
stress = stats.get('averageStressLevel', '--')
body_bat = stats.get('bodyBatteryMostRecentValue', stats.get('bodyBatteryMostRecentLevel', '--'))

col1, col2 = st.columns(2)
col1.metric("👣 Pas", pas)
col2.metric("💤 Sommeil", sommeil_txt)
col3, col4 = st.columns(2)
col3.metric("⚡ Stress", f"{stress}/100")
col4.metric("🔋 Body Battery", body_bat)

st.markdown("---")

# --- ONGLETS ---
tab1, tab2, tab3, tab4 = st.tabs(["📊 Activité", "❤️ Santé", "🏅 Cartes & Sport", "🤖 Coach"])

with tab1:
    if not df_history.empty:
        fig = px.bar(df_history, x='Date', y
