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
            .stButton button {width: 100%; text-align: left;}
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
    if "walking" in t: return "🚶"
    if "strength" in t: return "🏋️"
    return "🏅"

# --- GARMIN (AVEC VOLUME HEBDOMADAIRE) ---
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
        
        # 2. Stats du jour
        stats = client.get_user_summary(today.isoformat())
        
        # 3. Historique récent (7 jours pour les petits graphes)
        data_list = []
        for i in range(6, -1, -1):
            d = today - timedelta(days=i)
            try:
                day = client.get_user_summary(d.isoformat())
                steps = day.get('totalSteps', 0)
                bb = day.get('bodyBatteryMostRecentValue', 0)
                data_list.append({"Date": d.strftime("%d/%m"), "Pas": steps, "Body Battery": bb})
            except: continue
            
        # 4. ACTIVITÉS (15 SEMAINES)
        # On remonte assez loin pour avoir de la donnée pour le graphique hebdo
        start_date = today - timedelta(weeks=16) 
        acts = client.get_activities_by_date(start_date.isoformat(), today.isoformat())
        
        # 5. Profil
        metrics = None
        try:
            user_profile = client.get_user_profile()
            weight_grams = user_profile.get('weight', 75000)
            metrics = {
                "fc_max": 190, 
                "fc_repos": 60,
                "poids": weight_grams / 1000,
                "ftp": 200,
                "vo2_run": user_profile.get('vo2MaxRunning', 0)
            }
        except: metrics = None 
        
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

# --- UI PRINCIPALE ---
st.title("Hey Alexis !")

if st.button("🔄 Forcer la mise à jour"):
    st.cache_data.clear()
    st.rerun()

with st.spinner('Analyse de ton volume...'):
    stats, df_daily, acts, client, metrics_garmin = get_global_data()

if isinstance(df_daily, str):
    st.error(df_daily)
    st.stop()

# KPI
pas = stats.get('totalSteps', 0)
bb = stats.get('bodyBatteryMostRecentValue', 0)
c1, c2 = st.columns(2)
c1.metric("👣 Pas (Auj.)", pas)
c2.metric("🔋 Body Battery", bb)

# --- GRAPHIQUE VOLUME HEBDOMADAIRE (NOUVEAU) ---
st.markdown("### 📈 Volume Hebdomadaire (Heures)")

if acts:
    # 1. Création DataFrame Pandas des activités
    df_acts = pd.DataFrame(acts)
    
    # 2. Conversion des dates et durées
    # On s'assure que c'est bien des dates
    df_acts['date'] = pd.to_datetime(df_acts['startTimeLocal'])
    # Conversion secondes -> heures
    df_acts['duration_h'] = df_acts['duration'] / 3600
    
    # 3. Groupement par Semaine (W-MON = Semaine commençant le Lundi)
    # On utilise 'resample' pour avoir aussi les semaines à 0h
    df_weekly = df_acts.set_index('date').resample('W-MON')['duration_h'].sum().reset_index()
    
    # 4. On garde les 15 dernières
    df_weekly = df_weekly.tail(15)
    
    # 5. Formatage de la date pour l'axe X (ex: "18 Dec")
    df_weekly['Semaine'] = df_weekly['date'].dt.strftime('%d %b')

    # 6. Affichage
    fig_vol = px.bar(
        df_weekly, 
        x='Semaine', 
        y='duration_h', 
        text_auto='.1f', # Affiche la valeur sur la barre
        color='duration_h',
        color_continuous_scale='Viridis'
    )
    fig_vol.update_layout(yaxis_title="Heures", xaxis_title=None, showlegend=False)
    st.plotly_chart(fig_vol, use_container_width=True)
else:
    st.info("Pas assez de données pour le graphique hebdo.")

st.divider()

# --- INITIALISATION SESSION ---
if metrics_garmin:
    if 'fc_max' not in st.session_state: st.session_state.fc_max = metrics_garmin['fc_max']
    if 'fc_repos' not in st.session_state: st.session_state.fc_repos = metrics_garmin['fc_repos']
    if 'poids' not in st.session_state: st.session_state.poids = metrics_garmin['poids']
    if 'ftp' not in st.session_state: st.session_state.ftp = metrics_garmin['ftp']
else:
    if 'fc_max' not in st.session_state: st.session_state.fc_max = 190
    if 'fc_repos' not in st.session_state: st.session_state.fc_repos = 60
    if 'poids' not in st.session_state: st.session_state.poids = 75.0
    if 'ftp' not in st.session_state: st.session_state.ftp = 200

# --- ONGLETS ---
t1, t2, t3, t4, t5, t6 = st.tabs(["Activités", "Santé", "Séances", "Analyse", "📅 Créateur", "👤 Profil"])

with t1:
    if not df_daily.empty: st.plotly_chart(px.bar(df_daily, x='Date', y='Pas'), use_container_width=True)

with t2:
    if not df_daily.empty: st.plotly_chart(px.line(df_daily, x='Date', y='Body Battery'), use_container_width=True)

with t3:
    st.subheader("📜 Tes 10 dernières sorties")
    if acts:
        for a in acts[:10]:
            nom = a['activityName']
            date_str = a['startTimeLocal'][:10]
            icon = get_activity_icon(a['activityType']['typeKey'])
            if st.button(f"{icon} {date_str} : {nom}", key=a['activityId']):
                with st.spinner("Chargement carte..."):
                    p, c = get_gps(client, a['activityId'])
                    if p: st.pydeck_chart(pdk.Deck(layers=[pdk.Layer(type="PathLayer", data=p, get_color=[255,0,0], width_scale=20, get_path="path")], initial_view_state=pdk.ViewState(latitude=c[1], longitude=c[0], zoom=12)))
                    else: st.warning("Pas de GPS.")
    else: st.info("Vide.")

with t6:
    st.header("👤 Profil")
    if metrics_garmin: st.success("✅ Données Garmin Synchro")
    else: st.info("ℹ️ Mode Manuel")

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
