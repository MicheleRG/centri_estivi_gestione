#/pages/01_Gestione_Dati_Controllore.py
import streamlit as st
import pandas as pd
from utils.db import add_multiple_spese, log_activity, check_rif_pa_exists
from utils.common_utils import (
    parse_excel_currency, 
    validate_rif_pa_format,
    run_detailed_validations
)
import uuid
from io import StringIO
import re 
from typing import Tuple, Union # Aggiunto Union

st.set_page_config(page_title="Gestione Dati Controllore", layout="wide")

# --- Costanti Specifiche Pagina ---
COLONNE_SIFER_INPUT = [ 
    'Rif. PA', 'Numero progetto', 'ID documento', 'Codice organismo',
    'Voce imputazione', 'Importo imputazione', 'Note imputazione',
    'Data pagamento', 'Tipo pagamento', 'Nr. documento', 'Data documento',
    'Importo documento', 'Fornitore/oggetto documento', 'C.F./P.I documento',
    'Descrizione documento', 'Tipo documento'
]

DB_COLS_ATTESE = [ 
    'id_trasmissione', 'rif_pa', 'cup', 'distretto', 'comune_capofila', 
    'numero_mandato', 'data_mandato', 'comune_titolare_mandato', 'importo_mandato',
    'comune_centro_estivo', 'centro_estivo', 'genitore_cognome_nome', 
    'bambino_cognome_nome', 'codice_fiscale_bambino', 'valore_contributo_fse', 
    'altri_contributi', 'quota_retta_destinatario', 'totale_retta', 
    'numero_settimane_frequenza', 'controlli_formali'
]

# --- Funzioni di Parsing Specifiche per il Controllore ---
def parse_note_imputazione_sifer(note_str: str) -> Tuple[float, float, float]:
    val_B, val_C, val_D = 0.0, 0.0, 0.0
    if pd.isna(note_str) or not isinstance(note_str, str):
        return val_B, val_C, val_D

    match_b = re.search(r"B altri contr:\s*([\d\.,]+)", note_str)
    match_c = re.search(r"C retta:\s*([\d\.,]+)", note_str)
    match_d = re.search(r"D Tot retta:\s*([\d\.,]+)", note_str)

    if match_b:
        val_B = parse_excel_currency(match_b.group(1))
    if match_c:
        val_C = parse_excel_currency(match_c.group(1))
    if match_d:
        val_D = parse_excel_currency(match_d.group(1))
        
    return val_B, val_C, val_D

def parse_id_documento_sifer(id_doc_str: str) -> Tuple[Union[str, None], Union[str, None], Union[str, None], str]:
    cup, distretto, capofila, progressivo = None, None, None, ""
    if pd.isna(id_doc_str) or not isinstance(id_doc_str, str):
        return cup, distretto, capofila, progressivo

    match = re.search(
        r"cup:\s*(?P<cup>.*?)\s*\|\s*distretto:\s*(?P<distretto>.*?)\s*\|\s*capofila:\s*(?P<capofila>.*?)\s*\|\s*prog:\s*(?P<prog>\d+)",
        id_doc_str
    )

    if match:
        cup_match = match.group("cup").strip()
        distretto_match = match.group("distretto").strip()
        capofila_match = match.group("capofila").strip()
        
        cup = None if cup_match == "--" else cup_match
        distretto = None if distretto_match == "--" else distretto_match
        capofila = None if capofila_match == "--" else capofila_match
        progressivo = match.group("prog").strip()
        
    return cup, distretto, capofila, progressivo

def parse_voce_imputazione_sifer(voce_str: str) -> Tuple[Union[str, None], Union[str, None]]:
    """
    Estrae Comune Centro Estivo e Centro Estivo dalla stringa Voce Imputazione.
    Formato atteso: "com centro est: <val_com_ce> | centro est: <val_ce>"
    Restituisce (comune_ce, centro_estivo) come stringhe.
    Placeholder "ComuneCE ND" o "CentroEstivo ND" vengono restituiti come None.
    """
    comune_ce, centro_estivo = None, None
    if pd.isna(voce_str) or not isinstance(voce_str, str):
        return comune_ce, centro_estivo

    match = re.search(
        r"com centro est:\s*(?P<com_ce>.*?)\s*\|\s*centro est:\s*(?P<ce>.*)",
        voce_str
    )

    if match:
        com_ce_match = match.group("com_ce").strip()
        ce_match = match.group("ce").strip() # Non c'è un separatore | dopo, quindi prendi tutto il resto

        comune_ce = None if com_ce_match == "ComuneCE ND" else com_ce_match
        centro_estivo = None if ce_match == "CentroEstivo ND" else ce_match
        
    return comune_ce, centro_estivo

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

# --- Logica Pagina ---
st.title("⚙️ Caricamento, Validazione e Salvataggio Dati SIFER (Controllore)")
log_activity(USERNAME_CTRL, "PAGE_VIEW", "Controllore - Caricamento/Validazione SIFER")

st.markdown("Carica il file CSV formattato SIFER, verifica unicità Rif. PA, valida dati e salva nel DB.")

uploaded_file_ctrl = st.file_uploader(
    "📤 Carica CSV SIFER (formato SIFER_costi_reali_1420_v1.0)", 
    type=['csv'], 
    help="Il file CSV deve seguire il formato SIFER: prima riga versione, poi dati senza header.",
    key="ctrl_file_uploader_widget"
)

if uploaded_file_ctrl is not None:
    if st.session_state.get('ctrl_last_uploaded_filename') != uploaded_file_ctrl.name:
        st.session_state.ctrl_df_sifer_loaded = None
        st.session_state.ctrl_df_internal_for_validation = None
        st.session_state.ctrl_df_ready_for_db = None
        st.session_state.ctrl_validation_results_df = None
        st.session_state.ctrl_has_blocking_errors = True
        st.session_state.ctrl_current_rif_pa_info = None
        st.session_state.ctrl_last_uploaded_filename = uploaded_file_ctrl.name
elif st.session_state.get('ctrl_last_uploaded_filename') is not None:
    st.session_state.ctrl_df_sifer_loaded = None
    st.session_state.ctrl_df_internal_for_validation = None
    st.session_state.ctrl_df_ready_for_db = None
    st.session_state.ctrl_validation_results_df = None
    st.session_state.ctrl_has_blocking_errors = True
    st.session_state.ctrl_current_rif_pa_info = None
    st.session_state.ctrl_last_uploaded_filename = None

results_display_area = st.container()

if uploaded_file_ctrl is not None and st.session_state.get('ctrl_df_sifer_loaded') is None:
    with results_display_area, st.spinner("Elaborazione file CSV SIFER..."):
        try:
            stringio = StringIO(uploaded_file_ctrl.getvalue().decode('utf-8-sig'))
            sifer_version_row = stringio.readline().strip()
            log_activity(USERNAME_CTRL, "SIFER_FILE_VERSION_CONTROLLER", f"File: {uploaded_file_ctrl.name}, Versione: {sifer_version_row}")

            df_sifer_raw = pd.read_csv(stringio, sep=',', header=None, names=COLONNE_SIFER_INPUT, dtype=str, na_filter=False, quotechar='"', doublequote=True, skipinitialspace=True)
            log_activity(USERNAME_CTRL, "FILE_UPLOADED_CONTROLLER", f"File: {uploaded_file_ctrl.name}, Righe Dati: {len(df_sifer_raw)}")

            if df_sifer_raw.empty: st.error("🚨 CSV SIFER non contiene dati."); st.stop()
            
            df_internal = pd.DataFrame()

            rif_pa_csv = df_sifer_raw['Rif. PA'].iloc[0]
            if not rif_pa_csv or pd.isna(rif_pa_csv): st.error("🚨 'Rif. PA' mancante nel CSV SIFER."); st.stop()
            is_valid_rif, rif_msg = validate_rif_pa_format(rif_pa_csv)
            if not is_valid_rif: st.error(f"🚨 Formato Rif. PA non valido ('{rif_pa_csv}'): {rif_msg}"); st.stop()
            
            current_rif_pa = rif_pa_csv.strip()
            st.session_state.ctrl_current_rif_pa_info = {'rif_pa': current_rif_pa, 'message': rif_msg}
            st.subheader(f"📄 File Caricato: Dati SIFER per Rif. PA: `{current_rif_pa}`")
            st.success(rif_msg)

            if check_rif_pa_exists(current_rif_pa):
                st.error(f"🚫 ATTENZIONE: Registrazione per Rif. PA '{current_rif_pa}' già presente."); st.session_state.ctrl_has_blocking_errors = True; st.stop()
            else:
                st.success(f"✅ OK: Nessuna registrazione per Rif. PA '{current_rif_pa}'.")

            df_internal['rif_pa'] = df_sifer_raw['Rif. PA']
            
            parsed_id_docs = df_sifer_raw['ID documento'].apply(parse_id_documento_sifer)
            df_internal['cup'] = parsed_id_docs.apply(lambda x: x[0])
            df_internal['distretto'] = parsed_id_docs.apply(lambda x: x[1])
            df_internal['comune_capofila'] = parsed_id_docs.apply(lambda x: x[2])
            
            df_internal['numero_mandato'] = df_sifer_raw['Nr. documento']
            df_internal['data_mandato_originale'] = df_sifer_raw['Data pagamento']
            df_internal['data_mandato'] = pd.to_datetime(df_internal['data_mandato_originale'], format='%d/%m/%Y', errors='coerce').dt.date
            
            df_internal['comune_titolare_mandato'] = df_sifer_raw['Fornitore/oggetto documento']
            df_internal['importo_mandato'] = df_sifer_raw['Importo documento'].apply(parse_excel_currency)
            
            # --- NUOVO PARSING PER VOCE IMPUTAZIONE ---
            parsed_voce_imputazione = df_sifer_raw['Voce imputazione'].apply(parse_voce_imputazione_sifer)
            df_internal['comune_centro_estivo'] = parsed_voce_imputazione.apply(lambda x: x[0])
            df_internal['centro_estivo'] = parsed_voce_imputazione.apply(lambda x: x[1])
            # --- FINE NUOVO PARSING ---
            
            df_internal['genitore_cognome_nome'] = df_sifer_raw['Tipo documento'] 
            df_internal['bambino_cognome_nome'] = df_sifer_raw['Descrizione documento']
            
            df_internal['codice_fiscale_bambino'] = df_sifer_raw['C.F./P.I documento']
            df_internal['codice_fiscale_bambino_pulito'] = df_internal['codice_fiscale_bambino'].astype(str).str.upper().str.strip()

            df_internal['valore_contributo_fse'] = df_sifer_raw['Importo imputazione'].apply(parse_excel_currency)
            
            parsed_notes = df_sifer_raw['Note imputazione'].apply(parse_note_imputazione_sifer)
            df_internal['altri_contributi'] = parsed_notes.apply(lambda x: x[0])
            df_internal['quota_retta_destinatario'] = parsed_notes.apply(lambda x: x[1])
            df_internal['totale_retta'] = parsed_notes.apply(lambda x: x[2])
            
            df_internal['numero_settimane_frequenza'] = pd.to_numeric(df_sifer_raw['Numero progetto'], errors='coerce').fillna(0).astype(int)
            df_internal['controlli_formali_dichiarati'] = df_sifer_raw['Tipo pagamento'].apply(parse_excel_currency)
            
            st.session_state.ctrl_df_sifer_loaded = df_sifer_raw
            st.session_state.ctrl_df_internal_for_validation = df_internal.copy()

            df_val_res, has_err = run_detailed_validations(
                df_input=df_internal,
                cf_col_clean_name='codice_fiscale_bambino_pulito',
                original_date_col_name='data_mandato_originale',
                parsed_date_col_name='data_mandato',
                declared_formal_controls_col_name='controlli_formali_dichiarati',
                row_offset_val=2 
            )
            st.session_state.ctrl_validation_results_df = df_val_res
            st.session_state.ctrl_has_blocking_errors = has_err
                
        except pd.errors.EmptyDataError: st.error("Il CSV SIFER è vuoto o malformato."); st.session_state.ctrl_has_blocking_errors = True
        except pd.errors.ParserError as pe: st.error(f"Errore parsing CSV SIFER: {pe}."); log_activity(USERNAME_CTRL, "CSV_PARSE_ERROR_CONTROLLER", str(pe)); st.session_state.ctrl_has_blocking_errors = True
        except ValueError as ve: st.error(f"Errore conversione dati da CSV SIFER: {ve}."); log_activity(USERNAME_CTRL, "DATA_CONVERSION_ERROR_CONTROLLER", str(ve)); st.session_state.ctrl_has_blocking_errors = True
        except Exception as e_proc: st.error(f"Errore imprevisto: {e_proc}"); log_activity(USERNAME_CTRL, "FILE_PROCESSING_ERROR_CONTROLLER", str(e_proc)); st.exception(e_proc); st.session_state.ctrl_has_blocking_errors = True
        st.rerun() 

if st.session_state.get('ctrl_validation_results_df') is not None:
    with results_display_area:
        df_val_res_show = st.session_state.ctrl_validation_results_df
        current_rif_pa_info = st.session_state.get('ctrl_current_rif_pa_info', {})
        
        if 'rif_pa' in current_rif_pa_info: st.subheader(f"📄 Risultati Verifica per Rif. PA: `{current_rif_pa_info['rif_pa']}` (da file SIFER)")
        else: st.subheader("🔍 Risultati Verifica Dati Caricati da File SIFER")

        cols_disp_val = ['Riga','Bambino','Esito CF','Esito Data Mandato','Esito D=A+B+C','Esito Regole Contr.FSE','Esito Contr.Formali 5%', "Verifica Max 300€ FSE per Bambino (batch)", 'Errori Bloccanti']
        actual_cols_val_disp = [col for col in cols_disp_val if col in df_val_res_show.columns]
        if not df_val_res_show.empty:
            st.dataframe(df_val_res_show[actual_cols_val_disp], use_container_width=True, hide_index=True)
        else:
            st.info("Nessun risultato di validazione da mostrare.")

        has_errors_display = st.session_state.get('ctrl_has_blocking_errors', True)
        df_validated_for_db_prep = st.session_state.get('ctrl_df_internal_for_validation')

        if not has_errors_display and df_validated_for_db_prep is not None:
            st.success("✅ Verifiche OK. Pronto per salvataggio nel DB.")
            df_to_save_db = df_validated_for_db_prep.copy()
            df_to_save_db['id_trasmissione'] = str(uuid.uuid4())
            
            df_to_save_db['controlli_formali'] = round(df_to_save_db['valore_contributo_fse'] * 0.05, 2)
            
            cols_to_drop_for_db = ['codice_fiscale_bambino_pulito', 'data_mandato_originale', 'controlli_formali_dichiarati']
            df_to_save_db.drop(columns=cols_to_drop_for_db, inplace=True, errors='ignore')
            
            for col_db in DB_COLS_ATTESE:
                if col_db not in df_to_save_db.columns:
                    if col_db in ['cup', 'distretto', 'comune_capofila', 'comune_centro_estivo']:
                         df_to_save_db[col_db] = None if pd.isna(df_to_save_db.get(col_db)) else df_to_save_db.get(col_db) # Mantieni se già popolato
                    elif col_db not in df_to_save_db: 
                         df_to_save_db[col_db] = 0.0 if 'importo' in col_db or 'contributo' in col_db or 'retta' in col_db or 'frequenza' in col_db else None
            
            df_final_for_db = df_to_save_db.reindex(columns=DB_COLS_ATTESE)

            st.session_state.ctrl_df_ready_for_db = df_final_for_db

            with st.expander("🔍 Anteprima Dati da Salvare nel DB", expanded=False):
                df_preview = df_final_for_db.copy()
                if 'data_mandato' in df_preview.columns:
                     df_preview['data_mandato'] = pd.to_datetime(df_preview['data_mandato'], errors='coerce').dt.strftime('%d/%m/%Y').fillna('')
                st.dataframe(df_preview, use_container_width=True, hide_index=True)
        
        elif has_errors_display:
            st.error("🚫 Rilevati errori bloccanti (❌). Correggere il file CSV SIFER e ricaricare.")
            st.session_state.ctrl_df_ready_for_db = None

if st.session_state.get('ctrl_df_ready_for_db') is not None and not st.session_state.get('ctrl_has_blocking_errors', True):
    if st.button("💾 Salva Dati Verificati nel DB", key="save_ctrl_data_btn", type="primary"):
        with results_display_area, st.spinner("Salvataggio nel DB..."):
            df_to_persist = st.session_state.ctrl_df_ready_for_db
            rif_pa_persist = df_to_persist['rif_pa'].iloc[0] if not df_to_persist.empty and 'rif_pa' in df_to_persist.columns else "N/A_RIFPA"
            
            if check_rif_pa_exists(rif_pa_persist):
                 st.error(f"🚨 ERRORE CRITICO: Rif. PA '{rif_pa_persist}' già presente. Salvataggio annullato.")
                 log_activity(USERNAME_CTRL, "SAVE_BLOCKED_DUPLICATE_RIFPA_FINAL", f"Rif. PA: {rif_pa_persist}")
            else:
                success_db, msg_db = add_multiple_spese(df_to_persist, USERNAME_CTRL)
                if success_db:
                    st.success(f"✅ {msg_db}")
                    log_activity(USERNAME_CTRL, "DATA_SAVED_BY_CONTROLLER", f"Rif.PA: {rif_pa_persist}, Righe: {len(df_to_persist)}")
                    st.session_state.ctrl_df_sifer_loaded = None
                    st.session_state.ctrl_df_internal_for_validation = None
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