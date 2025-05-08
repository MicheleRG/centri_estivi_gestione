#cartella/pages/02_Log_Attivita.py
import streamlit as st
from utils.db import get_log_content, log_activity 

st.set_page_config(page_title="Log Attività", layout="wide")

# --- Autenticazione e Controllo Ruolo ---
if 'authentication_status' not in st.session_state or not st.session_state.get('authentication_status'):
    st.warning("Devi effettuare il login per accedere a questa pagina.")
    if st.button("🏠 Vai alla pagina di Login"): st.switch_page("app.py")
    st.stop()

USER_ROLE = st.session_state.get('user_role', 'user')
USERNAME = st.session_state.get('username', 'N/D')
NAME = st.session_state.get('name', 'N/D')
AUTHENTICATOR = st.session_state.get('authenticator')

if not AUTHENTICATOR:
    st.error("Errore di sessione.")
    if st.button("🏠 Riprova Login"): st.switch_page("app.py")
    st.stop()

# Limitare accesso a Controllore e Admin
if USER_ROLE not in ['controllore', 'admin']:
    st.error("Accesso negato. Pagina riservata a Controllori e Amministratori.")
    log_activity(USERNAME, "PAGE_ACCESS_DENIED", "Pagina Log Attività")
    st.stop()

st.sidebar.title(f"Utente: {NAME}")
st.sidebar.write(f"Ruolo: {USER_ROLE.capitalize()}")
AUTHENTICATOR.logout('Logout', 'sidebar')
# --- Fine Autenticazione ---

st.title("📜 Log Attività Utente")
st.markdown("Visualizzazione delle attività recenti registrate (le più recenti per prime).")

if st.button("🔄 Aggiorna Log"):
    log_activity(USERNAME, "LOG_VIEW_REFRESHED") # Logga chi ha aggiornato
    st.toast("Log aggiornato!")
    # Non è necessario st.rerun() qui, get_log_content() viene chiamato sotto

log_data = get_log_content()
st.text_area("Contenuto del Log:", value=log_data, height=600, disabled=True, 
             help="Il log mostra le azioni più recenti in alto.")
#cartella/pages/02_Log_Attivita.py