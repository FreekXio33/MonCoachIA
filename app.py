import streamlit as st
import plotly.express as px
from datetime import date, timedelta
from garminconnect import Garmin
from google import genai
import pandas as pd # Pour gérer les tableaux de données facilement

# --- CONFIGURATION (MODE APP MOBILE) ---
st.set_page_config(page_title="Coach AI", page_icon="⚡", layout="centered")

# CSS pour cacher les menus et faire "App native"
hide_streamlit_style = """
            <style>
            #MainMenu {visibility: hidden;}
            footer {visibility: hidden;}
            header {visibility: hidden;}
            </style>
            """
st.markdown(hide_streamlit_style, unsafe_allow_html=True)

# --- FONCTIONS ---
@st.cache_data(ttl=3600)
def get_data():
    try:
        email = st.secrets["GARMIN_EMAIL"]
        password = st.secrets["GARMIN_PASSWORD"]
        client = Garmin(email, password)
        client.login()
        
        today = date.today()
        # Données du jour
        stats_today = client.get_user_summary(today.isoformat())
        
        # Historique 7 jours
        data_list = []
        for i in range(6, -1, -1):
            d = today - timedelta(days=i)
            d_str = d.isoformat()
            try:
                # On récupère tout
                day_data = client.get_user_summary(d_str)
                # On sécurise les valeurs (si nulles)
                data_list.append({
                    "Date": d.strftime("%d/%m"),
                    "Pas": day_data.get('dailySteps', 0) or 0,
                    "Cœur Repos": day_data.get('restingHeartRate', 0) or 0,
                    "Stress": day_data.get('averageStressLevel', 0) or 0,
                    "Body Battery": day_data.get('bodyBatteryMostRecentLevel', 0) or 0
                })
            except:
                continue
                
        return stats_today, pd.DataFrame(data_list) # On retourne un tableau Pandas
    except Exception as e:
        return None, str(e)

# --- CHARGEMENT ---
st.title(f"⚡ Mon Coach - {date.today().strftime('%d/%m')}")

with st.spinner('Synchronisation Garmin...'):
    stats, df_history = get_data()

if isinstance(df_history, str): # Si erreur
    st.error(f"Erreur de connexion : {df_history}")
    st.stop()

# --- INTERFACE PAR ONGLETS ---
tab1, tab2, tab3 = st.tabs(["📊 Vue d'ensemble", "❤️ Santé & Stress", "🤖 Le Coach"])

# --- ONGLET 1 : VUE D'ENSEMBLE ---
with tab1:
    # Les gros indicateurs (KPI)
    col1, col2 = st.columns(2)
    col1.metric("👣 Pas du jour", stats.get('dailySteps', 0), delta_color="normal")
    col2.metric("🔋 Body Battery", f"{stats.get('bodyBatteryMostRecentLevel', '--')}%")
    
    col3, col4 = st.columns(2)
    col3.metric("🔥 Calories", f"{stats.get('totalKilocalories', 0)}")
    col4.metric("💤 Sommeil", f"{stats.get('sleepDurationInSeconds', 0)//3600}h")

    st.markdown("---")
    st.subheader("Semaine d'activité")
    
    # Graphique interactif (Barres)
    fig_steps = px.bar(df_history, x='Date', y='Pas', color='Pas', 
                       color_continuous_scale='Blues')
    fig_steps.update_layout(showlegend=False, margin=dict(l=0, r=0, t=0, b=0))
    st.plotly_chart(fig_steps, use_container_width=True)

# --- ONGLET 2 : SANTÉ & STRESS ---
with tab2:
    st.subheader("❤️ Fréquence Cardiaque (Repos)")
    # Courbe Rouge
    fig_hr = px.line(df_history, x='Date', y='Cœur Repos', markers=True, 
                     line_shape='spline', color_discrete_sequence=['#FF4B4B'])
    fig_hr.update_yaxes(range=[40, 80]) # Zoom automatique sur la zone intéressante
    st.plotly_chart(fig_hr, use_container_width=True)
    
    st.subheader("⚡ Niveau de Stress")
    # Zone colorée
    fig_stress = px.area(df_history, x='Date', y='Stress', 
                         color_discrete_sequence=['orange'])
    fig_stress.update_yaxes(range=[0, 100])
    st.plotly_chart(fig_stress, use_container_width=True)

# --- ONGLET 3 : LE COACH IA ---
with tab3:
    st.info("Le coach analyse votre Body Battery et votre stress.")
    
    if st.button("🎙️ Lancer l'analyse"):
        with st.spinner("Analyse du physiologiste en cours..."):
            try:
                client_ai = genai.Client(api_key=st.secrets["GEMINI_KEY"])
                
                # On prépare un résumé textuel des données pour l'IA
                resume_semaine = df_history.to_string(index=False)
                
                prompt = f"""
                Tu es un coach sportif expert. Analyse mes données :
                {resume_semaine}
                
                Données du jour : Body Battery {stats.get('bodyBatteryMostRecentLevel')}, Pas {stats.get('dailySteps')}.
                
                1. Donne un bilan global de ma fatigue (basé sur le Stress et la Body Battery).
                2. Donne un conseil précis pour demain.
                3. Sois bref, tutoie-moi, utilise des emojis.
                """
                
                response = client_ai.models.generate_content(
                    model="gemini-1.5-flash",
                    contents=prompt
                )
                st.markdown(response.text)
                
            except Exception as e:
                st.error(f"Erreur IA : {e}")
