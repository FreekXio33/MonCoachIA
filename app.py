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

# --- STYLE CSS ---
hide_streamlit_style = """
            <style>
            #MainMenu {visibility: hidden;}
            footer {visibility: hidden;}
            header {visibility: hidden;}
            .stMetric {background-color: #f0f2f6; padding: 10px; border-radius: 10px;}
            /* Style pour le nouvel onglet */
            .stTextArea textarea {font-size: 16px !important;}
            </style>
            """
st.markdown(hide_streamlit_style, unsafe_allow_html=True)

# --- CONFIGURATION IA ---
try:
    api_key = st.secrets["GEMINI_KEY"]
    genai.configure(api_key=api_key)
except Exception as e:
    st.error("⚠️ Clé API non trouvée.")

# --- FONCTIONS UTILITAIRES ---
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

# --- CONNEXION GARMIN ---
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
        except:
            time.sleep(3)
    
    if client is None: return None, "Erreur connexion Garmin", None, None

    try:
        today = date.today()
        stats_today = client.get_user_summary(today.isoformat())
        
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
        
        start_date = date(2025, 9, 1)
        all_activities = client.get_activities_by_date(start_date.isoformat(), today.isoformat())
        
        return stats_today, pd.DataFrame(data_list), all_activities, client
        
    except Exception as e:
        return None, str(e), None, None

# --- GPS ---
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

# --- UI PRINCIPALE ---
st.title("Hey Alexis !")

with st.spinner('Synchronisation...'):
    stats, df_history, activities, client = get_global_data()

if isinstance(df_history, str):
    st.error(f"⚠️ {df_history}")
    if st.button("Recharger"): st.rerun()
    st.stop()

# --- KPI ---
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

# --- AJOUT DU NOUVEL ONGLET DANS LA LISTE ---
tab1, tab2, tab3, tab4, tab5 = st.tabs(["📊 Activité", "❤️ Santé", "🏅 Cartes", "🤖 Coach", "📅 Créateur"])

with tab1:
    if not df_history.empty:
        fig = px.bar(df_history, x='Date', y='Pas', color='Pas', color_continuous_scale='Blues')
        st.plotly_chart(fig, use_container_width=True)

with tab2:
    if not df_history.empty:
        fig = px.line(df_history, x='Date', y='Body Battery', markers=True, color_discrete_sequence=['#2ecc71'])
        fig.update_layout(yaxis_range=[0, 100])
        st.plotly_chart(fig, use_container_width=True)

with tab3:
    st.caption("Dernières sorties")
    if activities:
        for act in activities[:5]:
            nom = act['activityName']
            act_id = act['activityId']
            type_act = act['activityType']['typeKey']
            date_str = act['startTimeLocal'][:10]
            duree = format_duration(act['duration'])
            dist = f"{act.get('distance', 0) / 1000:.2f} km"
            icon = get_activity_icon(type_act)
            
            with st.expander(f"{icon} {date_str} - {nom}"):
                c1, c2 = st.columns(2)
                c1.metric("Distance", dist)
                c2.metric("Durée", duree)
                if act.get('distance', 0) > 0:
                    if st.button(f"🗺️ Carte", key=f"btn_{act_id}"):
                        path, center = get_gps_data(client, act_id)
                        if path:
                            view = pdk.ViewState(latitude=center[1], longitude=center[0], zoom=12)
                            layer = pdk.Layer(type="PathLayer", data=path, get_color=[255, 0, 0], width_scale=20, get_path="path", get_width=5)
                            st.pydeck_chart(pdk.Deck(layers=[layer], initial_view_state=view, map_style='light'))
    else:
        st.info("Rien à afficher.")

with tab4:
    st.write("### 🧠 Analyse de Saison")
    if st.button("Analyser mon historique"):
        with st.spinner("Le coach épluche vos données..."):
            resume_activites = ""
            total_km = 0
            for act in activities: 
                d = act['startTimeLocal'][:10]
                t = act['activityType']['typeKey']
                km = act.get('distance', 0) / 1000
                hr = act.get('averageHR', 'N/A')
                resume_activites += f"- {d}: {t} ({km:.1f}km, FC:{hr})\n"
                total_km += km

            prompt = f"""
            Tu es un coach sportif expert.
            MES DATAS : Pas:{pas}, Sommeil:{sommeil_txt}, Stress:{stress}, BodyBattery:{body_bat}.
            HISTORIQUE ({total_km:.1f} km) : {resume_activites}
            1. Analyse ma charge. 2. Forme du jour. 3. Conseil futur.
            """
            try:
                model = genai.GenerativeModel("models/gemini-2.5-flash")
                response = model.generate_content(prompt)
                st.markdown(response.text)
            except Exception as e:
                st.error(f"Erreur IA : {e}")

# --- LE NOUVEL ONGLET : CRÉATEUR DE SÉANCE ---
with tab5:
    st.write("### 📅 Générateur de Séance sur Mesure")
    st.caption("Je crée une séance adaptée à votre forme du jour (Body Battery).")
    
    # Formulaire de demande
    c1, c2 = st.columns(2)
    sport_target = c1.selectbox("Quel sport ?", ["Course à pied", "Vélo de route", "Gravel", "Musculation", "Natation"])
    duree_target = c2.slider("Durée disponible (min)", 30, 180, 60, step=15)
    
    type_seance = st.text_input("Envie spécifique ? (ex: VMA, Endurance, Seuil, Récup)", placeholder="Laisse vide pour que je décide...")

    if st.button("🏃 Générer ma séance"):
        with st.spinner("Calcul de la séance optimale..."):
            
            # On construit un prompt intelligent qui prend en compte la fatigue
            prompt_seance = f"""
            Tu es mon coach sportif personnel.
            
            MA FORME ACTUELLE (Très important) :
            - Body Battery : {body_bat}/100 (Si < 30 : propose une séance cool. Si > 80 : tu peux charger).
            - Sommeil cette nuit : {sommeil_txt}
            - Stress aujourd'hui : {stress}/100
            
            MA DEMANDE :
            - Sport : {sport_target}
            - Durée : {duree_target} minutes
            - Objectif spécifique : {type_seance if type_seance else "A toi de décider selon ma forme"}
            
            TA MISSION :
            Crée une séance structurée et détaillée.
            Format attendu :
            1. **Échauffement** (durée et intensité)
            2. **Corps de séance** (séries, répétitions, zones de FC ou Allure)
            3. **Retour au calme**
            4. **Conseil technique** pour cette séance.
            
            Utilise des tableaux Markdown si besoin pour la clarté.
            """
            
            try:
                model_seance = genai.GenerativeModel("models/gemini-2.5-flash")
                response_seance = model_seance.generate_content(prompt_seance)
                
                # Affichage joli
                st.success("✅ Voici ta séance :")
                st.markdown(response_seance.text)
                
            except Exception as e:
                st.error(f"Oups, le coach a trébuché : {e}")
