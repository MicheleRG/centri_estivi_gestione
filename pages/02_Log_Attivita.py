#cartella/pages/02_Log_Attivita.py
import streamlit as st
from utils.db import get_log_content, log_activity 

st.set_page_config(page_title="Log Attività", layout="wide")

# --- Autenticazione e Controllo Ruolo ---
if not st.session_state.get('authentication_status', False):
    st.warning("Devi effettuare il login per accedere a questa pagina.")
    if st.button("🏠 Vai alla pagina di Login", key="log_login_btn_redir"):
        st.switch_page("app.py")
    st.stop()

USER_ROLE_LOG = st.session_state.get('user_role')
USERNAME_LOG = st.session_state.get('username')
NAME_LOG = st.session_state.get('name')
AUTHENTICATOR_LOG = st.session_state.get('authenticator')

if not AUTHENTICATOR_LOG:
    st.error("🚨 Errore di sessione. Riprova il login.")
    if st.button("🏠 Riprova Login", key="log_login_btn_no_auth"):
        st.switch_page("app.py")
    st.stop()

if USER_ROLE_LOG not in ['controllore', 'admin']:
    st.error("🚫 Accesso negato. Pagina riservata a Controllori e Amministratori.")
    log_activity(USERNAME_LOG, "PAGE_ACCESS_DENIED", "Tentativo accesso a Pagina Log Attività")
    st.stop()

st.sidebar.title(f"👤 Utente: {NAME_LOG}")
st.sidebar.write(f"🔖 Ruolo: {USER_ROLE_LOG.capitalize()}")
AUTHENTICATOR_LOG.logout('🚪 Logout', 'sidebar', key='log_logout_sidebar')
# --- Fine Autenticazione ---

st.title("📜 Log Attività Utente")
st.markdown("Visualizzazione delle attività recenti registrate nel sistema (le più recenti per prime).")

if st.button("🔄 Aggiorna Visualizzazione Log", key="refresh_log_btn"):
    log_activity(USERNAME_LOG, "LOG_VIEW_REFRESHED", "L'utente ha aggiornato la visualizzazione del log.")
    st.toast("Visualizzazione del log aggiornata!", icon="🔄")
    # st.rerun() # Non strettamente necessario se get_log_content() viene chiamato sotto e l'output cambia

try:
    log_data_content = get_log_content()
    st.text_area(
        "Contenuto del Log:", 
        value=log_data_content, 
        height=600, 
        disabled=True, 
        help="Il log mostra le azioni più recenti in alto. Il file di log ruota per dimensione."
    )
except Exception as e_log_display:
    st.error(f"Impossibile visualizzare il log: {e_log_display}")
    log_activity(USERNAME_LOG, "LOG_DISPLAY_ERROR", str(e_log_display))

#cartella/pages/02_Log_Attivita.py