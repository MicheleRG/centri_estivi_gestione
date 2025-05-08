#cartella/pages/03_Admin_Settings.py
import streamlit as st
from utils.db import log_activity # Rimosso get_setting, update_setting

st.set_page_config(page_title="Impostazioni Admin", layout="centered")

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

if USER_ROLE != 'admin':
    st.error("Accesso negato. Pagina riservata agli Amministratori.")
    log_activity(USERNAME, "ADMIN_SETTINGS_ACCESS_DENIED")
    st.stop()

st.sidebar.title(f"Utente: {NAME}")
st.sidebar.write(f"Ruolo: {USER_ROLE.capitalize()}")
AUTHENTICATOR.logout('Logout', 'sidebar')
# --- Fine Autenticazione ---

st.title("🛠️ Impostazioni Amministratore")
log_activity(USERNAME, "PAGE_VIEW", "Admin Settings")

st.info("Questa sezione è riservata alle impostazioni di sistema per l'amministratore.")
st.markdown("---")

# Le opzioni 'allow_data_modification' e 'allow_data_deletion' sono state rimosse
# perché la logica di modifica/eliminazione è ora gestita dai ruoli e dalle funzionalità specifiche.

st.subheader("Gestione Utenti (Esempio Platzhalter)")
st.markdown("""
Attualmente, la gestione degli utenti (creazione, modifica password, cambio ruolo) 
deve essere effettuata modificando direttamente il file `config.yaml` e 
generando le password hashate con lo script `hash_password.py`.

Per il futuro, si potrebbe integrare qui un'interfaccia per:
- Visualizzare gli utenti esistenti.
- Registrare nuovi utenti (con generazione automatica di password hashata).
- Modificare i dettagli degli utenti (es. nome, email, ruolo).
- Reimpostare le password.
""")
st.markdown("---")
st.caption("Non ci sono impostazioni modificabili da questa interfaccia al momento.")

# Se si volesse gestire la cancellazione del file di log o altre impostazioni, andrebbero qui.

#cartella/pages/03_Admin_Settings.py