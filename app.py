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

# ONGLETS
t1, t2, t3, t4, t5 = st.tabs(["Activités", "Santé", "Cartes", "Analyse", "📅 Créateur"])

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

with t4:
    if st.button("Analyser ma saison"):
        with st.spinner("Analyse..."):
            hist = "".join([f"- {a['startTimeLocal'][:10]}: {a['activityType']['typeKey']} ({a.get('distance',0)/1000:.1f}km)\n" for a in acts])
            prompt = f"Coach sportif. Datas: BB={bb}, Pas={pas}. Historique:\n{hist}\nAnalyse charge et conseil."
            try: st.markdown(genai.GenerativeModel("models/gemini-2.5-flash").generate_content(prompt).text)
            except Exception as e: st.error(e)

# --- NOUVEL ONGLET CRÉATEUR AVEC DATE ---
with t5:
    st.header("📅 Planifier une séance")
    
    # 1. LE SÉLECTEUR DE DATE
    c_date, c_sport = st.columns(2)
    # Date par défaut = demain
    demain = date.today() + timedelta(days=1)
    date_seance = c_date.date_input("Date de la séance", demain)
    sport = c_sport.selectbox("Sport", ["Course à pied", "Vélo", "Musculation"])
    
    # 2. Paramètres
    c_duree, c_intensite = st.columns(2)
    duree = c_duree.slider("Durée (min)", 30, 180, 60, step=15)
    
    # Astuce : On récupère le jour de la semaine pour l'IA
    jour_semaine = date_seance.strftime("%A") # Renvoie 'Monday', etc.
    
    if st.button("Générer la séance"):
        with st.spinner(f"Création de la séance pour le {date_seance}..."):
            
            prompt = f"""
            Agis comme un coach sportif expert.
            
            CONTEXTE :
            - Date prévue de la séance : {date_seance} (C'est un {jour_semaine}).
            - Ma forme actuelle (Body Battery) : {bb}/100.
            
            DEMANDE :
            - Sport : {sport}
            - Durée : {duree} minutes.
            
            MISSION :
            Crée une séance structurée adaptée à ma forme et au jour de la semaine.
            IMPORTANT : Donne-moi la structure exacte (Échauffement / Corps / Retour au calme) de façon claire pour que je puisse la copier dans ma montre.
            """
            
            try:
                model = genai.GenerativeModel("models/gemini-2.5-flash")
                resp = model.generate_content(prompt)
                
                st.success(f"Séance planifiée pour le {date_seance}")
                st.markdown(resp.text)
                
                st.info("💡 Pour mettre cette séance sur ta montre : Ouvre Garmin Connect > Entraînement > Créer > Copie les étapes ci-dessus.")
                
            except Exception as e:
                st.error(f"Erreur IA : {e}")
