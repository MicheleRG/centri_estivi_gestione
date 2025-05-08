#cartella/pages/01_Gestione_Dati_Controllore.py
import streamlit as st
import pandas as pd
from utils.db import add_multiple_spese, log_activity, check_rif_pa_exists
from utils.common_utils import (
    # sanitize_filename_component, convert_df_to_excel_bytes, generate_timestamp_filename, # Non usati qui
    parse_excel_currency, validate_rif_pa_format,
    run_detailed_validations # Importa la funzione di validazione centralizzata
)
import uuid # Per generare id_trasmissione

st.set_page_config(page_title="Gestione Dati Controllore", layout="wide")

# --- Costanti Specifiche Pagina ---
DB_COLS_ATTESE = [
    'id_trasmissione', 'rif_pa', 'cup', 'distretto', 'comune_capofila', 
    'numero_mandato', 'data_mandato', 'comune_titolare_mandato', 'importo_mandato',
    'comune_centro_estivo', 'centro_estivo', 'genitore_cognome_nome', 
    'bambino_cognome_nome', 'codice_fiscale_bambino', 'valore_contributo_fse', 
    'altri_contributi', 'quota_retta_destinatario', 'totale_retta', 
    'numero_settimane_frequenza', 'controlli_formali' # Calcolati e finali
]
# Colonne che potrebbero essere nel CSV e che non vanno direttamente nel DB o sono trasformate
COLS_DA_RIMUOVERE_PER_DB = ['cf_pulito', 'data_mandato_originale_csv']


# --- Autenticazione e Controllo Ruolo (Standard per Pagine Interne) ---
if not st.session_state.get('authentication_status', False):
    st.warning("Devi effettuare il login per accedere a questa pagina.")
    if st.button("🏠 Vai alla pagina di Login", key="ctrl_login_btn_redir"):
        st.switch_page("app.py") # Assumendo che app.py sia la pagina di login principale
    st.stop()

USER_ROLE_CTRL = st.session_state.get('user_role')
USERNAME_CTRL = st.session_state.get('username')
NAME_CTRL = st.session_state.get('name')
AUTHENTICATOR_CTRL = st.session_state.get('authenticator')

if not AUTHENTICATOR_CTRL: # Ulteriore controllo di sessione valida
    st.error("🚨 Errore di sessione (Authenticator non trovato). Riprova il login.")
    if st.button("🏠 Riprova Login", key="ctrl_login_btn_no_auth_obj"):
        st.switch_page("app.py")
    st.stop()

if USER_ROLE_CTRL not in ['controllore', 'admin']:
    st.error("🚫 Accesso negato. Questa pagina è riservata ai ruoli Controllore e Amministratore.")
    log_activity(USERNAME_CTRL, "PAGE_ACCESS_DENIED", f"Tentativo accesso a Gestione Dati Controllore da ruolo: {USER_ROLE_CTRL}")
    st.stop()

st.sidebar.title(f"👤 Utente: {NAME_CTRL}")
st.sidebar.write(f"🔖 Ruolo: {USER_ROLE_CTRL.capitalize()}")
AUTHENTICATOR_CTRL.logout('🚪 Logout', 'sidebar', key='ctrl_logout_sidebar')
# --- Fine Autenticazione ---

# --- Contenuto Pagina ---
st.title("⚙️ Caricamento, Validazione e Salvataggio Dati (Controllore)")
log_activity(USERNAME_CTRL, "PAGE_VIEW", "Controllore - Caricamento/Validazione Dati")

st.markdown("""
Questa sezione è dedicata ai **Controllori** e **Amministratori** per:
1.  Caricare un file CSV precedentemente verificato e scaricato dalla sezione "Richiedente" (o preparato esternamente secondo lo stesso formato).
2.  Verificare che non esista già una registrazione per lo stesso **Rif. PA** nel database.
3.  Eseguire controlli di validità sui dati (simili a quelli del Richiedente).
4.  Salvare i dati validati nel database centrale (azione irreversibile per la specifica trasmissione).
""")

uploaded_file_ctrl = st.file_uploader(
    "📤 Carica il file CSV delle spese (separatore ';', decimale ',', encoding UTF-8)", 
    type=['csv'],
    help="Il file CSV dovrebbe provenire dalla sezione Richiedente o seguire lo stesso formato. Il Rif. PA deve essere nel formato AAAA-NUMERO/RER.",
    key="ctrl_file_uploader_widget"
)

# Gestione Stato Sessione per il file e i dati processati (specifico per questa pagina)
if uploaded_file_ctrl is not None:
    if st.session_state.get('ctrl_last_uploaded_filename') != uploaded_file_ctrl.name:
        # Nuovo file caricato, resetta stati precedenti
        st.session_state.ctrl_df_loaded_validated = None # DataFrame dopo parsing e validazione iniziale
        st.session_state.ctrl_df_ready_for_db = None    # DataFrame pronto per il salvataggio
        st.session_state.ctrl_validation_results_df = None # Risultati della validazione
        st.session_state.ctrl_has_blocking_errors = True   # Default a True finché non validato
        st.session_state.ctrl_current_rif_pa_info = None  # Info sul Rif PA corrente
        st.session_state.ctrl_last_uploaded_filename = uploaded_file_ctrl.name
elif st.session_state.get('ctrl_last_uploaded_filename') is not None: # File rimosso
    st.session_state.ctrl_df_loaded_validated = None
    st.session_state.ctrl_df_ready_for_db = None
    st.session_state.ctrl_validation_results_df = None
    st.session_state.ctrl_has_blocking_errors = True
    st.session_state.ctrl_current_rif_pa_info = None
    st.session_state.ctrl_last_uploaded_filename = None

results_display_area = st.container() # Per mostrare risultati e pulsanti

if uploaded_file_ctrl is not None and st.session_state.get('ctrl_df_loaded_validated') is None:
    with results_display_area: # Processa e mostra risultati dentro quest'area
        with st.spinner("Elaborazione file CSV in corso..."):
            try:
                df_from_csv = pd.read_csv(uploaded_file_ctrl, sep=';', decimal=',', na_filter=False, dtype=str)
                log_activity(USERNAME_CTRL, "FILE_UPLOADED_CONTROLLER", f"File: {uploaded_file_ctrl.name}, Righe: {len(df_from_csv)}")

                if df_from_csv.empty:
                    st.error("🚨 Il file CSV caricato è vuoto.")
                    st.stop()

                # --- 1. Controllo e Validazione Rif. PA (dal CSV) ---
                if 'rif_pa' not in df_from_csv.columns:
                    st.error("🚨 Colonna 'rif_pa' mancante nel file CSV.")
                    st.stop()
                
                rif_pa_csv_value = df_from_csv['rif_pa'].iloc[0] if not df_from_csv.empty else None
                if not rif_pa_csv_value or pd.isna(rif_pa_csv_value):
                    st.error("🚨 Valore 'rif_pa' mancante o vuoto nella prima riga del CSV (e deve essere uguale per tutte le righe).")
                    st.stop()
                
                # Validazione formato Rif. PA
                is_valid_rif_format, rif_msg_format = validate_rif_pa_format(rif_pa_csv_value)
                if not is_valid_rif_format:
                    st.error(f"🚨 Formato Rif. PA non valido ('{rif_pa_csv_value}'): {rif_msg_format}")
                    st.stop()
                
                current_rif_pa = rif_pa_csv_value.strip()
                st.session_state.ctrl_current_rif_pa_info = {'rif_pa': current_rif_pa, 'message': rif_msg_format}
                st.subheader(f"📄 File Caricato: Dati per Rif. PA: `{current_rif_pa}`")
                st.success(rif_msg_format)

                # Controllo unicità Rif. PA nel DB (critico)
                if check_rif_pa_exists(current_rif_pa):
                    st.error(f"🚫 ATTENZIONE: Esiste già una registrazione nel database per il Rif. PA '{current_rif_pa}'. Impossibile procedere con questo caricamento.")
                    st.session_state.ctrl_has_blocking_errors = True # Blocca salvataggio
                    st.stop()
                else:
                    st.success(f"✅ OK: Nessuna registrazione esistente per Rif. PA '{current_rif_pa}'. Si può procedere.")

                df_check_ctrl = df_from_csv.copy()
                
                # --- 2. Pre-processing e Parsing Tipi dal CSV ---
                # CF pulito
                df_check_ctrl['cf_pulito'] = df_check_ctrl.get('codice_fiscale_bambino', pd.Series(dtype='str')).astype(str).str.upper().str.strip()
                
                # Date (conserva originale per messaggi)
                df_check_ctrl['data_mandato_originale_csv'] = df_check_ctrl.get('data_mandato', pd.Series(dtype='str'))
                df_check_ctrl['data_mandato'] = pd.to_datetime(df_check_ctrl['data_mandato_originale_csv'], errors='coerce', dayfirst=True).dt.date

                # Valute (il CSV dovrebbe averle già come numeri, ma parsare per sicurezza se sono stringhe)
                currency_cols_ctrl = ['importo_mandato','valore_contributo_fse','altri_contributi','quota_retta_destinatario','totale_retta', 'controlli_formali'] # 'controlli_formali' è quella dal CSV del richiedente
                for col in currency_cols_ctrl:
                    if col in df_check_ctrl.columns:
                        df_check_ctrl[col] = df_check_ctrl[col].apply(lambda x: parse_excel_currency(str(x))) # Forzo a stringa per parse_excel_currency
                    else:
                        st.warning(f"⚠️ Colonna valuta attesa '{col}' non trovata nel CSV. Sarà trattata come 0.0 se richiesta.")
                        df_check_ctrl[col] = 0.0 # Default se mancante

                # Settimane
                df_check_ctrl['numero_settimane_frequenza'] = df_check_ctrl.get('numero_settimane_frequenza', pd.Series(dtype='str')).apply(
                    lambda x: int(float(str(x).replace(',','.'))) if pd.notna(x) and str(x).strip().replace('.','',1).replace(',','.',1).isdigit() else 0
                )
                st.session_state.ctrl_df_loaded_validated = df_check_ctrl # Salva df dopo parsing
                
                # --- 3. Esegui Validazioni Dettagliate ---
                # 'controlli_formali' nel CSV è il "dichiarato" per il controllore
                df_val_res, has_err = run_detailed_validations(
                    df_to_validate=df_check_ctrl,
                    cf_col_clean='cf_pulito',
                    original_date_col='data_mandato_originale_csv',
                    parsed_date_col='data_mandato',
                    declared_formal_controls_col='controlli_formali', # Usa colonna 'controlli_formali' dal CSV
                    row_offset_for_messages=2 # Per Controllore, riga CSV è index + intestazione + 1
                )
                st.session_state.ctrl_validation_results_df = df_val_res
                st.session_state.ctrl_has_blocking_errors = has_err
                
            except pd.errors.EmptyDataError:
                st.error("Il file CSV è vuoto o non contiene dati leggibili.")
                st.session_state.ctrl_has_blocking_errors = True
            except pd.errors.ParserError as pe:
                st.error(f"Errore di parsing del CSV: {pe}. Verificare separatore (deve essere ';'), decimali (','), e encoding (UTF-8).")
                log_activity(USERNAME_CTRL, "CSV_PARSE_ERROR_CONTROLLER", str(pe))
                st.session_state.ctrl_has_blocking_errors = True
            except ValueError as ve: # Errori di conversione non gestiti
                st.error(f"Errore nella conversione dei dati CSV: {ve}. Controlla formati numerici e date.")
                log_activity(USERNAME_CTRL, "DATA_CONVERSION_ERROR_CONTROLLER", str(ve))
                st.session_state.ctrl_has_blocking_errors = True
            except Exception as e_proc:
                st.error(f"Errore imprevisto durante l'elaborazione del file: {e_proc}")
                log_activity(USERNAME_CTRL, "FILE_PROCESSING_ERROR_CONTROLLER", str(e_proc))
                st.exception(e_proc)
                st.session_state.ctrl_has_blocking_errors = True
            
            # Ricarica la sezione per mostrare i risultati o il form di salvataggio
            st.rerun() 

# --- Visualizzazione Risultati Validazione e Preparazione per Salvataggio ---
if st.session_state.get('ctrl_validation_results_df') is not None:
    with results_display_area:
        df_val_res_show = st.session_state.ctrl_validation_results_df
        current_rif_pa_info_show = st.session_state.get('ctrl_current_rif_pa_info', {})
        
        if 'rif_pa' in current_rif_pa_info_show: # Mostra di nuovo il Rif PA se disponibile
             st.subheader(f"📄 Risultati Verifica per Rif. PA: `{current_rif_pa_info_show['rif_pa']}`")
        else: # Se il file non è stato processato o rif_pa non estratto
             st.subheader("🔍 Risultati Verifica Dati Caricati")

        cols_disp_val = ['Riga','Bambino','Esito CF','Esito Data Mandato','Esito D=A+B+C','Esito Regole Contr.FSE','Esito Contr.Formali 5%', "Verifica Max 300€ FSE per Bambino (batch)", 'Errori Rilevati']
        actual_cols_val_disp = [col for col in cols_disp_val if col in df_val_res_show.columns]
        st.dataframe(df_val_res_show[actual_cols_val_disp], use_container_width=True, hide_index=True)

        has_errors_display = st.session_state.get('ctrl_has_blocking_errors', True)
        df_loaded_for_save = st.session_state.get('ctrl_df_loaded_validated')

        if not has_errors_display and df_loaded_for_save is not None:
            st.success("✅ Verifiche preliminari OK. Pronto per il salvataggio nel database.")
            
            # --- Preparazione DataFrame Finale per il DB ---
            df_to_save_db = df_loaded_for_save.copy()
            
            # Aggiungi ID Trasmissione (univoco per questo batch di caricamento)
            df_to_save_db['id_trasmissione'] = str(uuid.uuid4())
            
            # Ricalcola 'controlli_formali' come 5% FSE (verità ultima per DB)
            # Questo sovrascrive la colonna 'controlli_formali' che era nel CSV del richiedente.
            df_to_save_db['controlli_formali'] = round(df_to_save_db['valore_contributo_fse'] * 0.05, 2)
            
            # Rinomina colonna CF pulita e rimuovi quella originale (se diversa)
            if 'codice_fiscale_bambino' in df_to_save_db.columns and 'cf_pulito' in df_to_save_db.columns:
                 df_to_save_db.drop(columns=['codice_fiscale_bambino'], inplace=True, errors='ignore')
            if 'cf_pulito' in df_to_save_db.columns:
                df_to_save_db.rename(columns={'cf_pulito':'codice_fiscale_bambino'}, inplace=True)
            
            # Assicura che tutte le colonne DB_COLS_ATTESE esistano, impostando None o default se necessario
            # (anche se il CSV del richiedente dovrebbe averle tutte)
            for col_db in DB_COLS_ATTESE:
                if col_db not in df_to_save_db.columns:
                    # Determina un default sensato in base al tipo atteso o None
                    default_val_db = 0.0 if col_db in ['importo_mandato','valore_contributo_fse','altri_contributi','quota_retta_destinatario','totale_retta', 'controlli_formali'] else \
                                   0 if col_db == 'numero_settimane_frequenza' else \
                                   None # Per stringhe o date (anche se data dovrebbe esserci)
                    st.warning(f"⚠️ Colonna DB '{col_db}' mancante nel CSV processato, sarà impostata a '{default_val_db}'.")
                    df_to_save_db[col_db] = default_val_db
            
            # Rimuovi colonne temporanee/ausiliarie non necessarie per il DB
            df_to_save_db = df_to_save_db.drop(columns=COLS_DA_RIMUOVERE_PER_DB, errors='ignore')
            
            # Seleziona solo le colonne attese dal DB nell'ordine corretto (se importante per DB, anche se ORM non lo richiede)
            final_cols_for_db = [c for c in DB_COLS_ATTESE if c in df_to_save_db.columns]
            df_final_for_db = df_to_save_db[final_cols_for_db]
            
            st.session_state.ctrl_df_ready_for_db = df_final_for_db # Salva in session_state

            with st.expander("🔍 Anteprima Dati da Salvare nel Database", expanded=False):
                df_preview_db = df_final_for_db.copy()
                if 'data_mandato' in df_preview_db.columns: # Formatta data per anteprima
                     df_preview_db['data_mandato'] = df_preview_db['data_mandato'].apply(
                         lambda x: x.strftime('%d/%m/%Y') if pd.notna(x) and hasattr(x,'strftime') else ''
                     )
                st.dataframe(df_preview_db, use_container_width=True, hide_index=True)
        
        elif has_errors_display:
            st.error("🚫 Sono stati rilevati errori bloccanti (❌). Correggere il file CSV e ricaricarlo.")
            st.session_state.ctrl_df_ready_for_db = None # Nessun df pronto per il salvataggio

# --- Bottone di Salvataggio (mostrato solo se i dati sono pronti e validi) ---
if st.session_state.get('ctrl_df_ready_for_db') is not None and not st.session_state.get('ctrl_has_blocking_errors', True):
    if st.button("💾 Salva Dati Verificati nel Database Centrale", key="save_controller_data_final_btn", type="primary"):
        with results_display_area: # Mostra output del salvataggio nella stessa area
            with st.spinner("Salvataggio nel database in corso..."):
                df_to_persist = st.session_state.ctrl_df_ready_for_db
                rif_pa_to_persist = df_to_persist['rif_pa'].iloc[0] if not df_to_persist.empty else "N/A_RIFPA_PERSIST"
                
                # Doppio controllo (finale) esistenza Rif PA prima di scrivere (paranoia check)
                if check_rif_pa_exists(rif_pa_to_persist):
                     st.error(f"🚨 ERRORE CRITICO: Il Rif. PA '{rif_pa_to_persist}' risulta già presente nel DB (controllo finale). Salvataggio annullato. Questo non dovrebbe succedere se i controlli precedenti hanno funzionato.")
                     log_activity(USERNAME_CTRL, "SAVE_BLOCKED_DUPLICATE_RIFPA_FINAL", f"Rif. PA: {rif_pa_to_persist}")
                else:
                    success_db, msg_db = add_multiple_spese(df_to_persist, USERNAME_CTRL)
                    if success_db:
                        st.success(f"✅ {msg_db}")
                        log_activity(USERNAME_CTRL, "DATA_SAVED_BY_CONTROLLER", f"Rif.PA: {rif_pa_to_persist}, Righe: {len(df_to_persist)}")
                        # Resetta stato per permettere nuovo caricamento
                        st.session_state.ctrl_df_loaded_validated = None
                        st.session_state.ctrl_df_ready_for_db = None
                        st.session_state.ctrl_validation_results_df = None
                        st.session_state.ctrl_has_blocking_errors = True
                        st.session_state.ctrl_current_rif_pa_info = None
                        st.session_state.ctrl_last_uploaded_filename = None 
                        st.rerun() 
                    else:
                        st.error(f"⚠️ Errore durante il salvataggio nel database: {msg_db}")
                        log_activity(USERNAME_CTRL, "DATA_SAVE_FAILED_CONTROLLER", f"Rif.PA: {rif_pa_to_persist}, Dettaglio: {msg_db}")

elif uploaded_file_ctrl is None and not results_display_area.empty(): # Se il file è stato rimosso e c'erano messaggi
    results_display_area.empty() # Pulisce l'area se non c'è più un file
#cartella/pages/01_Gestione_Dati_Controllore.py