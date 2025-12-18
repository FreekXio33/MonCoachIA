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

# --- VALEURS PAR DÉFAUT (Profil) ---
# Astuce : Modifie ces valeurs ici pour ne pas avoir à les retaper à chaque redémarrage
DEFAULT_FC_MAX = 190
DEFAULT_FC_REPOS = 55
DEFAULT_FTP = 200
DEFAULT_POIDS = 75

# --- INITIALISATION SESSION STATE (Mémoire) ---
if 'fc_max' not in st.session_state: st.session_state.fc_max = DEFAULT_FC_MAX
if 'fc_repos' not in st.session_state: st.session_state.fc_repos = DEFAULT_FC_REPOS
if 'ftp' not in st.session_state: st.session_state.ftp = DEFAULT_FTP
if 'poids' not in st.session_state: st.session_state.poids = DEFAULT_POIDS

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

# --- GARMIN ---
@st.cache_data(ttl=3600)
def get_global_data():
    email = st.secrets["GARMIN_EMAIL"]
    password = st.secrets["GARMIN_PASSWORD"]
    client = None
    for i in range(3):
        try:
            client = Garmin(email, password)
            client.login()
            break
        except: time.sleep(3)
    
    if client is None: return None, "Erreur connexion", None, None

    try:
        today = date.today()
        stats = client.get_user_summary(today.isoformat())
        data_list = []
        for i in range(6, -1, -1):
            d = today - timedelta(days=i)
            try:
                day = client.get_user_summary(d.isoformat())
                steps = day.get('totalSteps', 0)
                bb = day.get('bodyBatteryMostRecentValue', 0)
                data_list.append({"Date": d.strftime("%d/%m"), "Pas": steps, "Body Battery": bb})
            except: continue
            
        start = date(2025, 9, 1)
        acts = client.get_activities_by_date(start.isoformat(), today.isoformat())
        return stats, pd.DataFrame(data_list), acts, client
    except Exception as e: return None, str(e), None, None

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
with st.spinner('Synchro Garmin...'):
    stats, df, acts, client = get_global_data()

if isinstance(df, str):
    st.error(df)
    st.stop()

# KPI
pas = stats.get('totalSteps', 0)
bb = stats.get('bodyBatteryMostRecentValue', 0)
c1, c2 = st.columns(2)
c1.metric("👣 Pas", pas)
c2.metric("🔋 Body Battery", bb)

st.divider()

# --- ONGLETS (AJOUT DE 'PROFIL') ---
t1, t2, t3, t4, t5, t6 = st.tabs(["Activités", "Santé", "Cartes", "Analyse", "📅 Créateur", "👤 Profil"])

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

# --- ONGLET PROFIL (CONFIGURATION) ---
with t6:
    st.header("👤 Tes Métriques")
    st.caption("Ces valeurs sont envoyées à l'IA pour personnaliser tes zones.")
    
    col_p1, col_p2 = st.columns(2)
    st.session_state.fc_max = col_p1.number_input("FC Max (bpm)", value=st.session_state.fc_max)
    st.session_state.fc_repos = col_p2.number_input("FC Repos (bpm)", value=st.session_state.fc_repos)
    
    col_p3, col_p4 = st.columns(2)
    st.session_state.ftp = col_p3.number_input("FTP Vélo (Watts)", value=st.session_state.ftp)
    st.session_state.poids = col_p4.number_input("Poids (kg)", value=st.session_state.poids)
    
    st.info(f"✅ Zones estimées : Zone 2 (Endurance) = {int(st.session_state.fc_max * 0.65)}-{int(st.session_state.fc_max * 0.75)} bpm")

# --- ANALYSE (AVEC PROFIL) ---
with t4:
    if st.button("Analyser ma saison"):
        with st.spinner("Analyse..."):
            hist = "".join([f"- {a['startTimeLocal'][:10]}: {a['activityType']['typeKey']} ({a.get('distance',0)/1000:.1f}km)\n" for a in acts])
            
            # Injection du profil dans le prompt
            profil_str = f"PROFIL ATHLÈTE : FC Max={st.session_state.fc_max}, FC Repos={st.session_state.fc_repos}, FTP={st.session_state.ftp}W, Poids={st.session_state.poids}kg."
            
            prompt = f"Coach sportif. Datas: BB={bb}, Pas={pas}. {profil_str} Historique:\n{hist}\nAnalyse charge et conseil précis (base toi sur mes zones)."
            try: st.markdown(genai.GenerativeModel("models/gemini-2.5-flash").generate_content(prompt).text)
            except Exception as e: st.error(e)

# --- CRÉATEUR (AVEC PROFIL) ---
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
        with st.spinner(f"Création de la séance..."):
            
            # Injection du profil pour les zones
            profil_str = f"MES MÉTRIQUES : FC Max={st.session_state.fc_max}, FTP={st.session_state.ftp}W."
            
            prompt = f"""
            Coach sportif expert.
            CONTEXTE : Séance pour le {date_seance} ({jour_semaine}). Forme: {bb}/100.
            {profil_str}
            DEMANDE : {sport}, {duree} min.
            
            MISSION : Crée une séance structurée.
            IMPORTANT : Affiche un TABLEAU Markdown : | Étape | Durée | Intensité | Détails |.
            Dans 'Intensité', utilise mes valeurs (ex: '150 bpm' ou '200 Watts') au lieu de juste dire 'Zone 2'.
            """
            
            try:
                model = genai.GenerativeModel("models/gemini-2.5-flash")
                resp = model.generate_content(prompt)
                st.success(f"Séance du {date_seance}")
                st.markdown(resp.text)
            except Exception as e:
                st.error(f"Erreur IA : {e}")
