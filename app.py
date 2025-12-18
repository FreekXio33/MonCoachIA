import streamlit as st
import matplotlib.pyplot as plt
from datetime import date, timedelta
from garminconnect import Garmin
from google import genai
import time

# --- CONFIGURATION DE LA PAGE ---
st.set_page_config(page_title="Mon Coach AI", page_icon="🏃‍♂️")

st.title("🏃‍♂️ Mon Coach AI")
st.write(f"Date : {date.today().strftime('%d/%m/%Y')}")

# --- 1. CONNEXION (SECRETS) ---
# Sur Streamlit Cloud, on ne lit pas un fichier .env mais les "Secrets" du site
try:
    email = st.secrets["GARMIN_EMAIL"]
    password = st.secrets["GARMIN_PASSWORD"]
    api_key_ai = st.secrets["GEMINI_KEY"]
except:
    st.error("⚠️ Les mots de passe ne sont pas configurés dans les Secrets Streamlit.")
    st.stop()

# --- 2. FONCTIONS DE RÉCUPÉRATION ---
@st.cache_data(ttl=3600) # On garde les données en mémoire 1h pour ne pas surcharger Garmin
def get_garmin_data():
    try:
        client = Garmin(email, password)
        client.login()
        
        today = date.today()
        # Récup data du jour
        stats_today = client.get_user_summary(today.isoformat())
        
        # Récup historique 7 jours
        history = []
        labels = []
        full_text = ""
        
        for i in range(6, -1, -1):
            d = today - timedelta(days=i)
            d_str = d.isoformat()
            try:
                data = client.get_user_summary(d_str)
                bpm = data.get('restingHeartRate', 0)
                if bpm is None: bpm = 0
            except:
                bpm = 0
            
            history.append(bpm)
            labels.append(d.strftime("%d/%m"))
            full_text += f"- {d_str}: {bpm} bpm (Repos)\n"
            
        return stats_today, history, labels, full_text
        
    except Exception as e:
        return None, None, None, str(e)

# --- 3. AFFICHAGE ---
with st.spinner('Connexion à votre montre en cours...'):
    stats, history_bpm, labels, text_history = get_garmin_data()

if stats:
    # A. Les Métriques (Gros chiffres)
    col1, col2, col3 = st.columns(3)
    col1.metric("Pas", stats.get('dailySteps', 0))
    col2.metric("Stress", f"{stats.get('averageStressLevel', '--')}/100")
    col3.metric("Cœur Repos", f"{stats.get('restingHeartRate', '--')} bpm")

    # B. Le Graphique
    st.subheader("❤️ Ma semaine (Cœur au repos)")
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(labels, history_bpm, marker='o', color='#FF4B4B', linewidth=2)
    ax.grid(True, linestyle='--', alpha=0.3)
    # Afficher les valeurs sur les points
    for i, v in enumerate(history_bpm):
        if v > 0:
            ax.text(i, v+1, str(int(v)), ha='center')
    st.pyplot(fig)

    # C. L'IA Gemini
    st.subheader("🎙️ L'avis du Coach")
    if st.button("Lancer l'analyse AI"):
        with st.spinner("Le coach réfléchit..."):
            try:
                client_ai = genai.Client(api_key=api_key_ai)
                prompt = f"""
                Agis comme un coach sportif expert.
                Voici mes données cardiaques de la semaine :
                {text_history}
                Données du jour : Pas={stats.get('dailySteps',0)}, Stress={stats.get('averageStressLevel',0)}.
                
                Analyse ma fatigue. Sois court (3 phrases) et motivant.
                """
                response = client_ai.models.generate_content(
                    model="gemini-1.5-flash",
                    contents=prompt
                )
                st.success(response.text)
            except Exception as e:
                st.error(f"Erreur IA : {e}")

else:
    st.error(f"Erreur de connexion Garmin : {text_history}")
