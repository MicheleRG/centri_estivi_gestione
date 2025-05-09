#/pages/01_Gestione_Dati_Controllore.py
import streamlit as st
import pandas as pd
from utils.db import add_multiple_spese, log_activity, check_rif_pa_exists
from utils.common_utils import (
    parse_excel_currency, validate_rif_pa_format,
    run_detailed_validations # Importa la funzione con i nuovi nomi dei parametri
)
import uuid

st.set_page_config(page_title="Gestione Dati Controllore", layout="wide")

# --- Costanti Specifiche Pagina ---
DB_COLS_ATTESE = [
    'id_trasmissione', 'rif_pa', 'cup', 'distretto', 'comune_capofila', 
    'numero_mandato', 'data_mandato', 'comune_titolare_mandato', 'importo_mandato',
    'comune_centro_estivo', 'centro_estivo', 'genitore_cognome_nome', 
    'bambino_cognome_nome', 'codice_fiscale_bambino', 'valore_contributo_fse', 
    'altri_contributi', 'quota_retta_destinatario', 'totale_retta', 
    'numero_settimane_frequenza', 'controlli_formali'
]
COLS_DA_RIMUOVERE_PER_DB = ['cf_pulito', 'data_mandato_originale_csv']

# --- Autenticazione e Controllo Ruolo ---
if not st.session_state.get('authentication_status', False):
    st.warning("Devi effettuare il login per accedere a questa pagina.")
    if st.button("🏠 Vai al Login", key="ctrl_login_btn_redir"): st.switch_page("app.py")
    st.stop()

USER_ROLE_CTRL = st.session_state.get('user_role')
USERNAME_CTRL = st.session_state.get('username')
NAME_CTRL = st.session_state.get('name')
AUTHENTICATOR_CTRL = st.session_state.get('authenticator')

if not AUTHENTICATOR_CTRL:
    st.error("🚨 Errore sessione. Riprova il login.")
    if st.button("🏠 Riprova Login", key="ctrl_login_btn_no_auth_obj"): st.switch_page("app.py")
    st.stop()

if USER_ROLE_CTRL not in ['controllore', 'admin']:
    st.error("🚫 Accesso negato. Pagina riservata a Controllori e Amministratori.")
    log_activity(USERNAME_CTRL, "PAGE_ACCESS_DENIED", f"Accesso negato a Gestione Dati Controllore da: {USER_ROLE_CTRL}")
    st.stop()

st.sidebar.title(f"👤 Utente: {NAME_CTRL}")
st.sidebar.write(f"🔖 Ruolo: {USER_ROLE_CTRL.capitalize()}")
AUTHENTICATOR_CTRL.logout('🚪 Logout', 'sidebar', key='ctrl_logout_sidebar')
# --- Fine Autenticazione ---

st.title("⚙️ Caricamento, Validazione e Salvataggio Dati (Controllore)")
log_activity(USERNAME_CTRL, "PAGE_VIEW", "Controllore - Caricamento/Validazione")

st.markdown("Carica CSV, verifica unicità Rif. PA, valida dati e salva nel DB.")

uploaded_file_ctrl = st.file_uploader(
    "📤 Carica CSV (separatore ';', decimale ',', encoding UTF-8)", 
    type=['csv'], help="Il file CSV dovrebbe seguire il formato del Richiedente.",
    key="ctrl_file_uploader_widget"
)

# Gestione Stato Sessione per il file
if uploaded_file_ctrl is not None:
    if st.session_state.get('ctrl_last_uploaded_filename') != uploaded_file_ctrl.name:
        st.session_state.ctrl_df_loaded_validated = None
        st.session_state.ctrl_df_ready_for_db = None
        st.session_state.ctrl_validation_results_df = None
        st.session_state.ctrl_has_blocking_errors = True
        st.session_state.ctrl_current_rif_pa_info = None
        st.session_state.ctrl_last_uploaded_filename = uploaded_file_ctrl.name
elif st.session_state.get('ctrl_last_uploaded_filename') is not None:
    st.session_state.ctrl_df_loaded_validated = None
    st.session_state.ctrl_df_ready_for_db = None
    st.session_state.ctrl_validation_results_df = None
    st.session_state.ctrl_has_blocking_errors = True
    st.session_state.ctrl_current_rif_pa_info = None
    st.session_state.ctrl_last_uploaded_filename = None

results_display_area = st.container()

if uploaded_file_ctrl is not None and st.session_state.get('ctrl_df_loaded_validated') is None:
    with results_display_area, st.spinner("Elaborazione file CSV..."):
        try:
            df_from_csv = pd.read_csv(uploaded_file_ctrl, sep=';', decimal=',', na_filter=False, dtype=str)
            log_activity(USERNAME_CTRL, "FILE_UPLOADED_CONTROLLER", f"File: {uploaded_file_ctrl.name}, Righe: {len(df_from_csv)}")

            if df_from_csv.empty: st.error("🚨 Il file CSV è vuoto."); st.stop()
            if 'rif_pa' not in df_from_csv.columns: st.error("🚨 Colonna 'rif_pa' mancante."); st.stop()
            
            rif_pa_csv = df_from_csv['rif_pa'].iloc[0]
            if not rif_pa_csv or pd.isna(rif_pa_csv): st.error("🚨 Valore 'rif_pa' mancante nel CSV."); st.stop()
            
            is_valid_rif, rif_msg = validate_rif_pa_format(rif_pa_csv)
            if not is_valid_rif: st.error(f"🚨 Formato Rif. PA non valido ('{rif_pa_csv}'): {rif_msg}"); st.stop()
            
            current_rif_pa = rif_pa_csv.strip()
            st.session_state.ctrl_current_rif_pa_info = {'rif_pa': current_rif_pa, 'message': rif_msg}
            st.subheader(f"📄 File Caricato: Dati per Rif. PA: `{current_rif_pa}`")
            st.success(rif_msg)

            if check_rif_pa_exists(current_rif_pa):
                st.error(f"🚫 ATTENZIONE: Registrazione per Rif. PA '{current_rif_pa}' già presente. Impossibile procedere.")
                st.session_state.ctrl_has_blocking_errors = True; st.stop()
            else:
                st.success(f"✅ OK: Nessuna registrazione per Rif. PA '{current_rif_pa}'.")

            df_check_ctrl = df_from_csv.copy()
            df_check_ctrl['cf_pulito'] = df_check_ctrl.get('codice_fiscale_bambino', pd.Series(dtype='str')).astype(str).str.upper().str.strip()
            df_check_ctrl['data_mandato_originale_csv'] = df_check_ctrl.get('data_mandato', pd.Series(dtype='str'))
            df_check_ctrl['data_mandato'] = pd.to_datetime(df_check_ctrl['data_mandato_originale_csv'], errors='coerce', dayfirst=True).dt.date

            currency_cols_ctrl = ['importo_mandato','valore_contributo_fse','altri_contributi','quota_retta_destinatario','totale_retta', 'controlli_formali']
            for col in currency_cols_ctrl:
                if col in df_check_ctrl.columns:
                    df_check_ctrl[col] = df_check_ctrl[col].apply(lambda x: parse_excel_currency(str(x)))
                else:
                    st.warning(f"⚠️ Colonna valuta '{col}' non trovata. Sarà 0.0.")
                    df_check_ctrl[col] = 0.0
            
            df_check_ctrl['numero_settimane_frequenza'] = df_check_ctrl.get('numero_settimane_frequenza', pd.Series(dtype='str')).apply(
                lambda x: int(float(str(x).replace(',','.'))) if pd.notna(x) and str(x).strip().replace('.','',1).replace(',','.',1).isdigit() else 0
            )
            st.session_state.ctrl_df_loaded_validated = df_check_ctrl
            
            # Nomi dei parametri aggiornati per la chiamata a run_detailed_validations
            df_val_res, has_err = run_detailed_validations(
                df_input=df_check_ctrl,                             # AGGIORNATO
                cf_col_clean_name='cf_pulito',                      # AGGIORNATO
                original_date_col_name='data_mandato_originale_csv',# AGGIORNATO
                parsed_date_col_name='data_mandato',                # AGGIORNATO
                declared_formal_controls_col_name='controlli_formali', # AGGIORNATO
                row_offset_val=2                                    # AGGIORNATO
            )
            st.session_state.ctrl_validation_results_df = df_val_res
            st.session_state.ctrl_has_blocking_errors = has_err
                
        except pd.errors.EmptyDataError: st.error("Il CSV è vuoto."); st.session_state.ctrl_has_blocking_errors = True
        except pd.errors.ParserError as pe: st.error(f"Errore parsing CSV: {pe}."); log_activity(USERNAME_CTRL, "CSV_PARSE_ERROR_CONTROLLER", str(pe)); st.session_state.ctrl_has_blocking_errors = True
        except ValueError as ve: st.error(f"Errore conversione dati CSV: {ve}."); log_activity(USERNAME_CTRL, "DATA_CONVERSION_ERROR_CONTROLLER", str(ve)); st.session_state.ctrl_has_blocking_errors = True
        except Exception as e_proc: st.error(f"Errore imprevisto: {e_proc}"); log_activity(USERNAME_CTRL, "FILE_PROCESSING_ERROR_CONTROLLER", str(e_proc)); st.exception(e_proc); st.session_state.ctrl_has_blocking_errors = True
        st.rerun() 

if st.session_state.get('ctrl_validation_results_df') is not None:
    with results_display_area:
        df_val_res_show = st.session_state.ctrl_validation_results_df
        current_rif_pa_info = st.session_state.get('ctrl_current_rif_pa_info', {})
        
        if 'rif_pa' in current_rif_pa_info: st.subheader(f"📄 Risultati Verifica per Rif. PA: `{current_rif_pa_info['rif_pa']}`")
        else: st.subheader("🔍 Risultati Verifica Dati Caricati")

        cols_disp_val = ['Riga','Bambino','Esito CF','Esito Data Mandato','Esito D=A+B+C','Esito Regole Contr.FSE','Esito Contr.Formali 5%', "Verifica Max 300€ FSE per Bambino (batch)", 'Errori Bloccanti'] # 'Errori Bloccanti' nome colonna aggiornato
        actual_cols_val_disp = [col for col in cols_disp_val if col in df_val_res_show.columns]
        st.dataframe(df_val_res_show[actual_cols_val_disp], use_container_width=True, hide_index=True)

        has_errors_display = st.session_state.get('ctrl_has_blocking_errors', True)
        df_loaded_for_save = st.session_state.get('ctrl_df_loaded_validated')

        if not has_errors_display and df_loaded_for_save is not None:
            st.success("✅ Verifiche OK. Pronto per salvataggio nel DB.")
            df_to_save_db = df_loaded_for_save.copy()
            df_to_save_db['id_trasmissione'] = str(uuid.uuid4())
            df_to_save_db['controlli_formali'] = round(df_to_save_db['valore_contributo_fse'] * 0.05, 2)
            
            if 'codice_fiscale_bambino' in df_to_save_db.columns and 'cf_pulito' in df_to_save_db.columns:
                 df_to_save_db.drop(columns=['codice_fiscale_bambino'], inplace=True, errors='ignore')
            if 'cf_pulito' in df_to_save_db.columns:
                df_to_save_db.rename(columns={'cf_pulito':'codice_fiscale_bambino'}, inplace=True)
            
            for col_db in DB_COLS_ATTESE:
                if col_db not in df_to_save_db.columns:
                    default_val = 0.0 if col_db in ['importo_mandato','valore_contributo_fse'] else 0 if col_db == 'numero_settimane_frequenza' else None
                    st.warning(f"⚠️ Colonna DB '{col_db}' mancante, impostata a '{default_val}'.")
                    df_to_save_db[col_db] = default_val
            
            df_to_save_db = df_to_save_db.drop(columns=COLS_DA_RIMUOVERE_PER_DB, errors='ignore')
            final_cols_for_db = [c for c in DB_COLS_ATTESE if c in df_to_save_db.columns]
            df_final_for_db = df_to_save_db[final_cols_for_db]
            st.session_state.ctrl_df_ready_for_db = df_final_for_db

            with st.expander("🔍 Anteprima Dati da Salvare", expanded=False):
                df_preview = df_final_for_db.copy()
                if 'data_mandato' in df_preview.columns:
                     df_preview['data_mandato'] = df_preview['data_mandato'].apply(lambda x: x.strftime('%d/%m/%Y') if pd.notna(x) and hasattr(x,'strftime') else '')
                st.dataframe(df_preview, use_container_width=True, hide_index=True)
        
        elif has_errors_display:
            st.error("🚫 Rilevati errori bloccanti (❌). Correggere CSV e ricaricare.")
            st.session_state.ctrl_df_ready_for_db = None

if st.session_state.get('ctrl_df_ready_for_db') is not None and not st.session_state.get('ctrl_has_blocking_errors', True):
    if st.button("💾 Salva Dati Verificati nel DB", key="save_ctrl_data_btn", type="primary"):
        with results_display_area, st.spinner("Salvataggio nel DB..."):
            df_to_persist = st.session_state.ctrl_df_ready_for_db
            rif_pa_persist = df_to_persist['rif_pa'].iloc[0] if not df_to_persist.empty else "N/A_RIFPA"
            
            if check_rif_pa_exists(rif_pa_persist): # Doppio controllo
                 st.error(f"🚨 ERRORE CRITICO: Rif. PA '{rif_pa_persist}' già presente (controllo finale). Salvataggio annullato.")
                 log_activity(USERNAME_CTRL, "SAVE_BLOCKED_DUPLICATE_RIFPA_FINAL", f"Rif. PA: {rif_pa_persist}")
            else:
                success_db, msg_db = add_multiple_spese(df_to_persist, USERNAME_CTRL) # Non passa existing_conn, add_multiple_spese gestisce la sua
                if success_db:
                    st.success(f"✅ {msg_db}")
                    log_activity(USERNAME_CTRL, "DATA_SAVED_BY_CONTROLLER", f"Rif.PA: {rif_pa_persist}, Righe: {len(df_to_persist)}")
                    # Reset stato per nuovo caricamento
                    st.session_state.ctrl_df_loaded_validated = None
                    st.session_state.ctrl_df_ready_for_db = None
                    st.session_state.ctrl_validation_results_df = None
                    st.session_state.ctrl_has_blocking_errors = True
                    st.session_state.ctrl_current_rif_pa_info = None
                    st.session_state.ctrl_last_uploaded_filename = None 
                    st.rerun() 
                else:
                    st.error(f"⚠️ Errore salvataggio DB: {msg_db}")
                    log_activity(USERNAME_CTRL, "DATA_SAVE_FAILED_CONTROLLER", f"Rif.PA: {rif_pa_persist}, Dettaglio: {msg_db}")

elif uploaded_file_ctrl is None and not results_display_area.empty():
    results_display_area.empty()
#/pages/01_Gestione_Dati_Controllore.py