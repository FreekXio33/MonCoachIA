import streamlit as st
import plotly.express as px
import pydeck as pdk
from datetime import date, timedelta
from garminconnect import Garmin
import google.generativeai as genai
import pandas as pd
import time
import os

# --- CONFIGURATION ---
st.set_page_config(page_title="Coach AI", page_icon="⚡", layout="centered")
st.markdown("""
            <style>
            #MainMenu {visibility: hidden;}
            footer {visibility: hidden;}
            header {visibility: hidden;}
            .stMetric {background-color: #f0f2f6; padding: 10px; border-radius: 10px;}
            </style>
            """, unsafe_allow_html=True)

# --- IA ---
try:
    api_key = st.secrets["GEMINI_KEY"]
    genai.configure(api_key=api_key)
except:
    st.error("⚠️ Clé API manquante.")

# --- UTILITAIRES ---
def format_duration(seconds):
    if not seconds: return "--"
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    return f"{h}h {m}m" if h > 0 else f"{m}m"

def get_activity_icon(type_key):
    t = str(type_key).lower()
    if "running" in t: return "🏃"
    if "cycling" in t: return "🚴"
    if "swimming" in t: return "🏊"
    return "🏅"

# --- GARMIN (AVEC RÉCUPÉRATION PROFIL) ---
@st.cache_data(ttl=3600)
def get_global_data():
    email = st.secrets["GARMIN_EMAIL"]
    password = st.secrets["GARMIN_PASSWORD"]
    client = None
    
    # Tentative de connexion
    for i in range(3):
        try:
            client = Garmin(email, password)
            client.login()
            break
        except: time.sleep(3)
    
    if client is None: return None, "Erreur connexion", None, None, None

    try:
        today = date.today()
        
        # 1. Stats du jour
        stats = client.get_user_summary(today.isoformat())
        
        # 2. Historique récent
        data_list = []
        for i in range(6, -1, -1):
            d = today - timedelta(days=i)
            try:
                day = client.get_user_summary(d.isoformat())
                steps = day.get('totalSteps', 0)
                bb = day.get('bodyBatteryMostRecentValue', 0)
                data_list.append({"Date": d.strftime("%d/%m"), "Pas": steps, "Body Battery": bb})
            except: continue
            
        # 3. Activités (depuis Septembre)
        start = date(2025, 9, 1)
        acts = client.get_activities_by_date(start.isoformat(), today.isoformat())
        
        # 4. RÉCUPÉRATION DU PROFIL PHYSIQUE
        # On doit d'abord récupérer le "display name" pour accéder aux settings
        social_profile = client.get_social_profile()
        display_name = social_profile['displayName']
        full_settings = client.get_user_settings(display_name)
        user_data = full_settings.get('userData', {})
        
        # Extraction des métriques (avec des valeurs par défaut si non trouvées)
        # Garmin stocke le poids en grammes, on divise par 1000
        metrics = {
            "fc_max": user_data.get('maxHeartRate', 190),
            "fc_repos": user_data.get('restingHeartRate', 60),
            "poids": user_data.get('weight', 75000) / 1000, 
            "ftp": user_data.get('functionalThresholdPower', 200), # Parfois absent selon la montre
            "vo2_run": user_data.get('vo2MaxRunning', 0),
            "vo2_cycle": user_data.get('vo2MaxCycling', 0)
        }
        
        return stats, pd.DataFrame(data_list), acts, client, metrics
        
    except Exception as e: return None, str(e), None, None, None

def get_gps(client, id):
    try:
        d = client.get_activity_details(id)
        pts = d['geoPolylineDTO']['polyline']
        path = [{"path": [[p['longitude'], p['latitude']] for p in pts]}]
        c = [pts[len(pts)//2]['longitude'], pts[len(pts)//2]['latitude']]
        return path, c
    except: return None, None

# --- UI ---
st.title("Hey Alexis !")

if st.button("🔄 Forcer la mise à jour (Garmin)"):
    st.cache_data.clear()
    st.rerun()

with st.spinner('Synchro des données et du profil...'):
    stats, df, acts, client, metrics_garmin = get_global_data()

if isinstance(df, str):
    st.error(df)
    st.stop()

# --- INITIALISATION SESSION STATE AVEC DONNÉES GARMIN ---
# Si on a récupéré des métriques de Garmin, on les met à jour dans la mémoire
if metrics_garmin:
    if 'fc_max' not in st.session_state: st.session_state.fc_max = metrics_garmin['fc_max']
    if 'fc_repos' not in st.session_state: st.session_state.fc_repos = metrics_garmin['fc_repos']
    if 'poids' not in st.session_state: st.session_state.poids = metrics_garmin['poids']
    if 'ftp' not in st.session_state: st.session_state.ftp = metrics_garmin['ftp']

# KPI
pas = stats.get('totalSteps', 0)
bb = stats.get('bodyBatteryMostRecentValue', 0)
c1, c2 = st.columns(2)
c1.metric("👣 Pas", pas)
c2.metric("🔋 Body Battery", bb)

st.divider()

# --- ONGLETS ---
t1, t2, t3, t4, t5, t6 = st.tabs(["Activités", "Santé", "Cartes", "Analyse", "📅 Créateur", "👤 Profil Auto"])

with t1:
    if not df.empty: st.plotly_chart(px.bar(df, x='Date', y='Pas'), use_container_width=True)

with t2:
    if not df.empty: st.plotly_chart(px.line(df, x='Date', y='Body Battery'), use_container_width=True)

with t3:
    if acts:
        for a in acts[:3]:
            if st.button(f"Carte : {a['activityName']}", key=a['activityId']):
                p, c = get_gps(client, a['activityId'])
                if p: st.pydeck_chart(pdk.Deck(layers=[pdk.Layer(type="PathLayer", data=p, get_color=[255,0,0], width_scale=20, get_path="path")], initial_view_state=pdk.ViewState(latitude=c[1], longitude=c[0], zoom=12)))

# --- ONGLET PROFIL (AUTOMATISÉ) ---
with t6:
    st.header("👤 Profil Synchronisé")
    if metrics_garmin:
        st.success("✅ Données récupérées depuis ton compte Garmin !")
    else:
        st.warning("⚠️ Mode manuel (Données Garmin inaccessibles)")

    col_p1, col_p2 = st.columns(2)
    st.session_state.fc_max = col_p1.number_input("FC Max (Garmin)", value=st.session_state.fc_max)
    st.session_state.fc_repos = col_p2.number_input("FC Repos (Garmin)", value=st.session_state.fc_repos)
    
    col_p3, col_p4 = st.columns(2)
    st.session_state.ftp = col_p3.number_input("FTP (Watts)", value=st.session_state.ftp)
    st.session_state.poids = col_p4.number_input("Poids (kg)", value=st.session_state.poids)
    
    # Affichage VO2 Max si dispo
    if metrics_garmin and metrics_garmin.get('vo2_run'):
        st.caption(f"🚀 VO2 Max détectée : {metrics_garmin['vo2_run']} ml/kg/min")

# --- ANALYSE ---
with t4:
    if st.button("Analyser ma saison"):
        with st.spinner("Analyse..."):
            hist = "".join([f"- {a['startTimeLocal'][:10]}: {a['activityType']['typeKey']} ({a.get('distance',0)/1000:.1f}km)\n" for a in acts])
            profil_str = f"PROFIL ATHLÈTE : FC Max={st.session_state.fc_max}, FC Repos={st.session_state.fc_repos}, FTP={st.session_state.ftp}W, Poids={st.session_state.poids}kg."
            prompt = f"Coach sportif. Datas: BB={bb}, Pas={pas}. {profil_str} Historique:\n{hist}\nAnalyse charge et conseil précis."
            try: st.markdown(genai.GenerativeModel("models/gemini-2.5-flash").generate_content(prompt).text)
            except Exception as e: st.error(e)

# --- CRÉATEUR ---
with t5:
    st.header("📅 Planifier une séance")
    c_date, c_sport = st.columns(2)
    demain = date.today() + timedelta(days=1)
    date_seance = c_date.date_input("Date", demain)
    sport = c_sport.selectbox("Sport", ["Course à pied", "Vélo", "Musculation"])
    
    c_duree, c_intensite = st.columns(2)
    duree = c_duree.slider("Durée (min)", 30, 180, 60, step=15)
    jour_semaine = date_seance.strftime("%A")
    
    if st.button("Générer la séance"):
        with st.spinner(f"Création..."):
            profil_str = f"MES ZONES : FC Max={st.session_state.fc_max}, FC Repos={st.session_state.fc_repos}, FTP={st.session_state.ftp}W."
            prompt = f"""
            Coach sportif expert.
            CONTEXTE : Séance le {date_seance} ({jour_semaine}). Forme: {bb}/100.
            {profil_str}
            DEMANDE : {sport}, {duree} min.
            MISSION : Crée une séance structurée (Tableau Markdown). Utilise mes valeurs cardiaques ou watts précises.
            """
            try:
                model = genai.GenerativeModel("models/gemini-2.5-flash")
                st.markdown(model.generate_content(prompt).text)
            except Exception as e: st.error(e)
