import streamlit as st
import plotly.express as px
import pydeck as pdk
from datetime import date, timedelta
from garminconnect import Garmin
import google.generativeai as genai
import pandas as pd
import time
import os

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

# --- CONFIGURATION IA SÉCURISÉE ---
try:
    api_key = st.secrets["GEMINI_KEY"]
    genai.configure(api_key=api_key)
except Exception as e:
    st.error("⚠️ Clé API non trouvée dans les secrets.")

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
            d_str = d.isoformat()
            try:
                day_data = client.get_user_summary(d_str)
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

# --- UI PRINCIPALE ---
st.title("Hey Alexis !")
with st.spinner('Synchronisation Garmin...'):
    stats, df_history, activities, client = get_global_data()

if isinstance(df_history, str):
    st.error(f"⚠️ {df_history}")
    if st.button("Recharger"): st.rerun()
    st.stop()

# KPIS
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

tab1, tab2, tab3, tab4 = st.tabs(["📊 Activité", "❤️ Santé", "🏅 Cartes & Sport", "🤖 Coach"])

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
    st.caption("Vos 5 dernières séances")
    if activities:
        recent_activities = activities[:5] 
        for act in recent_activities:
            nom = act['activityName']
            act_id = act['activityId']
            type_act = act['activityType']['typeKey']
            date_start = act['startTimeLocal'][:10]
            duree = format_duration(act['duration'])
            dist_km = f"{act.get('distance', 0) / 1000:.2f} km" if act.get('distance') else ""
            icon = get_activity_icon(type_act)
            with st.expander(f"{icon} {date_start} - {nom}"):
                c1, c2, c3 = st.columns(3)
                c1.metric("Durée", duree)
                c2.metric("Distance", dist_km)
                c3.metric("BPM", act.get('averageHR', '--'))
                if act.get('distance', 0) > 0:
                    if st.button(f"🗺️ Voir le parcours", key=f"btn_{act_id}"):
                        with st.spinner("Téléchargement du tracé GPS..."):
                            path_data, center = get_gps_data(client, act_id)
                            if path_data:
                                view_state = pdk.ViewState(latitude=center[1], longitude=center[0], zoom=11, pitch=0)
                                layer = pdk.Layer(type="PathLayer", data=path_data, pickable=True, get_color=[255, 75, 75], width_scale=20, width_min_pixels=2, get_path="path", get_width=5)
                                r = pdk.Deck(layers=[layer], initial_view_state=view_state, map_style='light')
                                st.pydeck_chart(r)
                            else:
                                st.warning("Pas de données GPS.")
    else:
        st.info("Aucune activité trouvée.")

with tab4:
    st.header("🔍 Diagnostic IA")
    
    if st.button("Quels modèles sont disponibles pour ma clé ?"):
        try:
            st.info("Interrogation des serveurs Google en cours...")
            
            # On demande la liste officielle
            available_models = []
            for m in genai.list_models():
                if 'generateContent' in m.supported_generation_methods:
                    available_models.append(m.name)
            
            if available_models:
                st.success("✅ Connexion réussie ! Voici les noms exacts à utiliser :")
                st.code("\n".join(available_models))
                st.write("Copiez l'un de ces noms (de préférence celui qui contient 'flash') pour le mettre dans le code.")
            else:
                st.warning("Aucun modèle trouvé compatible avec generateContent.")
                
        except Exception as e:
            st.error(f"Erreur de connexion : {e}")
            st.write("Vérifiez que votre clé API est bien une clé 'Google AI Studio' et non une clé 'Google Cloud Vertex' (qui nécessite une configuration différente).")
