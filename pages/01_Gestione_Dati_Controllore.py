#cartella/pages/01_Gestione_Dati_Controllore.py
import streamlit as st
import pandas as pd
from utils.db import add_multiple_spese, log_activity, check_rif_pa_exists
from utils.common_utils import (
    sanitize_filename_component, convert_df_to_excel_bytes, generate_timestamp_filename,
    validate_codice_fiscale, parse_excel_currency, check_controlli_formali,
    check_sum_d, check_contribution_rules,
    validate_rif_pa_format # Solo validazione formato
)
import uuid

st.set_page_config(page_title="Gestione Dati Controllore", layout="wide")

# --- Autenticazione e Controllo Ruolo ---
if 'authentication_status' not in st.session_state or not st.session_state.get('authentication_status'):
    st.warning("Devi effettuare il login per accedere a questa pagina.")
    if st.button("🏠 Vai alla pagina di Login", key="ctrl_login_btn_auth_direct"):
        st.switch_page("app.py")
    st.stop()

USER_ROLE_CTRL = st.session_state.get('user_role', 'user')
USERNAME_CTRL = st.session_state.get('username', 'N/D')
NAME_CTRL = st.session_state.get('name', 'N/D')
AUTHENTICATOR_CTRL = st.session_state.get('authenticator')

if not AUTHENTICATOR_CTRL:
    st.error("Errore di sessione. Riprova il login.")
    if st.button("🏠 Riprova Login", key="ctrl_login_btn_no_auth_direct"):
        st.switch_page("app.py")
    st.stop()

if USER_ROLE_CTRL not in ['controllore', 'admin']:
    st.error("Accesso negato. Pagina riservata ai Controllori e Amministratori.")
    log_activity(USERNAME_CTRL, "PAGE_ACCESS_DENIED_CONTROLLER_PAGE", f"Tentativo da ruolo: {USER_ROLE_CTRL}")
    st.stop()

# Sidebar Utente e Logout
st.sidebar.title(f"Utente: {NAME_CTRL}")
st.sidebar.write(f"Ruolo: {USER_ROLE_CTRL.capitalize()}")
AUTHENTICATOR_CTRL.logout('Logout', 'sidebar', key='ctrl_logout_sidebar')
# --- Fine Autenticazione ---

# --- Contenuto Pagina ---
st.title("⚙️ Caricamento e Validazione Dati (Controllore)")
log_activity(USERNAME_CTRL, "PAGE_VIEW", "Controllore - Caricamento/Validazione Dati")

st.markdown("""
Questa sezione è dedicata ai **Controllori** per:
1.  Caricare un file CSV (il Rif. PA deve essere nel formato AAAA-NUMERO/RER).
2.  Verificare che non esista già una registrazione per lo stesso **Rif. PA** nel database.
3.  Eseguire controlli di validità sui dati caricati.
4.  Salvare i dati validati nel database centrale.
""")

# Widget File Uploader
uploaded_file_ctrl = st.file_uploader(
    "Carica il file CSV delle spese", 
    type=['csv'],
    help="Il file CSV deve avere ';' come separatore, ',' per i decimali. Il Rif. PA deve essere nel formato AAAA-NUMERO/RER.",
    key="ctrl_file_uploader_widget"
)

# Gestione Stato Sessione per il file caricato (usa chiavi specifiche per questa pagina)
if uploaded_file_ctrl is not None:
    # Se viene caricato un nuovo file diverso dal precedente
    if st.session_state.get('ctrl_last_uploaded_file_name') != uploaded_file_ctrl.name:
        st.session_state.ctrl_df_loaded = None
        st.session_state.ctrl_df_validated = None
        st.session_state.ctrl_errors_exist = True # Resetta flag errori
        st.session_state.ctrl_current_rif_pa = None # Resetta Rif PA corrente
        st.session_state.ctrl_last_uploaded_file_name = uploaded_file_ctrl.name # Aggiorna nome file
elif st.session_state.get('ctrl_last_uploaded_file_name') is not None:
    # Se il file viene rimosso (uploaded_file_ctrl diventa None)
    st.session_state.ctrl_df_loaded = None
    st.session_state.ctrl_df_validated = None
    st.session_state.ctrl_errors_exist = True
    st.session_state.ctrl_current_rif_pa = None
    st.session_state.ctrl_last_uploaded_file_name = None

# Container per i risultati e l'anteprima
validation_container = st.container()

# Processamento del file caricato (solo se presente e non già processato)
if uploaded_file_ctrl is not None:
    if st.session_state.get('ctrl_df_loaded') is None: # Controlla se df non è già in stato sessione
        try:
            # Lettura CSV
            df_loaded = pd.read_csv(uploaded_file_ctrl, sep=';', decimal=',', na_filter=False, dtype=str)
            st.session_state.ctrl_df_loaded = df_loaded # Salva df letto in session state
            log_activity(USERNAME_CTRL, "FILE_UPLOADED_CONTROLLER", f"File: {uploaded_file_ctrl.name}, Righe: {len(df_loaded)}")

            # Controllo Colonna e Valore Rif. PA
            if 'rif_pa' not in df_loaded.columns or df_loaded.empty:
                validation_container.error("Colonna 'rif_pa' mancante nel CSV o file vuoto.")
                st.stop()
            
            rif_pa_csv = df_loaded['rif_pa'].iloc[0]
            if pd.isna(rif_pa_csv) or not str(rif_pa_csv).strip():
                validation_container.error("Valore 'rif_pa' vuoto nella prima riga del CSV.")
                st.stop()

            # Validazione Formato Rif. PA (Stretta)
            is_valid_rif, rif_msg = validate_rif_pa_format(rif_pa_csv)
            if not is_valid_rif:
                validation_container.error(f"Rif. PA dal CSV ('{rif_pa_csv}'): {rif_msg}")
                st.stop()
            
            # Rif. PA valido
            current_rif_pa = rif_pa_csv.strip()
            st.session_state.ctrl_current_rif_pa = current_rif_pa
            validation_container.subheader(f"File Caricato: Dati per Rif. PA: {current_rif_pa}")
            validation_container.success(rif_msg) # Mostra messaggio formato corretto

            # Controllo Esistenza Rif. PA nel DB
            if check_rif_pa_exists(current_rif_pa):
                validation_container.error(f"ATTENZIONE: Esiste già una registrazione per Rif. PA '{current_rif_pa}'. Impossibile caricare.")
                st.stop() # Blocca se Rif PA esiste già
            else:
                validation_container.success(f"OK: Nessuna registrazione esistente per Rif. PA '{current_rif_pa}'.")

            # Preparazione DataFrame per validazione
            df_check = df_loaded.copy()
            
            # Prepara colonna CF pulita (per validazioni e groupby)
            if 'codice_fiscale_bambino' in df_check.columns:
                 df_check['cf_pulito'] = df_check['codice_fiscale_bambino'].astype(str).str.upper().str.strip()
            else:
                 df_check['cf_pulito'] = '' # Crea colonna vuota se manca originale

            # Parsing Date (flessibile)
            if 'data_mandato' in df_check.columns:
                df_check['data_orig'] = df_check['data_mandato'] # Conserva originale per messaggio
                df_check['data_mandato'] = pd.to_datetime(df_check['data_orig'], errors='coerce', dayfirst=True).dt.date
            else:
                validation_container.error("Colonna 'data_mandato' mancante nel file CSV.")
                st.stop()
            
            # Parsing Valute
            currency_cols = ['importo_mandato','valore_contributo_fse','altri_contributi','quota_retta_destinatario','totale_retta', 'controlli_formali']
            for col in currency_cols:
                if col in df_check.columns:
                    df_check[col] = df_check[col].apply(lambda x: parse_excel_currency(str(x)))
                else:
                    st.warning(f"Colonna '{col}' mancante nel CSV.")
                    # Imposta a 0.0 tranne 'controlli_formali' che verrà calcolato dopo
                    if col != 'controlli_formali':
                         df_check[col] = 0.0
                    else:
                         df_check[col] = None # Sarà calcolato e sovrascritto

            # Parsing Settimane
            df_check['numero_settimane_frequenza'] = df_check.get('numero_settimane_frequenza','0').apply(
                lambda x: int(float(x)) if pd.notna(x) and str(x).replace('.','',1).isdigit() else 0
            )
            
            # --- Validazioni per Riga e Aggregate ---
            validation_results = []
            st.session_state.ctrl_errors_exist = False # Resetta flag errori per questa validazione

            # Itera sulle righe per validazioni
            for index, row in df_check.iterrows():
                # Validazioni singole
                cf_ok, cf_msg = validate_codice_fiscale(row.get('cf_pulito',''))
                sum_ok, sum_msg = check_sum_d(row)
                contrib_ok, contrib_msg = check_contribution_rules(row)
                # Passa 'controlli_formali' se esiste nel CSV per confrontarlo con il calcolo
                cf5_ok, cf5_msg = check_controlli_formali(row, col_name_dichiarati='controlli_formali')

                # Validazione Data (con messaggio chiaro)
                data_obj = row.get('data_mandato')
                data_orig = str(row.get('data_orig','')).strip()
                if pd.notna(data_obj):
                    data_ok = True
                    data_fmt = data_obj.strftime('%d/%m/%Y')
                    msg_data = f"✅ Data '{data_orig}' → {data_fmt}" if data_orig != data_fmt else f"✅ OK ({data_fmt})"
                else:
                    data_ok = False
                    msg_data = f"❌ Data '{data_orig}' non riconosciuta."
                
                # Aggrega errori per la riga
                errors = []
                if not cf_ok: errors.append(cf_msg)
                if not data_ok: errors.append(msg_data)
                if not sum_ok: errors.append(sum_msg)
                if not contrib_ok: errors.append(contrib_msg)
                if not cf5_ok: errors.append(cf5_msg)

                # Aggiorna flag errori bloccanti
                if any("❌" in e for e in errors):
                    st.session_state.ctrl_errors_exist = True
                
                # Aggiungi risultato riga
                validation_results.append({
                    'Riga CSV': index + 2, 
                    'Bambino': row.get('bambino_cognome_nome','N/A'),
                    'Esito CF': cf_msg, 
                    'Esito Data': msg_data,
                    'Esito D=A+B+C': sum_msg, 
                    'Esito Regole Contr.FSE': contrib_msg, 
                    'Esito Contr.Formali 5%': cf5_msg,
                    'Errori Rilevati': "; ".join(errors) if errors else "Nessuno",
                    'Verifica Max 300€ FSE per Bambino (batch)': '⏳' # Placeholder
                })
            
            # Crea DataFrame risultati
            df_res = pd.DataFrame(validation_results)
            
            # Check aggregato Max 300€ FSE
            col_cap = "Verifica Max 300€ FSE per Bambino (batch)"
            df_res[col_cap] = '✅ OK' # Default
            
            if 'cf_pulito' in df_check.columns and 'valore_contributo_fse' in df_check.columns:
                valid_cf = df_check[df_check['cf_pulito'] != ''] # Escludi CF vuoti
                if not valid_cf.empty:
                    contrib = valid_cf.groupby('cf_pulito')['valore_contributo_fse'].sum()
                    over_cap = contrib[contrib > 300.01] # Con tolleranza
                    if not over_cap.empty:
                        st.session_state.ctrl_errors_exist = True # Errore bloccante
                        for cf, total in over_cap.items():
                            err_cap = f"❌ Superato cap 300€ ({total:.2f}€ totali)"
                            indices = df_check.index[df_check['cf_pulito'] == cf].tolist()
                            # Aggiorna le righe corrispondenti nel df dei risultati
                            for idx in indices:
                                mask = df_res['Riga CSV'] == idx + 2
                                if not mask.empty:
                                    df_res.loc[mask, col_cap] = err_cap
                                    current_errors = df_res.loc[mask, 'Errori Rilevati'].iloc[0]
                                    # Aggiungi errore anche alla colonna generale, se non già presente
                                    if err_cap not in current_errors:
                                        if current_errors == "Nessuno":
                                            df_res.loc[mask, 'Errori Rilevati'] = err_cap
                                        else:
                                            df_res.loc[mask, 'Errori Rilevati'] += "; " + err_cap

            # Visualizza Tabella Risultati
            validation_container.subheader("Risultati Verifica Dati Caricati")
            cols_disp = ['Riga CSV','Bambino','Esito CF','Esito Data','Esito D=A+B+C','Esito Regole Contr.FSE','Esito Contr.Formali 5%', col_cap, 'Errori Rilevati']
            validation_container.dataframe(df_res[cols_disp], use_container_width=True, hide_index=True)

            # --- Preparazione per Salvataggio (se non ci sono errori) ---
            if not st.session_state.ctrl_errors_exist:
                validation_container.success("Verifiche OK. Pronto per il salvataggio nel database.")
                df_save = df_check.copy() # Inizia dalla copia validata
                
                # Aggiungi ID Trasmissione e calcola Controlli Formali finali
                df_save['id_trasmissione'] = str(uuid.uuid4())
                df_save['controlli_formali'] = round(df_save['valore_contributo_fse'] * 0.05, 2)
                
                # Rimuovi/Rinomina colonne CF
                if 'codice_fiscale_bambino' in df_save.columns:
                     df_save.drop(columns=['codice_fiscale_bambino'], inplace=True, errors='ignore')
                if 'cf_pulito' in df_save.columns:
                    df_save.rename(columns={'cf_pulito':'codice_fiscale_bambino'}, inplace=True)
                
                # Definisci colonne attese dal DB
                db_cols_expected = [
                    'id_trasmissione', 'rif_pa', 'cup', 'distretto', 'comune_capofila', 
                    'numero_mandato', 'data_mandato', 'comune_titolare_mandato', 'importo_mandato',
                    'comune_centro_estivo', 'centro_estivo', 'genitore_cognome_nome', 
                    'bambino_cognome_nome', 'codice_fiscale_bambino', 'valore_contributo_fse', 
                    'altri_contributi', 'quota_retta_destinatario', 'totale_retta', 
                    'numero_settimane_frequenza', 'controlli_formali'
                ]
                
                # Assicura che tutte le colonne DB esistano e imposta default se necessario
                for col in db_cols_expected:
                    if col not in df_save.columns:
                        # Imposta default specifici per tipo (o più genericamente None)
                        default_val = 0.0 if col in ['importo_mandato','valore_contributo_fse','altri_contributi','quota_retta_destinatario','totale_retta', 'controlli_formali'] else 0 if col == 'numero_settimane_frequenza' else None
                        st.warning(f"Colonna DB '{col}' mancante nel CSV, verrà impostata a '{default_val}'.")
                        df_save[col] = default_val
                
                # Rimuovi colonne temporanee/ausiliarie non necessarie per il DB
                cols_to_drop_for_db = ['data_orig', 'data_parsed_temp_ctrl', 'cf_pulito', 'data_mandato_originale_ctrl', 'controlli_formali_dichiarati'] # Rimuovi anche quella dichiarata se esiste
                df_save = df_save.drop(columns=cols_to_drop_for_db, errors='ignore')
                
                # Seleziona solo le colonne attese dal DB nell'ordine corretto
                existing_final_cols_db = [c for c in db_cols_expected if c in df_save.columns]
                df_save_final = df_save[existing_final_cols_db]
                
                # Salva il DataFrame pronto per il salvataggio in session state
                st.session_state.ctrl_df_validated = df_save_final

                # Mostra Anteprima
                with validation_container.expander("Anteprima Dati da Salvare nel Database", expanded=False):
                    df_preview = st.session_state.ctrl_df_validated.copy()
                    # Formatta date per l'anteprima
                    if 'data_mandato' in df_preview.columns:
                         df_preview['data_mandato'] = df_preview['data_mandato'].apply(
                             lambda x: x.strftime('%d/%m/%Y') if pd.notna(x) and hasattr(x,'strftime') else ''
                         )
                    st.dataframe(df_preview, use_container_width=True, hide_index=True)
            
            else: # Se ci sono errori bloccanti
                validation_container.error("Sono stati rilevati errori bloccanti (❌). Correggere il file CSV e ricaricarlo.")
                st.session_state.ctrl_df_validated = None # Nessun df pronto per il salvataggio

        # --- Gestione Errori Generali ---
        except pd.errors.ParserError as pe:
            st.error(f"Errore di parsing del CSV: {pe}. Verificare separatore e formato.")
            log_activity(USERNAME_CTRL, "CSV_PARSE_ERROR_CONTROLLER", str(pe))
            st.session_state.ctrl_df_loaded = None # Resetta stato
        except ValueError as ve:
            st.error(f"Errore nella conversione dei dati: {ve}. Controlla formati numerici e date.")
            log_activity(USERNAME_CTRL, "DATA_CONVERSION_ERROR_CONTROLLER", str(ve))
            st.session_state.ctrl_df_loaded = None
        except Exception as e:
            st.error(f"Errore imprevisto durante l'elaborazione: {e}")
            log_activity(USERNAME_CTRL, "FILE_PROCESSING_ERROR_CONTROLLER", str(e))
            st.exception(e) # Mostra traceback per debug
            st.session_state.ctrl_df_loaded = None

# --- Bottone di Salvataggio ---
# Mostra il bottone solo se un DataFrame è stato validato con successo e non ci sono errori bloccanti
if st.session_state.get('ctrl_df_validated') is not None and not st.session_state.get('ctrl_errors_exist', True):
    if st.button("💾 Salva Dati Verificati nel Database Centrale", key="save_controller_data_final_btn"):
        with st.spinner("Salvataggio in corso..."):
            df_to_save = st.session_state.ctrl_df_validated
            rif_pa_save = df_to_save['rif_pa'].iloc[0]
            
            # Doppio controllo esistenza Rif PA prima di scrivere
            if check_rif_pa_exists(rif_pa_save):
                 st.error(f"ERRORE CRITICO: Il Rif. PA '{rif_pa_save}' risulta già presente nel DB (controllo finale). Salvataggio annullato.")
                 log_activity(USERNAME_CTRL, "SAVE_BLOCKED_DUPLICATE_RIFPA_FINAL_CHECK", f"Rif. PA: {rif_pa_save}")
            else:
                # Chiama la funzione per inserire i dati nel DB
                success, msg = add_multiple_spese(df_to_save, USERNAME_CTRL)
                if success:
                    st.success(msg)
                    log_activity(USERNAME_CTRL, "DATA_SAVED_BY_CONTROLLER", f"Rif.PA: {rif_pa_save}, Righe: {len(df_to_save)}")
                    # Resetta lo stato dopo salvataggio per permettere nuovo caricamento
                    st.session_state.ctrl_df_loaded = None
                    st.session_state.ctrl_df_validated = None
                    st.session_state.ctrl_errors_exist = True
                    st.session_state.ctrl_current_rif_pa = None
                    st.session_state.ctrl_last_uploaded_file_name = None 
                    st.rerun() # Ricarica la pagina
                else:
                    # Mostra errore di salvataggio
                    st.error(f"Errore durante il salvataggio nel database: {msg}")
                    log_activity(USERNAME_CTRL, "DATA_SAVE_FAILED_CONTROLLER", msg)

#cartella/pages/01_Gestione_Dati_Controllore.py