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

# --- GARMIN (VERSION ROBUSTE) ---
@st.cache_data(ttl=3600)
def get_global_data():
    email = st.secrets["GARMIN_EMAIL"]
    password = st.secrets["GARMIN_PASSWORD"]
    client = None
    
    # 1. Connexion
    for i in range(3):
        try:
            client = Garmin(email, password)
            client.login()
            break
        except: time.sleep(3)
    
    if client is None: return None, "Erreur connexion", None, None, None

    try:
        today = date.today()
        
        # 2. Données de base (Ça marche toujours)
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
        
        # 3. RÉCUPÉRATION PROFIL (BLINDÉE)
        # On met tout ça dans un try/except pour que l'app ne plante JAMAIS ici
        metrics = None
        try:
            # On essaie de récupérer le profil utilisateur standard
            # Cette méthode est plus stable que get_social_profile
            user_profile = client.get_user_profile()
            
            # Poids (souvent en grammes)
            weight_grams = user_profile.get('weight', 75000)
            
            # Pour la FC Max, c'est parfois dans les settings, parfois non
            # On tente une valeur par défaut si non trouvée
            metrics = {
                "fc_max": 190, # Valeur par défaut si non trouvée
                "fc_repos": 60,
                "poids": weight_grams / 1000,
                "ftp": 200,
                "vo2_run": user_profile.get('vo2MaxRunning', 0)
            }
            
            # Si on arrive à choper le VO2 Max, c'est que la connexion profil fonctionne
        except Exception as e:
            print(f"Info: Impossible de récupérer le profil détaillé ({e}). Passage en manuel.")
            metrics = None # Ce n'est pas grave, on passera en manuel
        
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

if st.button("🔄 Forcer la mise à jour"):
    st.cache_data.clear()
    st.rerun()

with st.spinner('Synchro Garmin...'):
    stats, df, acts, client, metrics_garmin = get_global_data()

if isinstance(df, str):
    st.error(df)
    st.stop()

# --- KPI ---
pas = stats.get('totalSteps', 0)
bb = stats.get('bodyBatteryMostRecentValue', 0)
c1, c2 = st.columns(2)
c1.metric("👣 Pas", pas)
c2.metric("🔋 Body Battery", bb)

st.divider()

# --- INITIALISATION SESSION ---
# Si on a trouvé des infos Garmin, on écrase les valeurs. Sinon on garde l'existant.
if metrics_garmin:
    if 'fc_max' not in st.session_state: st.session_state.fc_max = metrics_garmin['fc_max']
    if 'fc_repos' not in st.session_state: st.session_state.fc_repos = metrics_garmin['fc_repos']
    if 'poids' not in st.session_state: st.session_state.poids = metrics_garmin['poids']
    if 'ftp' not in st.session_state: st.session_state.ftp = metrics_garmin['ftp']
else:
    # Valeurs par défaut si Garmin échoue ou première visite
    if 'fc_max' not in st.session_state: st.session_state.fc_max = 190
    if 'fc_repos' not in st.session_state: st.session_state.fc_repos = 60
    if 'poids' not in st.session_state: st.session_state.poids = 75.0
    if 'ftp' not in st.session_state: st.session_state.ftp = 200

# --- ONGLETS ---
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

with t6:
    st.header("👤 Profil")
    if metrics_garmin:
        st.success("✅ Données synchronisées avec Garmin")
        if metrics_garmin.get('vo2_run'): st.caption(f"VO2 Max Run détectée : {metrics_garmin['vo2_run']}")
    else:
        st.info("ℹ️ Mode Manuel (Données Garmin protégées ou inaccessibles)")

    c_p1, c_p2 = st.columns(2)
    st.session_state.fc_max = c_p1.number_input("FC Max", value=st.session_state.fc_max)
    st.session_state.fc_repos = c_p2.number_input("FC Repos", value=st.session_state.fc_repos)
    
    c_p3, c_p4 = st.columns(2)
    st.session_state.ftp = c_p3.number_input("FTP (W)", value=st.session_state.ftp)
    st.session_state.poids = c_p4.number_input("Poids (kg)", value=st.session_state.poids)

with t4:
    if st.button("Analyser ma saison"):
        with st.spinner("Analyse..."):
            hist = "".join([f"- {a['startTimeLocal'][:10]}: {a['activityType']['typeKey']} ({a.get('distance',0)/1000:.1f}km)\n" for a in acts])
            profil = f"PROFIL: FCMax={st.session_state.fc_max}, Poids={st.session_state.poids}kg, FTP={st.session_state.ftp}W."
            prompt = f"Coach sportif. {profil} Datas: BB={bb}, Pas={pas}. Historique:\n{hist}\nAnalyse charge et conseil."
            try: st.markdown(genai.GenerativeModel("models/gemini-2.5-flash").generate_content(prompt).text)
            except Exception as e: st.error(e)

with t5:
    st.header("📅 Planifier")
    c_d, c_s = st.columns(2)
    demain = date.today() + timedelta(days=1)
    d_sea = c_d.date_input("Date", demain)
    sport = c_s.selectbox("Sport", ["Course à pied", "Vélo", "Muscu"])
    
    dur = st.slider("Durée (min)", 30, 180, 60, step=15)
    
    if st.button("Générer"):
        with st.spinner("Création..."):
            profil = f"MES ZONES: FCMax={st.session_state.fc_max}, FTP={st.session_state.ftp}W."
            prompt = f"Coach expert. Séance le {d_sea}. Forme {bb}/100. {profil}. Sport: {sport}, {dur}min. Crée séance structurée (Tableau)."
            try: st.markdown(genai.GenerativeModel("models/gemini-2.5-flash").generate_content(prompt).text)
            except Exception as e: st.error(e)
