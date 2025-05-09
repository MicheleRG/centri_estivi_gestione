#/app.py
import streamlit as st
import pandas as pd
import yaml
from yaml.loader import SafeLoader
import streamlit_authenticator as stauth
from utils.db import init_db, log_activity
from utils.common_utils import (
    sanitize_filename_component, convert_df_to_excel_bytes, generate_timestamp_filename,
    parse_excel_currency, validate_rif_pa_format,
    run_detailed_validations
)
import os
from io import StringIO

# Configurazione pagina
st.set_page_config(page_title="Comunicazione Spese Centri Estivi", layout="wide", initial_sidebar_state="expanded")

# --- Costanti ---
NOMI_COLONNE_PASTED_DATA = [
    'numero_mandato','data_mandato','comune_titolare_mandato','importo_mandato',
    'comune_centro_estivo','centro_estivo','genitore_cognome_nome','bambino_cognome_nome',
    'codice_fiscale_bambino','valore_contributo_fse','altri_contributi',
    'quota_retta_destinatario','totale_retta','numero_settimane_frequenza',
    'controlli_formali_dichiarati'
]

COLONNE_OUTPUT_FINALE_SIFER = [
    'rif_pa', 'cup', 'distretto', 'comune_capofila', 'numero_mandato', 'data_mandato', 
    'comune_titolare_mandato', 'importo_mandato', 'comune_centro_estivo', 'centro_estivo', 
    'genitore_cognome_nome', 'bambino_cognome_nome', 'codice_fiscale_bambino',
    'valore_contributo_fse', 'altri_contributi', 'quota_retta_destinatario', 'totale_retta', 
    'numero_settimane_frequenza', 'controlli_formali'
]

# --- Funzioni UI ---
def display_login_form():
    st.subheader("🔑 Accesso Utente")
    try:
        with open('config.yaml') as file:
            config_data = yaml.load(file, Loader=SafeLoader)
    except FileNotFoundError:
        st.error("🚨 Errore critico: File 'config.yaml' non trovato.")
        log_activity("System_Login", "CONFIG_ERROR", "config.yaml not found")
        st.session_state['authentication_status'] = None
        st.stop()
        return None
    except yaml.YAMLError as e:
        st.error(f"🚨 Errore critico nel parsing 'config.yaml': {e}.")
        log_activity("System_Login", "CONFIG_YAML_ERROR", str(e))
        st.session_state['authentication_status'] = None
        st.stop()
        return None
    except Exception as e:
        st.error(f"🚨 Errore critico caricamento config.yaml: {e}")
        log_activity("System_Login", "CONFIG_LOAD_ERROR", str(e))
        st.session_state['authentication_status'] = None
        st.stop()
        return None

    try:
        authenticator = stauth.Authenticate(
            config_data['credentials'],
            config_data['cookie']['name'],
            config_data['cookie']['key'],
            config_data['cookie']['expiry_days'],
        )
        st.session_state['authenticator'] = authenticator
    except KeyError as e:
        st.error(f"🚨 Errore config autenticazione: chiave '{e}' mancante.")
        log_activity("System_Login", "AUTH_INIT_CONFIG_KEY_ERROR", str(e))
        st.session_state['authentication_status'] = None
        st.stop()
        return None
    except Exception as e:
        st.error(f"🚨 Errore init autenticazione: {e}")
        log_activity("System_Login", "AUTH_INIT_ERROR", str(e))
        st.session_state['authentication_status'] = None
        st.stop()
        return None

    name, authentication_status, username = None, None, None
    try:
        name, authentication_status, username = authenticator.login(
            fields={'Form name': 'Accedi al sistema', 'Username': 'Nome Utente', 'Password': 'Password'},
            location='main'
        )
    except KeyError as e: # Può accadere con cookie corrotti o problemi di session_state
        st.error(f"⚠️ Errore (KeyError) login: '{e}'. Prova a cancellare i cookie del browser e ricaricare.")
        log_activity("System_Login", "LOGIN_KEY_ERROR", str(e))
        authentication_status = None
    except Exception as e_login:
        st.error(f"⚠️ Errore generico login: {e_login}")
        log_activity("System_Login", "LOGIN_WIDGET_ERROR", str(e_login))
        authentication_status = None

    st.session_state['authentication_status'] = authentication_status

    if authentication_status is True:
        st.session_state.update({'name': name, 'username': username})
        try:
            user_config = config_data['credentials']['usernames'].get(username, {})
            st.session_state['user_role'] = user_config.get('role', 'user')
            log_activity(username, "LOGIN_SUCCESS", f"Role: {st.session_state['user_role']}")
        except KeyError: # Dovrebbe essere già gestito da .get, ma per sicurezza
            st.session_state['user_role'] = 'user'
            log_activity(username, "LOGIN_CONFIG_WARNING", f"Ruolo utente per '{username}' non trovato, default 'user'.")
            st.warning(f"Configurazione ruolo utente per '{username}' non trovata. Contattare admin.")
            
    elif authentication_status is False:
        st.error('🚫 Username o password non corretti.')
        if username: # Logga il tentativo fallito solo se è stato inserito un username
            log_activity(username, "LOGIN_FAILED_CREDENTIALS")
            
    return authentication_status


def render_richiedente_form(username_param: str):
    st.title("📝 Comunicazione Spesa Centri Estivi (Verifica e Download)")
    log_activity(username_param, "PAGE_VIEW", "Richiedente - Verifica e Download")

    st.markdown("Benvenuto! Inserisci dati, incolla spese da Excel (15 colonne), verifica e scarica.")
    st.info("**Nota:** I dati verificati qui **NON** vengono salvati automaticamente. Dovrai caricare il file CSV scaricato nel sistema SIFER, se previsto.")

    st.subheader("1. Dati Generali del Documento")
    
    # Mostra errore Rif. PA se presente nello stato sessione (dal precedente tentativo di submit)
    if 'rif_pa_error_message' in st.session_state and st.session_state.rif_pa_error_message:
        st.error(st.session_state.rif_pa_error_message)
        # Pulisci il messaggio d'errore dopo averlo mostrato, così non appare al prossimo refresh
        # se non c'è un nuovo submit. Potrebbe essere necessario un rerun per farlo sparire subito
        # se l'utente non interagisce più con il form.
        # Per ora lo lasciamo; sparirà al prossimo submit valido o interazione che causa rerun.

    with st.expander("Inserisci/Modifica Dati Documento", expanded=not st.session_state.get('metadati_confermati_richiedente', False)):
        with st.form("metadati_documento_form_richiedente"):
            doc_meta = st.session_state.doc_metadati_richiedente
            c1, c2 = st.columns(2)
            # Il valore di rif_pa_input viene pre-popolato da doc_metadati_richiedente['rif_pa']
            # che viene aggiornato anche in caso di errore per mantenere l'input dell'utente.
            rif_pa_input_val_form = c1.text_input("Rif. PA n° (AAAA-NUMERO/RER)", value=doc_meta.get('rif_pa', ''), key="rich_rifpa_input_widget")
            cup_val_form = c2.text_input("CUP", value=doc_meta.get('cup', ''), key="rich_cup_widget")
            distretto_val_form = c1.text_input("Distretto", value=doc_meta.get('distretto', ''), key="rich_distr_widget")
            comune_capofila_val_form = c2.text_input("Comune/Unione Capofila", value=doc_meta.get('comune_capofila', ''), key="rich_capofila_widget")
            
            metadati_submitted = st.form_submit_button("✅ Conferma Dati Generali")

            if metadati_submitted:
                # Aggiorna sempre i valori in session_state con quelli del form PRIMA della validazione
                # così se c'è un errore, l'utente vede l'input che ha appena fornito.
                st.session_state.doc_metadati_richiedente = {
                    'rif_pa': rif_pa_input_val_form.strip(), 
                    'cup': cup_val_form.strip(), 
                    'distretto': distretto_val_form.strip(), 
                    'comune_capofila': comune_capofila_val_form.strip()
                }

                is_valid_rif, rif_message = validate_rif_pa_format(rif_pa_input_val_form)
                if is_valid_rif:
                    st.session_state.metadati_confermati_richiedente = True
                    st.session_state.rif_pa_error_message = "" # Pulisci eventuale messaggio d'errore precedente
                    st.success(f"Dati generali confermati. {rif_message}") # Mostra successo immediatamente
                    if not all([cup_val_form, distretto_val_form, comune_capofila_val_form]):
                        st.warning("Alcuni campi (CUP, Distretto, Capofila) sono vuoti. Saranno vuoti nel file finale.")
                else:
                    # Non mostrare st.error qui, sarà gestito fuori dal form dopo il rerun
                    st.session_state.metadati_confermati_richiedente = False
                    st.session_state.rif_pa_error_message = rif_message # Salva messaggio d'errore per mostrarlo dopo rerun
                
                log_activity(username_param, "METADATA_SUBMITTED_RICHIEDENTE", f"RifPA: {rif_pa_input_val_form}, Valid: {is_valid_rif}")
                st.rerun() # Rerun per aggiornare l'expander e mostrare il messaggio d'errore fuori dal form
                
    if not st.session_state.get('metadati_confermati_richiedente', False):
        # Se i metadati non sono confermati E non c'è un messaggio d'errore specifico per Rif.PA da mostrare
        # (perché potrebbe essere già stato mostrato sopra), allora mostra il warning generico.
        if not st.session_state.get('rif_pa_error_message'):
             st.warning("☝️ Inserisci e conferma i Dati Generali del Documento (con Rif. PA nel formato corretto) per procedere.")
        st.stop() # Si ferma qui se i metadati non sono confermati (o Rif PA non valido)
    else:
        # Se siamo qui, i metadati sono confermati e il Rif PA è valido.
        # Pulisci il messaggio d'errore se per caso fosse rimasto.
        st.session_state.rif_pa_error_message = ""
        doc_meta_show = st.session_state.doc_metadati_richiedente
        st.markdown(f"**Riferimenti Documento:** Rif. PA: `{doc_meta_show['rif_pa']}`, CUP: `{doc_meta_show.get('cup','N/A')}`, Distr: `{doc_meta_show.get('distretto','N/A')}`, Capofila: `{doc_meta_show.get('comune_capofila','N/A')}`")
    
    st.markdown("---")
    st.subheader("2. Incolla i Dati delle Spese da Excel")
    pasted_data = st.text_area(
        f"Incolla qui le {len(NOMI_COLONNE_PASTED_DATA)} colonne (solo valori, **NO** intestazioni):",
        height=200, key="pasted_excel_data_richiedente",
        help="Formati data (GG/MM/AAAA) e valute (1.234,56 o 1234.56) accettati."
    )

    results_container = st.container() 
    if pasted_data:
        try:
            log_activity(username_param, "PASTE_DATA_PROCESSING_RICHIEDENTE", f"Len: {len(pasted_data)} chars")
            df_pasted_raw = pd.read_csv(StringIO(pasted_data), sep='\t', header=None, dtype=str, na_filter=False)

            if df_pasted_raw.shape[1] != len(NOMI_COLONNE_PASTED_DATA):
                results_container.error(f"🚨 Errore: Incollate {df_pasted_raw.shape[1]} colonne, attese {len(NOMI_COLONNE_PASTED_DATA)}.")
                st.stop()

            df_pasted_raw.columns = NOMI_COLONNE_PASTED_DATA
            df_check = df_pasted_raw.copy()

            df_check['codice_fiscale_bambino_pulito'] = df_check['codice_fiscale_bambino'].astype(str).str.upper().str.strip()
            df_check['data_mandato_originale'] = df_check['data_mandato']
            df_check['data_mandato'] = pd.to_datetime(df_check['data_mandato_originale'], errors='coerce', dayfirst=True).dt.date

            currency_cols = ['importo_mandato','valore_contributo_fse','altri_contributi',
                               'quota_retta_destinatario','totale_retta','controlli_formali_dichiarati']
            for col in currency_cols:
                df_check[col] = df_check[col].apply(parse_excel_currency)
            
            df_check['numero_settimane_frequenza'] = df_check.get('numero_settimane_frequenza', pd.Series(dtype='str')).apply(
                lambda x: int(float(str(x).replace(',','.'))) if pd.notna(x) and str(x).strip().replace('.','',1).replace(',','.',1).isdigit() else 0
            )

            df_validation_results, has_blocking_errors_rich = run_detailed_validations(
                df_input=df_check,
                cf_col_clean_name='codice_fiscale_bambino_pulito',
                original_date_col_name='data_mandato_originale',
                parsed_date_col_name='data_mandato',
                declared_formal_controls_col_name='controlli_formali_dichiarati',
                row_offset_val=1
            )
            
            results_container.subheader("3. Risultati della Verifica Dati")
            cols_order_results = ['Riga','Bambino','Esito CF','Esito Data Mandato','Esito D=A+B+C',
                                  'Esito Regole Contr.FSE','Esito Contr.Formali 5%', 
                                  "Verifica Max 300€ FSE per Bambino (batch)", 'Errori Bloccanti']
            actual_cols_to_display = [col for col in cols_order_results if col in df_validation_results.columns]
            if not df_validation_results.empty:
                 results_container.dataframe(df_validation_results[actual_cols_to_display], use_container_width=True, hide_index=True)
            else:
                 results_container.info("Nessun risultato di validazione da mostrare.")

            if not has_blocking_errors_rich:
                results_container.success("✅ Verifiche OK. Puoi scaricare i dati.")
                log_activity(username_param, "VALIDATION_SUCCESS_RICHIEDENTE", f"Righe: {len(df_check)}")
                
                df_validated_output = df_check.copy()
                for key, value in st.session_state.doc_metadati_richiedente.items():
                    df_validated_output[key] = value
                
                df_validated_output['controlli_formali'] = round(df_validated_output['valore_contributo_fse'] * 0.05, 2)
                
                if 'codice_fiscale_bambino' in df_validated_output.columns:
                     df_validated_output.drop(columns=['codice_fiscale_bambino'], inplace=True, errors='ignore')
                if 'codice_fiscale_bambino_pulito' in df_validated_output.columns:
                    df_validated_output.rename(columns={'codice_fiscale_bambino_pulito': 'codice_fiscale_bambino'}, inplace=True)

                df_output_sifer = df_validated_output[[col for col in COLONNE_OUTPUT_FINALE_SIFER if col in df_validated_output.columns]].copy()

                with results_container.expander("⬇️ 4. Anteprima e Download", expanded=True):
                    df_display_anteprima = df_output_sifer.copy()
                    if 'data_mandato' in df_display_anteprima.columns:
                        df_display_anteprima['data_mandato'] = pd.to_datetime(df_display_anteprima['data_mandato'], errors='coerce').dt.strftime('%d/%m/%Y').fillna('')
                    st.dataframe(df_display_anteprima, use_container_width=True, hide_index=True)

                    rif_pa_s = sanitize_filename_component(st.session_state.doc_metadati_richiedente.get('rif_pa',''))
                    df_export_csv = df_output_sifer.copy()
                    if 'data_mandato' in df_export_csv.columns:
                        df_export_csv['data_mandato'] = pd.to_datetime(df_export_csv['data_mandato'], errors='coerce').dt.strftime('%d/%m/%Y').fillna('')
                    
                    csv_bytes = df_export_csv.to_csv(index=False, sep=';', decimal=',', encoding='utf-8-sig').encode('utf-8-sig')
                    fn_csv = generate_timestamp_filename("datiSIFER", rif_pa_s) + ".csv"
                    st.download_button("📥 Scarica CSV SIFER", csv_bytes, fn_csv, 'text/csv', key="rich_dl_csv")
                    
                    excel_bytes = convert_df_to_excel_bytes(df_output_sifer)
                    fn_excel = generate_timestamp_filename("datiSIFER_Excel", rif_pa_s) + ".xlsx"
                    st.download_button("📄 Scarica Excel", excel_bytes, fn_excel, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key="rich_dl_excel")

                with results_container.expander("📊 5. Quadro di Controllo", expanded=True):
                    qc_data = {
                        "Voce": ["Tot. costi diretti (A - Contr. FSE)", "Quota costi indiretti (5% di A)", 
                                 "Contr. complessivo erogabile (A + 5%A)", "Tot. quote a carico destinatario (C)"],
                        "Valore (€)": [df_output_sifer['valore_contributo_fse'].sum(), df_output_sifer['controlli_formali'].sum(),
                                     df_output_sifer['valore_contributo_fse'].sum() + df_output_sifer['controlli_formali'].sum(),
                                     df_output_sifer['quota_retta_destinatario'].sum()]
                    }
                    df_qc = pd.DataFrame(qc_data)
                    df_qc_display = df_qc.copy()
                    df_qc_display["Valore (€)"] = df_qc_display["Valore (€)"].apply(lambda x: f"{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
                    st.dataframe(df_qc_display, hide_index=True, use_container_width=True)
                    
                    qc_csv_bytes = df_qc.to_csv(index=False,sep=';',decimal=',',encoding='utf-8-sig').encode('utf-8-sig')
                    fn_qc_csv = generate_timestamp_filename("QuadroControllo", rif_pa_s, False) + ".csv"
                    st.download_button("📥 Scarica Quadro CSV", qc_csv_bytes, fn_qc_csv, 'text/csv', key="rich_qc_csv")

                    qc_excel_bytes = convert_df_to_excel_bytes(df_qc)
                    fn_qc_excel = generate_timestamp_filename("QuadroControllo_Excel", rif_pa_s, False) + ".xlsx"
                    st.download_button("📄 Scarica Quadro Excel", qc_excel_bytes, fn_qc_excel, mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key="rich_qc_excel")
            
            elif df_validation_results.empty and not pasted_data.strip():
                results_container.info("Nessun dato valido incollato.")
            else: # Ci sono errori bloccanti
                 results_container.error("🚫 Rilevati errori bloccanti (❌). Correggere i dati e reincollare.")
                 log_activity(username_param, "VALIDATION_FAILED_RICHIEDENTE", "Errori bloccanti rilevati.")
        
        except pd.errors.EmptyDataError: 
             results_container.warning("⚠️ Nessun dato da elaborare. Assicurati di aver incollato correttamente.")
        except ValueError as ve:
             results_container.error(f"🚨 Errore nella conversione dei dati: {ve}. Controlla formati numerici e date.")
             log_activity(username_param, "PARSING_ERROR_RICHIEDENTE", str(ve))
        except Exception as e: 
             results_container.error(f"🚨 Errore imprevisto durante l'elaborazione: {e}")
             log_activity(username_param, "PROCESSING_ERROR_RICHIEDENTE", str(e))
             st.exception(e)


def main_app_router():
    user_role = st.session_state.get('user_role', 'user')
    username = st.session_state.get('username', 'N/D')
    name = st.session_state.get('name', 'Utente')
    auth_obj = st.session_state.get('authenticator')

    if not auth_obj:
        st.error("🚨 Sessione di autenticazione non valida o scaduta. Effettua nuovamente il login.")
        st.session_state['authentication_status'] = None
        if st.button("🔄 Ricarica e Vai al Login"): st.rerun()
        st.stop()
        return

    st.sidebar.title(f"👤 Utente: {name}")
    st.sidebar.write(f"🔖 Ruolo: {user_role.capitalize()}")
    auth_obj.logout('🚪 Logout', 'sidebar', key='main_logout_btn')

    if user_role == 'richiedente':
        render_richiedente_form(username)
    elif user_role in ['controllore', 'admin']:
        st.success(f"Benvenuto/a {name}! Sei autenticato/a come {user_role.capitalize()}.")
        st.info("Seleziona un'opzione dalla navigazione laterale (nelle sezioni 'pages') per accedere alle funzionalità specifiche del tuo ruolo.")
    else:
        st.error("🚫 Ruolo utente non riconosciuto o non autorizzato. Contattare l'amministratore.")
        log_activity(username, "UNKNOWN_ROLE_ACCESS", f"Ruolo: {user_role}")

if __name__ == "__main__":
    os.makedirs("database", exist_ok=True, mode=0o755) 
    
    # Esegui init_db solo una volta per sessione
    if 'db_initialized' not in st.session_state:
        try:
            init_db() # Non passa connessione, init_db gestirà la sua
            st.session_state.db_initialized = True
            # Usare un username specifico per i log di sistema all'avvio se possibile
            log_activity("System_AppMain", "APP_STARTUP", "Database inizializzato per la sessione.")
        except Exception as e_db:
            st.error(f"🚨 Errore critico durante l'inizializzazione del database: {e_db}")
            log_activity("System_AppMain", "DB_INIT_ERROR", str(e_db))
            st.stop()

    # Inizializzazione `session_state` (chiavi di default)
    default_session_keys = {
        'authentication_status': None, 'name': None, 'username': None, 
        'authenticator': None, 'user_role': None,
        'doc_metadati_richiedente': st.session_state.get('doc_metadati_richiedente', {'rif_pa': '', 'cup': '', 'distretto': '', 'comune_capofila': ''}), # Mantieni valori esistenti se ci sono
        'metadati_confermati_richiedente': st.session_state.get('metadati_confermati_richiedente', False),
        'rif_pa_error_message': st.session_state.get('rif_pa_error_message', "") # Per messaggio errore Rif.PA
    }
    for key, default_value in default_session_keys.items():
        st.session_state.setdefault(key, default_value)

    if not st.session_state.get('authentication_status'):
        auth_status = display_login_form()
        if not auth_status: st.stop()
    
    if st.session_state.get('authentication_status') is True: 
        main_app_router()
#/app.py