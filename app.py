import streamlit as st
import plotly.express as px
import pydeck as pdk
from datetime import date, timedelta
from garminconnect import Garmin
import google.generativeai as genai
import pandas as pd
import time
import os

# --- CONFIGURATION DE LA PAGE ---
st.set_page_config(page_title="Coach AI", page_icon="⚡", layout="centered")

# --- STYLE CSS (Pour faire joli) ---
hide_streamlit_style = """
            <style>
            #MainMenu {visibility: hidden;}
            footer {visibility: hidden;}
            header {visibility: hidden;}
            .stMetric {background-color: #f0f2f6; padding: 10px; border-radius: 10px;}
            </style>
            """
st.markdown(hide_streamlit_style, unsafe_allow_html=True)

# --- CONFIGURATION IA (Gemini) ---
try:
    # On récupère la clé dans les secrets Streamlit
    api_key = st.secrets["GEMINI_KEY"]
    genai.configure(api_key=api_key)
except Exception as e:
    st.error("⚠️ Clé API non trouvée. Vérifiez vos 'Secrets' dans Streamlit.")

# --- FONCTIONS UTILITAIRES ---
def format_duration(seconds):
    """Convertit des secondes en format h min"""
    if not seconds: return "--"
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    if h > 0: return f"{h}h {m}m"
    return f"{m}m"

def get_activity_icon(type_key):
    """Donne un emoji selon le sport"""
    type_key = str(type_key).lower()
    if "running" in type_key: return "🏃"
    if "cycling" in type_key: return "🚴"
    if "swimming" in type_key: return "🏊"
    if "walking" in type_key: return "🚶"
    return "🏅"

# --- CONNEXION GARMIN ET RÉCUPÉRATION DONNÉES ---
@st.cache_data(ttl=3600)
def get_global_data():
    email = st.secrets["GARMIN_EMAIL"]
    password = st.secrets["GARMIN_PASSWORD"]
    
    client = None
    # Tentative de connexion (3 essais)
    for i in range(3):
        try:
            client = Garmin(email, password)
            client.login()
            break
        except:
            time.sleep(3)
    
    if client is None: return None, "Erreur connexion Garmin", None, None

    try:
        today = date.today()
        # 1. Résumé d'aujourd'hui
        stats_today = client.get_user_summary(today.isoformat())
        
        # 2. Historique récent (7 jours pour les graphiques)
        data_list = []
        for i in range(6, -1, -1):
            d = today - timedelta(days=i)
            try:
                day_data = client.get_user_summary(d.isoformat())
                steps = day_data.get('totalSteps', 0) or day_data.get('dailySteps', 0) or 0
                bb = day_data.get('bodyBatteryMostRecentValue', 0) or day_data.get('bodyBatteryMostRecentLevel', 0) or 0
                data_list.append({"Date": d.strftime("%d/%m"), "Pas": steps, "Body Battery": bb})
            except:
                continue
        
        # 3. Historique Long (depuis Septembre 2025 pour l'IA)
        start_date = date(2025, 9, 1)
        all_activities = client.get_activities_by_date(start_date.isoformat(), today.isoformat())
        
        return stats_today, pd.DataFrame(data_list), all_activities, client
        
    except Exception as e:
        return None, str(e), None, None

# --- FONCTION CARTE GPS ---
def get_gps_data(client, activity_id):
    try:
        details = client.get_activity_details(activity_id)
        # On vérifie si les données GPS existent
        if 'geoPolylineDTO' in details and 'polyline' in details['geoPolylineDTO']:
            raw_points = details['geoPolylineDTO']['polyline']
            # Formatage pour PyDeck
            path_data = [{"path": [[p['longitude'], p['latitude']] for p in raw_points]}]
            # On trouve le centre de la carte
            mid_point = raw_points[len(raw_points)//2]
            center = [mid_point['longitude'], mid_point['latitude']]
            return path_data, center
    except:
        pass
    return None, None

# --- UI PRINCIPALE (L'affichage) ---
st.title("Hey Alexis !")

with st.spinner('Synchronisation avec Garmin...'):
    stats, df_history, activities, client = get_global_data()

# Gestion des erreurs de connexion
if isinstance(df_history, str):
    st.error(f"⚠️ {df_history}")
    if st.button("Recharger"): st.rerun()
    st.stop()

# --- KPI (Indicateurs clés) ---
pas = stats.get('totalSteps', stats.get('dailySteps', 0))
sommeil_sec = stats.get('sleepDurationInSeconds', stats.get('sleepingSeconds', 0))
sommeil_txt = format_duration(sommeil_sec)
stress = stats.get('averageStressLevel', '--')
body_bat = stats.get('bodyBatteryMostRecentValue', stats.get('bodyBatteryMostRecentLevel', '--') )

col1, col2 = st.columns(2)
col1.metric("👣 Pas", pas)
col2.metric("💤 Sommeil", sommeil_txt)
col3, col4 = st.columns(2)
col3.metric("⚡ Stress", f"{stress}/100")
col4.metric("🔋 Body Battery", body_bat)

st.markdown("---")

# --- ONGLETS ---
tab1, tab2, tab3, tab4 = st.tabs(["📊 Activité", "❤️ Santé", "🏅 Cartes", "🤖 Coach AI"])

# Onglet 1 : Graphique des Pas
with tab1:
    if not df_history.empty:
        fig = px.bar(df_history, x='Date', y='Pas', color='Pas', color_continuous_scale='Blues')
        st.plotly_chart(fig, use_container_width=True)

# Onglet 2 : Graphique Santé
with tab2:
    if not df_history.empty:
        fig = px.line(df_history, x='Date', y='Body Battery', markers=True, color_discrete_sequence=['#2ecc71'])
        fig.update_layout(yaxis_range=[0, 100])
        st.plotly_chart(fig, use_container_width=True)

# Onglet 3 : Liste des activités + Cartes GPS
with tab3:
    st.caption("Vos 5 dernières sorties")
    if activities:
        # On boucle sur les 5 dernières activités
        for act in activities[:5]:
            nom = act['activityName']
            act_id = act['activityId']
            type_act = act['activityType']['typeKey']
            
            # C'est ici que l'erreur se produisait : on sécurise la variable date
            date_str = act['startTimeLocal'][:10]
            
            duree = format_duration(act['duration'])
            dist_km = f"{act.get('distance', 0) / 1000:.2f} km"
            icon = get_activity_icon(type_act)
            
            # Création du menu déroulant pour chaque activité
            with st.expander(f"{icon} {date_str} - {nom}"):
                c1, c2 = st.columns(2)
                c1.metric("Distance", dist_km)
                c2.metric("Durée", duree)
                
                # Bouton pour afficher la carte
                if act.get('distance', 0) > 0:
                    if st.button(f"🗺️ Voir la carte", key=f"btn_{act_id}"):
                        path_data, center = get_gps_data(client, act_id)
                        if path_data:
                            view_state = pdk.ViewState(latitude=center[1], longitude=center[0], zoom=12)
                            layer = pdk.Layer(type="PathLayer", data=path_data, get_color=[255, 0, 0], width_scale=20, get_path="path", get_width=5)
                            st.pydeck_chart(pdk.Deck(layers=[layer], initial_view_state=view_state, map_style='light'))
                        else:
                            st.warning("Pas de tracé GPS disponible.")
    else:
        st.info("Aucune activité récente.")

# Onglet 4 : L'Intelligence Artificielle
with tab4:
    st.write("### 🧠 Analyse Gemini 2.5")
    st.write("Le coach analyse tout votre historique depuis Septembre.")
    
    if st.button("Lancer l'analyse du Coach"):
        with st.spinner("Analyse approfondie en cours..."):
            
            # Préparation des données pour l'IA
            resume_activites = ""
            total_km = 0
            
            for act in activities: 
                d_date = act['startTimeLocal'][:10]
                d_type = act['activityType']['typeKey']
                d_km = act.get('distance', 0) / 1000
                d_dur = act.get('duration', 0) // 60
                d_hr = act.get('averageHR', 'N/A')
                
                resume_activites += f"- {d_date}: {d_type} ({d_km:.1f}km, {d_dur}min, FC:{d_hr})\n"
                total_km += d_km

            # Le Prompt (Les instructions au coach)
            prompt = f"""
            Tu es un coach sportif expert de haut niveau.
            
            MES DATAS DU JOUR :
            - Pas : {pas}
            - Sommeil : {sommeil_txt}
            - Stress : {stress}/100
            - Body Battery : {body_bat}/100
            
            MON HISTORIQUE (Total: {total_km:.1f} km) :
            {resume_activites}
            
            TA MISSION :
            1. Analyse ma charge d'entraînement (progression ? fatigue ?).
            2. Commente ma forme du jour.
            3. Donne un conseil précis pour demain.
            
            Ton ton doit être motivant, technique mais concis.
            """

            # Appel au modèle IA (Gemini 2.5 Flash)
            # On utilise le nom exact trouvé précédemment
            try:
                model = genai.GenerativeModel("models/gemini-2.5-flash")
                response = model.generate_content(prompt)
                st.markdown(response.text)
            except Exception as e:
                st.error(f"Erreur IA : {e}")
                # Tentative de secours avec un autre modèle si le 2.5 échoue
                try:
                    st.info("Tentative avec le modèle de secours...")
                    model_fallback = genai.GenerativeModel("models/gemini-2.0-flash")
                    response = model_fallback.generate_content(prompt)
                    st.markdown(response.text)
                except:
                    st.error("Impossible de joindre le coach pour le moment.")
