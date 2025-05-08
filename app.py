#cartella/app.py
import streamlit as st
import pandas as pd
import yaml
from yaml.loader import SafeLoader
import streamlit_authenticator as stauth
# from datetime import datetime # Non più usata direttamente qui
from utils.db import init_db, log_activity # log_activity può essere utile
from utils.common_utils import (
    sanitize_filename_component, convert_df_to_excel_bytes, generate_timestamp_filename,
    parse_excel_currency, validate_rif_pa_format,
    run_detailed_validations # Importa la nuova funzione di validazione centralizzata
)
import os
from io import StringIO
# import numpy as np # Non più usato direttamente qui
# import uuid # Non più usato direttamente qui

# Configurazione pagina
st.set_page_config(page_title="Comunicazione Spese Centri Estivi", layout="wide", initial_sidebar_state="expanded")

# --- Costanti ---
NOMI_COLONNE_PASTED_DATA = [
    'numero_mandato','data_mandato','comune_titolare_mandato','importo_mandato',
    'comune_centro_estivo','centro_estivo','genitore_cognome_nome','bambino_cognome_nome',
    'codice_fiscale_bambino','valore_contributo_fse','altri_contributi',
    'quota_retta_destinatario','totale_retta','numero_settimane_frequenza',
    'controlli_formali_dichiarati' # Colonna 15
]

COLONNE_OUTPUT_FINALE_SIFER = [
    'rif_pa', 'cup', 'distretto', 'comune_capofila', 'numero_mandato', 'data_mandato', 
    'comune_titolare_mandato', 'importo_mandato', 'comune_centro_estivo', 'centro_estivo', 
    'genitore_cognome_nome', 'bambino_cognome_nome', 'codice_fiscale_bambino', # CF pulito e validato
    'valore_contributo_fse', 'altri_contributi', 'quota_retta_destinatario', 'totale_retta', 
    'numero_settimane_frequenza', 'controlli_formali' # Questo sarà il 5% calcolato
]

# --- Funzioni UI ---
def display_login_form():
    """Visualizza il form di login e gestisce l'autenticazione."""
    st.subheader("🔑 Accesso Utente")
    try:
        with open('config.yaml') as file:
            config_data = yaml.load(file, Loader=SafeLoader)
    except FileNotFoundError:
        st.error("🚨 Errore critico: File 'config.yaml' non trovato. L'applicazione non può avviarsi.")
        log_activity("System", "CONFIG_ERROR", "config.yaml not found")
        st.session_state['authentication_status'] = None # Assicura stato non autenticato
        st.stop() # Ferma l'esecuzione
        return None # Teoricamente non raggiunto causa st.stop()
    except yaml.YAMLError as e:
        st.error(f"🚨 Errore critico nel parsing del file 'config.yaml': {e}. Verificare la sintassi del file.")
        log_activity("System", "CONFIG_YAML_ERROR", str(e))
        st.session_state['authentication_status'] = None
        st.stop()
        return None
    except Exception as e: # Cattura altre eccezioni durante il caricamento
        st.error(f"🚨 Errore critico nel caricamento di config.yaml: {e}")
        log_activity("System", "CONFIG_LOAD_ERROR", str(e))
        st.session_state['authentication_status'] = None
        st.stop()
        return None

    try:
        authenticator = stauth.Authenticate(
            config_data['credentials'],
            config_data['cookie']['name'],
            config_data['cookie']['key'],
            config_data['cookie']['expiry_days'],
            # preauthorized=config_data.get('preauthorized', {}) # Opzionale per preautorizzazioni
        )
        st.session_state['authenticator'] = authenticator
    except KeyError as e:
        st.error(f"🚨 Errore nella configurazione di autenticazione: chiave '{e}' mancante in 'config.yaml'.")
        log_activity("System", "AUTH_INIT_CONFIG_KEY_ERROR", str(e))
        st.session_state['authentication_status'] = None
        st.stop()
        return None
    except Exception as e: # Altri errori durante l'init di Authenticate
        st.error(f"🚨 Errore durante l'inizializzazione del sistema di autenticazione: {e}")
        log_activity("System", "AUTH_INIT_ERROR", str(e))
        st.session_state['authentication_status'] = None
        st.stop()
        return None

    name, authentication_status, username = None, None, None
    try:
        # --- MODIFICA QUI ---
        name, authentication_status, username = authenticator.login(
            fields={'Form name': 'Accedi al sistema', 'Username': 'Nome Utente', 'Password': 'Password'},
            location='main'
        )
        # --- FINE MODIFICA ---
    except KeyError as e: # Può accadere con cookie corrotti o problemi di session_state
        st.error(f"⚠️ Errore (KeyError) durante il tentativo di login: '{e}'. Prova a cancellare i cookie del browser e ricaricare la pagina.")
        log_activity("System", "LOGIN_KEY_ERROR", str(e))
        authentication_status = None # Forza stato non autenticato
    except Exception as e_login: # Altri errori imprevisti
        st.error(f"⚠️ Si è verificato un errore generico durante il processo di login: {e_login}")
        log_activity("System", "LOGIN_WIDGET_ERROR", str(e_login))
        authentication_status = None

    st.session_state['authentication_status'] = authentication_status

    if authentication_status is True:
        st.session_state.update({'name': name, 'username': username})
        try:
            user_config = config_data['credentials']['usernames'].get(username, {})
            st.session_state['user_role'] = user_config.get('role', 'user') # Default a 'user' se ruolo non specificato
            log_activity(username, "LOGIN_SUCCESS", f"Role: {st.session_state['user_role']}")
        except KeyError: # Dovrebbe essere già gestito da .get, ma per sicurezza
            st.session_state['user_role'] = 'user' # Fallback sicuro
            log_activity(username, "LOGIN_CONFIG_WARNING", f"Ruolo utente per '{username}' non trovato o errore config, impostato a 'user'.")
            st.warning(f"Configurazione del ruolo utente per '{username}' non trovata o incompleta. Contattare l'amministratore.")
            
    elif authentication_status is False:
        st.error('🚫 Username o password non corretti.')
        if username: # Logga il tentativo fallito solo se è stato inserito un username
            log_activity(username, "LOGIN_FAILED_CREDENTIALS")
        # Non è necessario loggare se authentication_status è None, già gestito sopra
            
    return authentication_status


def render_richiedente_form(username_param: str):
    """Visualizza e gestisce il form per l'utente Richiedente."""
    st.title("📝 Comunicazione Spesa Centri Estivi (Verifica e Download)")
    log_activity(username_param, "PAGE_VIEW", "Richiedente - Verifica e Download")

    st.markdown("""
    Benvenuto! Questa sezione ti permette di:
    1.  Inserire i dati generali del tuo documento (il Rif. PA deve essere nel formato ANNO-OPERAZIONE/RER).
    2.  Copiare e incollare le righe di spesa da un foglio Excel (15 colonne, senza intestazioni).
    3.  Verificare la correttezza formale e sostanziale dei dati.
    4.  Scaricare i dati "normalizzati" e il quadro di controllo.
    """)
    st.info("**Nota:** I dati verificati qui **NON** vengono salvati automaticamente nel database. Dovrai caricare il file CSV scaricato nel sistema SIFER, se previsto dalla procedura.")

    # --- Sezione 1: Metadati Documento ---
    st.subheader("1. Dati Generali del Documento")
    # Inizializzazione stato sessione (già fatta in if __name__ == "__main__")

    with st.expander("Inserisci/Modifica Dati Documento", expanded=not st.session_state.get('metadati_confermati_richiedente', False)):
        with st.form("metadati_documento_form_richiedente"):
            doc_meta = st.session_state.doc_metadati_richiedente # Shortcut
            c1, c2 = st.columns(2)
            rif_pa_input_val = c1.text_input("Rif. PA n° (formato: AAAA-NUMERO/RER)", value=doc_meta.get('rif_pa', ''), key="rich_rifpa_input")
            cup_val = c2.text_input("CUP", value=doc_meta.get('cup', ''), key="rich_cup")
            distretto_val = c1.text_input("Distretto", value=doc_meta.get('distretto', ''), key="rich_distr")
            comune_capofila_val = c2.text_input("Comune/Unione Capofila", value=doc_meta.get('comune_capofila', ''), key="rich_capofila")
            
            metadati_submitted = st.form_submit_button("✅ Conferma Dati Generali")

            if metadati_submitted:
                is_valid_rif, rif_message = validate_rif_pa_format(rif_pa_input_val)
                if is_valid_rif:
                    st.session_state.doc_metadati_richiedente = {
                        'rif_pa': rif_pa_input_val.strip(), 
                        'cup': cup_val.strip(), 
                        'distretto': distretto_val.strip(), 
                        'comune_capofila': comune_capofila_val.strip()
                    }
                    st.session_state.metadati_confermati_richiedente = True
                    st.success(f"Dati generali confermati. {rif_message}")
                    if not all([cup_val, distretto_val, comune_capofila_val]):
                        st.warning("Alcuni campi (CUP, Distretto, Capofila) sono vuoti. Saranno vuoti anche nel file finale.")
                else:
                    st.error(rif_message)
                    st.session_state.doc_metadati_richiedente['rif_pa'] = rif_pa_input_val # Mantieni input per correzione
                    st.session_state.metadati_confermati_richiedente = False 
                
                log_activity(username_param, "METADATA_SUBMITTED_RICHIEDENTE", f"RifPA: {rif_pa_input_val}, Valid: {is_valid_rif}, Dati: {st.session_state.doc_metadati_richiedente}")
                st.rerun() 
                
    if not st.session_state.get('metadati_confermati_richiedente', False):
        st.warning("☝️ Inserisci e conferma i Dati Generali del Documento (con Rif. PA nel formato corretto) per procedere.")
        st.stop()
    else:
        doc_meta_show = st.session_state.doc_metadati_richiedente
        st.markdown(f"**Riferimenti Documento:** Rif. PA: `{doc_meta_show['rif_pa']}`, CUP: `{doc_meta_show.get('cup','N/A')}`, Distr: `{doc_meta_show.get('distretto','N/A')}`, Capofila: `{doc_meta_show.get('comune_capofila','N/A')}`")
    
    st.markdown("---")
    
    # --- Sezione 2: Incolla Dati Spesa ---
    st.subheader("2. Incolla i Dati delle Spese da Excel")
    pasted_data = st.text_area(
        f"Incolla qui le {len(NOMI_COLONNE_PASTED_DATA)} colonne di dati (solo i valori, **NON** le intestazioni):",
        height=200,
        key="pasted_excel_data_richiedente",
        help="Formati data comuni (es. GG/MM/AAAA) e valute (es. 1.234,56 o 1234.56) sono accettati."
    )

    results_container = st.container() 

    if pasted_data:
        try:
            log_activity(username_param, "PASTE_DATA_PROCESSING_RICHIEDENTE", f"Lunghezza dati: {len(pasted_data)} chars")
            
            data_io = StringIO(pasted_data)
            df_pasted_raw = pd.read_csv(data_io, sep='\t', header=None, dtype=str, na_filter=False)

            if df_pasted_raw.shape[1] != len(NOMI_COLONNE_PASTED_DATA):
                results_container.error(f"🚨 Errore: Incollate {df_pasted_raw.shape[1]} colonne, attese {len(NOMI_COLONNE_PASTED_DATA)}. Controlla la selezione da Excel.")
                st.stop()

            df_pasted_raw.columns = NOMI_COLONNE_PASTED_DATA
            df_check = df_pasted_raw.copy()

            # --- Pre-processing e Parsing Tipi ---
            df_check['codice_fiscale_bambino_pulito'] = df_check['codice_fiscale_bambino'].astype(str).str.upper().str.strip()
            
            df_check['data_mandato_originale'] = df_check['data_mandato'] # Conserva originale per messaggi
            df_check['data_mandato'] = pd.to_datetime(df_check['data_mandato_originale'], errors='coerce', dayfirst=True).dt.date

            currency_cols_to_parse = ['importo_mandato','valore_contributo_fse','altri_contributi','quota_retta_destinatario','totale_retta','controlli_formali_dichiarati']
            for col in currency_cols_to_parse:
                if col in df_check.columns:
                    df_check[col] = df_check[col].apply(parse_excel_currency)
                else: # Dovrebbe essere presente se NOMI_COLONNE_PASTED_DATA è corretto
                    results_container.warning(f"Attenzione: colonna valuta attesa '{col}' non trovata nei dati incollati. Sarà trattata come 0.")
                    df_check[col] = 0.0


            df_check['numero_settimane_frequenza'] = df_check['numero_settimane_frequenza'].apply(
                lambda x: int(float(str(x).replace(',','.'))) if pd.notna(x) and str(x).strip().replace('.','',1).replace(',','.',1).isdigit() else 0
            )
            # --- Fine Pre-processing ---

            # --- Esegui Validazioni Dettagliate ---
            df_validation_results, has_blocking_errors_rich = run_detailed_validations(
                df_to_validate=df_check,
                cf_col_clean='codice_fiscale_bambino_pulito',
                original_date_col='data_mandato_originale',
                parsed_date_col='data_mandato',
                declared_formal_controls_col='controlli_formali_dichiarati',
                row_offset_for_messages=1 # Per il richiedente, le righe sono 1-based dall'incollato
            )
            
            results_container.subheader("3. Risultati della Verifica Dati")
            cols_order_results = ['Riga','Bambino','Esito CF','Esito Data Mandato','Esito D=A+B+C','Esito Regole Contr.FSE','Esito Contr.Formali 5%', "Verifica Max 300€ FSE per Bambino (batch)", 'Errori Bloccanti']
            # Assicurati che tutte le colonne esistano in df_validation_results prima di provare a ordinarle/visualizzarle
            actual_cols_to_display = [col for col in cols_order_results if col in df_validation_results.columns]
            if not df_validation_results.empty:
                 results_container.dataframe(df_validation_results[actual_cols_to_display], use_container_width=True, hide_index=True)
            else:
                 results_container.info("Nessun risultato di validazione da mostrare (potrebbe essere un batch vuoto o un errore precedente).")


            if not has_blocking_errors_rich:
                results_container.success("✅ Tutte le verifiche preliminari sono OK. Puoi procedere a scaricare i dati.")
                log_activity(username_param, "VALIDATION_SUCCESS_RICHIEDENTE", f"N. righe: {len(df_check)}")
                
                df_validated_output = df_check.copy()
                # Aggiungi metadati al DataFrame di output
                for key, value in st.session_state.doc_metadati_richiedente.items():
                    df_validated_output[key] = value
                
                # Calcola la colonna finale 'controlli_formali' come 5% del FSE (verità ultima per l'export)
                df_validated_output['controlli_formali'] = round(df_validated_output['valore_contributo_fse'] * 0.05, 2)
                
                # Gestisci colonne CF: usa quella pulita e rinominala
                if 'codice_fiscale_bambino' in df_validated_output.columns: # Colonna originale
                     df_validated_output.drop(columns=['codice_fiscale_bambino'], inplace=True, errors='ignore')
                if 'codice_fiscale_bambino_pulito' in df_validated_output.columns:
                    df_validated_output.rename(columns={'codice_fiscale_bambino_pulito': 'codice_fiscale_bambino'}, inplace=True)

                # Seleziona e ordina colonne per l'output finale SIFER
                df_output_sifer = df_validated_output[[col for col in COLONNE_OUTPUT_FINALE_SIFER if col in df_validated_output.columns]].copy()

                with results_container.expander("⬇️ 4. Anteprima Dati Normalizzati e Download", expanded=True):
                    df_display_anteprima = df_output_sifer.copy()
                    if 'data_mandato' in df_display_anteprima.columns:
                        df_display_anteprima['data_mandato'] = pd.to_datetime(df_display_anteprima['data_mandato'], errors='coerce').dt.strftime('%d/%m/%Y').fillna('')
                    st.dataframe(df_display_anteprima, use_container_width=True, hide_index=True)

                    rif_pa_s = sanitize_filename_component(st.session_state.doc_metadati_richiedente.get('rif_pa',''))
                    
                    df_export_csv = df_output_sifer.copy()
                    if 'data_mandato' in df_export_csv.columns:
                        df_export_csv['data_mandato'] = pd.to_datetime(df_export_csv['data_mandato'], errors='coerce').dt.strftime('%d/%m/%Y').fillna('')
                    
                    csv_output_bytes = df_export_csv.to_csv(index=False, sep=';', decimal=',', encoding='utf-8-sig').encode('utf-8-sig')
                    fn_csv = generate_timestamp_filename(type_prefix="datiSIFER", rif_pa_sanitized=rif_pa_s) + ".csv"
                    st.download_button(label="📥 Scarica CSV per SIFER", data=csv_output_bytes, file_name=fn_csv, mime='text/csv', key="rich_dl_csv")
                    
                    excel_output_bytes = convert_df_to_excel_bytes(df_output_sifer) # Passa il df con oggetti date per Excel
                    fn_excel = generate_timestamp_filename(type_prefix="datiSIFER_Excel", rif_pa_sanitized=rif_pa_s) + ".xlsx"
                    st.download_button(label="📄 Scarica Excel", data=excel_output_bytes, file_name=fn_excel, mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key="rich_dl_excel")

                with results_container.expander("📊 5. Quadro di Controllo (Calcolato)", expanded=True):
                    tot_A_fse = df_output_sifer['valore_contributo_fse'].sum()
                    tot_controlli_formali_calc = df_output_sifer['controlli_formali'].sum() # Usa colonna ricalcolata
                    # tot_B_altri_contrib = df_output_sifer['altri_contributi'].sum() # Non richiesto nel quadro fornito
                    tot_C_quota_dest = df_output_sifer['quota_retta_destinatario'].sum()
                    tot_contrib_complessivo_per_qc = tot_A_fse + tot_controlli_formali_calc # A + 5% di A

                    quadro_data = {
                        "Voce": ["Totale costi diretti (A - Contributo FSE)", 
                                 "Quota costi indiretti (5% di A - calcolata)", 
                                 "Contributo complessivo erogabile (A + 5% di A)", 
                                 "Totale quote a carico del destinatario (C)"],
                        "Valore (€)": [tot_A_fse, tot_controlli_formali_calc, tot_contrib_complessivo_per_qc, tot_C_quota_dest]
                    }
                    df_qc = pd.DataFrame(quadro_data)
                    
                    df_qc_display = df_qc.copy()
                    df_qc_display["Valore (€)"] = df_qc_display["Valore (€)"].apply(lambda x: f"{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")) # Formattazione IT
                    st.dataframe(df_qc_display, hide_index=True, use_container_width=True)

                    csv_qc_bytes = df_qc.to_csv(index=False, sep=';', decimal=',', encoding='utf-8-sig').encode('utf-8-sig')
                    fn_qc_csv = generate_timestamp_filename(type_prefix="QuadroControllo", rif_pa_sanitized=rif_pa_s, include_seconds=False) + ".csv"
                    st.download_button(label="📥 Scarica Quadro CSV", data=csv_qc_bytes, file_name=fn_qc_csv, mime='text/csv', key="rich_qc_csv")

                    excel_qc_bytes = convert_df_to_excel_bytes(df_qc)
                    fn_qc_excel = generate_timestamp_filename(type_prefix="QuadroControllo_Excel", rif_pa_sanitized=rif_pa_s, include_seconds=False) + ".xlsx"
                    st.download_button(label="📄 Scarica Quadro Excel", data=excel_qc_bytes, file_name=fn_qc_excel, mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key="rich_qc_excel")
            
            elif df_validation_results.empty and not pasted_data.strip(): # Se non ci sono dati incollati ma pasted_data non è vuoto (es. solo spazi)
                results_container.info("Nessun dato valido incollato da elaborare.")
            else: # Se ci sono errori bloccanti
                 results_container.error("🚫 Sono stati rilevati errori bloccanti (contrassegnati con ❌). Correggere i dati e reincollare.")
                 log_activity(username_param, "VALIDATION_FAILED_RICHIEDENTE", "Errori bloccanti rilevati.")
        
        except pd.errors.EmptyDataError: 
             results_container.warning("⚠️ Nessun dato da elaborare. Assicurati di aver incollato i dati correttamente.")
        except ValueError as ve: # Errori di conversione non gestiti prima
             results_container.error(f"🚨 Errore nella conversione dei dati: {ve}. Controlla il formato delle date e dei numeri.")
             log_activity(username_param, "PARSING_ERROR_RICHIEDENTE", str(ve))
        except Exception as e: 
             results_container.error(f"🚨 Errore imprevisto durante l'elaborazione: {e}")
             log_activity(username_param, "PROCESSING_ERROR_RICHIEDENTE", str(e))
             st.exception(e) # Mostra traceback completo per debug in Streamlit


def main_app_router():
    """Gestisce la navigazione e visualizza la pagina appropriata in base al ruolo."""
    # Recupera info utente da session_state
    user_role = st.session_state.get('user_role', 'user') # Default a 'user'
    username = st.session_state.get('username', 'N/D')
    name = st.session_state.get('name', 'Utente')
    authenticator_obj = st.session_state.get('authenticator')

    if not authenticator_obj: # Controllo critico
        st.error("🚨 Sessione di autenticazione non valida o scaduta. Effettua nuovamente il login.")
        st.session_state['authentication_status'] = None # Forza logout logico
        if st.button("🔄 Ricarica e Vai al Login"):
            st.rerun() # Ricarica l'app, che dovrebbe portare al login
        st.stop()
        return

    # Sidebar Utente e Logout (comune a tutte le pagine post-login)
    st.sidebar.title(f"👤 Utente: {name}")
    st.sidebar.write(f"🔖 Ruolo: {user_role.capitalize()}")
    authenticator_obj.logout('🚪 Logout', 'sidebar', key='main_logout_btn') # Chiave univoca

    # Routing basato sul ruolo
    if user_role == 'richiedente':
        render_richiedente_form(username)
    elif user_role in ['controllore', 'admin']:
        # Per Controllore/Admin, le funzionalità sono nelle pagine dedicate.
        # Questa è la pagina "Home" dopo il login per loro.
        st.success(f"Benvenuto/a {name}! Sei autenticato/a come {user_role.capitalize()}.")
        st.info("Seleziona un'opzione dalla navigazione laterale (nelle sezioni 'pages') per accedere alle funzionalità specifiche del tuo ruolo.")
        st.markdown("---")
        st.markdown("#### Pagine disponibili nel menu laterale ↖️")
        # Si potrebbero elencare qui le pagine accessibili, ma Streamlit già le mostra.
    else:
        st.error("🚫 Ruolo utente non riconosciuto o non autorizzato. Contattare l'amministratore.")
        log_activity(username, "UNKNOWN_ROLE_ACCESS", f"Ruolo: {user_role}")

# --- Blocco Esecuzione Principale ---
if __name__ == "__main__":
    # 1. Inizializzazione Database (una sola volta all'avvio)
    # Assicura esistenza cartella database
    os.makedirs("database", exist_ok=True, mode=0o755) 
    try:
        init_db() # Chiamata centralizzata
        log_activity("System", "APP_STARTUP", "Database inizializzato con successo.")
    except Exception as e_db:
        st.error(f"🚨 Errore critico durante l'inizializzazione del database: {e_db}")
        log_activity("System", "DB_INIT_ERROR", str(e_db))
        st.stop() # Impossibile procedere senza DB

    # 2. Inizializzazione `session_state` (chiavi di default)
    # Deve avvenire prima di qualsiasi tentativo di accesso a queste chiavi
    default_session_keys = {
        'authentication_status': None, 'name': None, 'username': None, 
        'authenticator': None, 'user_role': None,
        'doc_metadati_richiedente': {'rif_pa': '', 'cup': '', 'distretto': '', 'comune_capofila': ''},
        'metadati_confermati_richiedente': False,
        # Aggiungere qui altre chiavi di session_state globali o per altre pagine se necessario,
        # ma è meglio inizializzare le chiavi specifiche della pagina all'interno della pagina stessa
        # o usare prefissi per evitare conflitti.
    }
    for key, default_value in default_session_keys.items():
        st.session_state.setdefault(key, default_value)

    # 3. Gestione Flusso di Autenticazione e Visualizzazione
    if not st.session_state.get('authentication_status'):
        auth_status = display_login_form()
        # Se il login non ha successo (False o None), display_login_form potrebbe aver chiamato st.stop()
        # o lo stato di autenticazione non è True.
        if not auth_status: # auth_status è True, False, o None
            st.stop() # Assicura che l'app si fermi se non autenticato o errore login.
    
    # Se l'utente è autenticato (authentication_status è True), esegui il router principale
    # Questo blocco viene eseguito solo se authentication_status è True.
    if st.session_state.get('authentication_status') is True: 
        main_app_router()
    # Se authentication_status è None o False e st.stop() non è stato chiamato prima,
    # l'app si fermerà qui implicitamente perché non c'è altro da eseguire.
#cartella/app.py