import streamlit as st
import plotly.express as px
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

# --- FONCTIONS UTILITAIRES ---
def format_duration(seconds):
    if not seconds: return "--"
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    if h > 0: return f"{h}h {m}m"
    return f"{m}m"

def get_activity_icon(type_key):
    # Petite fonction pour mettre un emoji sympa selon le sport
    type_key = str(type_key).lower()
    if "running" in type_key: return "🏃"
    if "cycling" in type_key: return "🚴"
    if "swimming" in type_key: return "🏊"
    if "walking" in type_key: return "🚶"
    if "yoga" in type_key: return "🧘"
    if "strength" in type_key: return "🏋️"
    return "🏅"

# --- FONCTION DE RÉCUPÉRATION ---
@st.cache_data(ttl=3600)
def get_data():
    email = st.secrets["GARMIN_EMAIL"]
    password = st.secrets["GARMIN_PASSWORD"]
    
    # Reconnexion Tenace (3 essais)
    client = None
    for i in range(3):
        try:
            client = Garmin(email, password)
            client.login()
            break
        except:
            time.sleep(3)
    
    if client is None:
        return None, "Connexion impossible", None

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
                data_list.append({
                    "Date": d.strftime("%d/%m"),
                    "Pas": steps,
                    "Body Battery": bb
                })
            except:
                continue
        
        # 3. Dernières Activités (NOUVEAU !)
        # On récupère les 5 dernières (0 à 5)
        activities = client.get_activities(0, 5)
                
        return stats_today, pd.DataFrame(data_list), activities
        
    except Exception as e:
        return None, str(e), None

# --- CHARGEMENT ---
st.title(f"⚡ Coach - {date.today().strftime('%d/%m')}")

with st.spinner('Synchronisation...'):
    stats, df_history, activities = get_data()

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
# On ajoute l'onglet "Activités"
tab1, tab2, tab3, tab4 = st.tabs(["📊 Activité", "❤️ Santé", "🏅 Activités", "🤖 Coach"])

with tab1:
    if not df_history.empty:
        fig = px.bar(df_history, x='Date', y='Pas', color='Pas', color_continuous_scale='Blues')
        st.plotly_chart(fig, use_container_width=True)

with tab2:
    if not df_history.empty:
        fig = px.line(df_history, x='Date', y='Body Battery', markers=True, color_discrete_sequence=['#2ecc71'])
        fig.update_layout(yaxis_range=[0, 100])
        st.plotly_chart(fig, use_container_width=True)

# --- NOUVEL ONGLET ACTIVITÉS ---
with tab3:
    st.caption("Vos 5 dernières séances")
    
    if activities:
        for act in activities:
            # Récupération des infos de l'activité
            nom = act['activityName']
            type_act = act['activityType']['typeKey']
            date_start = act['startTimeLocal'][:10] # On garde juste la date YYYY-MM-DD
            duree = format_duration(act['duration'])
            dist_m = act.get('distance', 0)
            
            # Conversion distance (km)
            dist_km = f"{dist_m / 1000:.2f} km" if dist_m else ""
            
            # Fréquence cardiaque moyenne de la séance
            bpm = act.get('averageHR', '--')
            
            icon = get_activity_icon(type_act)
            
            # Affichage sous forme de carte (Expander)
            with st.expander(f"{icon} {date_start} - {nom}"):
                c1, c2, c3 = st.columns(3)
                c1.metric("Durée", duree)
                if dist_m: c2.metric("Distance", dist_km)
                c3.metric("BPM Moy", bpm)
    else:
        st.info("Aucune activité récente trouvée.")

with tab4:
    if st.button("Lancer l'analyse IA"):
        with st.spinner("Analyse..."):
            try:
                client_ai = genai.Client(api_key=st.secrets["GEMINI_KEY"])
                # On ajoute les infos de la dernière activité pour le coach
                last_act = activities[0] if activities else "Aucune activité récente"
                prompt = f"""
                Coach sportif.
                Données jour: Pas={pas}, Sommeil={sommeil_txt}, Stress={stress}, BodyBattery={body_bat}.
                Dernière activité sportive: {last_act}.
                Donne un conseil court.
                """
                response = client_ai.models.generate_content(model="gemini-1.5-flash", contents=prompt)
                st.info(response.text)
            except Exception as e:
                st.error(f"Erreur IA: {e}")
