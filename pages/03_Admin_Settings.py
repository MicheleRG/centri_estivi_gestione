#cartella/pages/03_Admin_Settings.py
import streamlit as st
from utils.db import log_activity 

st.set_page_config(page_title="Impostazioni Admin", layout="centered")

# --- Autenticazione e Controllo Ruolo ---
if not st.session_state.get('authentication_status', False):
    st.warning("Devi effettuare il login per accedere a questa pagina.")
    if st.button("🏠 Vai alla pagina di Login", key="admin_login_btn_redir"):
        st.switch_page("app.py")
    st.stop()

USER_ROLE_ADMIN_PAGE = st.session_state.get('user_role')
USERNAME_ADMIN_PAGE = st.session_state.get('username')
NAME_ADMIN_PAGE = st.session_state.get('name')
AUTHENTICATOR_ADMIN_PAGE = st.session_state.get('authenticator')

if not AUTHENTICATOR_ADMIN_PAGE:
    st.error("🚨 Errore di sessione. Riprova il login.")
    if st.button("🏠 Riprova Login", key="admin_login_btn_no_auth"):
        st.switch_page("app.py")
    st.stop()

if USER_ROLE_ADMIN_PAGE != 'admin':
    st.error("🚫 Accesso negato. Questa pagina è riservata esclusivamente agli Amministratori.")
    log_activity(USERNAME_ADMIN_PAGE, "PAGE_ACCESS_DENIED", "Tentativo accesso a Admin Settings")
    st.stop()

st.sidebar.title(f"👤 Utente: {NAME_ADMIN_PAGE}")
st.sidebar.write(f"🔖 Ruolo: {USER_ROLE_ADMIN_PAGE.capitalize()}")
AUTHENTICATOR_ADMIN_PAGE.logout('🚪 Logout', 'sidebar', key='admin_logout_sidebar')
# --- Fine Autenticazione ---

st.title("🛠️ Impostazioni Amministratore")
log_activity(USERNAME_ADMIN_PAGE, "PAGE_VIEW", "Admin Settings")

st.info("Questa sezione è riservata alle impostazioni di sistema per l'amministratore.")
st.markdown("---")

st.subheader("Gestione Utenti")
st.markdown("""
La gestione degli utenti (creazione, modifica password, cambio ruolo) avviene attualmente attraverso:
1.  Modifica manuale del file `config.yaml`.
2.  Generazione delle password hashate tramite lo script `hash_password.py` (da eseguire localmente o sul server).

**Per il futuro, si potrebbe integrare un'interfaccia utente direttamente qui per:**
- Visualizzare gli utenti esistenti (senza mostrare le password hashate).
- Registrare nuovi utenti (con generazione automatica di password hashata e aggiunta a `config.yaml` - richiede permessi di scrittura sul file).
- Modificare i dettagli degli utenti (es. nome, email, ruolo - richiede riscrittura di `config.yaml`).
- Invalidare/Reimpostare le password.

**Nota sulla sicurezza:** La modifica programmatica di `config.yaml` da un'app web richiede attenzione particolare ai permessi e alla sicurezza per prevenire accessi non autorizzati o modifiche malevole.
""")
st.markdown("---")

st.subheader("Altre Impostazioni")
st.caption("Al momento non ci sono altre impostazioni di sistema configurabili da questa interfaccia.")
st.markdown("""
Eventuali future impostazioni globali dell'applicazione (es. limiti, parametri di default, modalità di manutenzione) potrebbero essere gestite qui.
""")
# Esempio di come potrebbe essere un'impostazione (attualmente non attiva):
# allow_new_registrations = st.checkbox("Consenti nuove registrazioni utenti (placeholder)")
# if allow_new_registrations:
#    st.write("Logica per gestire nuove registrazioni...")

log_activity(USERNAME_ADMIN_PAGE, "ADMIN_SETTINGS_NO_OPTS_DISPLAYED")
#cartella/pages/03_Admin_Settings.py
