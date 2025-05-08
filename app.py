#cartella/app.py
import streamlit as st
import pandas as pd
import yaml
from yaml.loader import SafeLoader
import streamlit_authenticator as stauth
from datetime import datetime
from utils.db import init_db, log_activity
from utils.common_utils import (
    sanitize_filename_component, convert_df_to_excel_bytes, generate_timestamp_filename,
    validate_codice_fiscale, parse_excel_currency, check_controlli_formali,
    check_sum_d, check_contribution_rules,
    validate_rif_pa_format # Solo validazione formato
)
import os
from io import StringIO
import numpy as np
import uuid

# Configurazione pagina
st.set_page_config(page_title="Comunicazione Spese Centri Estivi", layout="wide", initial_sidebar_state="expanded")

# --- Funzioni UI ---
def display_login_form():
    """Visualizza il form di login e gestisce l'autenticazione."""
    st.subheader("Accesso Utente")
    try:
        with open('config.yaml') as file:
            config_data = yaml.load(file, Loader=SafeLoader)
    except FileNotFoundError:
        st.error("Errore: File 'config.yaml' non trovato.")
        log_activity("System", "CONFIG_ERROR", "config.yaml not found")
        st.session_state['authentication_status'] = None
        st.stop()
        return None
    except yaml.YAMLError as e:
        st.error(f"Errore nel parsing del file 'config.yaml': {e}.")
        log_activity("System", "CONFIG_YAML_ERROR", str(e))
        st.session_state['authentication_status'] = None
        st.stop()
        return None
    except Exception as e:
        st.error(f"Errore critico nel caricamento di config.yaml: {e}")
        log_activity("System", "CONFIG_LOAD_ERROR", str(e))
        st.session_state['authentication_status'] = None
        st.stop()
        return None

    try:
        authenticator = stauth.Authenticate(
            config_data['credentials'],
            config_data['cookie']['name'],
            config_data['cookie']['key'],
            config_data['cookie']['expiry_days']
        )
        # Memorizza l'oggetto authenticator in session state per usarlo dopo (es. logout)
        st.session_state['authenticator'] = authenticator
    except KeyError as e:
        st.error(f"Errore nella configurazione: chiave '{e}' mancante.")
        log_activity("System", "AUTH_INIT_CONFIG_KEY_ERROR", str(e))
        st.session_state['authentication_status'] = None
        st.stop()
        return None
    except Exception as e:
        st.error(f"Errore durante l'inizializzazione del sistema di autenticazione: {e}")
        log_activity("System", "AUTH_INIT_ERROR", str(e))
        st.session_state['authentication_status'] = None
        st.stop()
        return None

    # Variabili per il ritorno della funzione login
    name, authentication_status, username = None, None, None
    
    try:
        # Chiamata al widget di login effettivo
        name, authentication_status, username = authenticator.login()
        
    except KeyError as e:
        # Gestisce errori potenziali legati a cookie o configurazione corrotta
        st.error(f"Errore (KeyError) durante il tentativo di login: '{e}'. Prova a cancellare i cookie del browser.")
        log_activity("System", "LOGIN_KEY_ERROR", str(e))
        authentication_status = None
        st.session_state['authentication_status'] = None
    except Exception as e_login:
        # Gestisce altri errori imprevisti durante il login
        st.error(f"Si è verificato un errore generico durante il processo di login: {e_login}")
        log_activity("System", "LOGIN_WIDGET_ERROR", str(e_login))
        authentication_status = None
        st.session_state['authentication_status'] = None
    
    # Aggiorna lo stato di autenticazione in session_state
    st.session_state['authentication_status'] = authentication_status

    if authentication_status is True:
        # Se l'autenticazione ha successo, memorizza nome, username e ruolo
        st.session_state.update({'name': name, 'username': username})
        try:
            # Recupera il ruolo dal file di configurazione
            st.session_state['user_role'] = config_data['credentials']['usernames'][username].get('role', 'user')
            log_activity(username, "LOGIN_SUCCESS", f"Role: {st.session_state['user_role']}")
        except KeyError:
            # Se l'utente non è trovato o manca la chiave 'role', assegna ruolo 'user' di default
            st.session_state['user_role'] = 'user'
            log_activity(username, "LOGIN_CONFIG_WARNING", f"Ruolo utente per '{username}' non trovato, impostato a 'user'.")
            st.warning(f"Configurazione del ruolo utente per '{username}' non trovata. Contattare l'amministratore.")
            
    elif authentication_status is False:
        # Se username/password errati
        st.error('Username o password non corretti.')
        if username: # Logga il tentativo fallito se è stato inserito un username
            log_activity(username, "LOGIN_FAILED_CREDENTIALS")
            
    # Ritorna lo stato di autenticazione (True, False, None)
    return authentication_status

# Funzione per il Richiedente
def render_richiedente_form(username_param):
    """Visualizza e gestisce il form per l'utente Richiedente."""
    st.title("📝 Comunicazione Spesa Centri Estivi (Verifica e Download)")
    log_activity(username_param, "PAGE_VIEW", "Richiedente - Verifica e Download")

    st.markdown("""
    Benvenuto! Questa sezione ti permette di:
    1.  Inserire i dati generali del tuo documento (il Rif. PA deve essere nel formato ANNO-OPERAZIONE/RER).
    2.  Copiare e incollare le righe di spesa da un foglio Excel.
    3.  Verificare la correttezza formale e sostanziale dei dati inseriti (incluse duplicazioni di Codice Fiscale).
    4.  Scaricare i dati "normalizzati" e il quadro di controllo in formato CSV o Excel.
    """)
    st.markdown("**Nota:** I dati verificati qui **NON** vengono salvati automaticamente. Dovrai caricare il file CSV scaricato nel sistema SIFER.")

    # --- Sezione 1: Metadati Documento ---
    st.subheader("1. Dati Generali del Documento")
    # Inizializzazione stato sessione se non presente
    if 'doc_metadati_richiedente' not in st.session_state:
        st.session_state.doc_metadati_richiedente = {'rif_pa': '', 'cup': '', 'distretto': '', 'comune_capofila': ''}
    if 'metadati_confermati_richiedente' not in st.session_state:
        st.session_state.metadati_confermati_richiedente = False

    with st.expander("Inserisci/Modifica Dati Documento", expanded=not st.session_state.metadati_confermati_richiedente):
        with st.form("metadati_documento_form_richiedente"):
            doc_meta = st.session_state.doc_metadati_richiedente
            c1, c2 = st.columns(2)
            # Input per i metadati
            rif_pa_input_val = c1.text_input("Rif. PA n° (formato: AAAA-NUMERO/RER)", value=doc_meta.get('rif_pa', ''), key="rich_rifpa_input")
            cup_val = c2.text_input("CUP", value=doc_meta.get('cup', ''), key="rich_cup")
            distretto_val = c1.text_input("Distretto", value=doc_meta.get('distretto', ''), key="rich_distr")
            comune_capofila_val = c2.text_input("Comune/Unione Capofila", value=doc_meta.get('comune_capofila', ''), key="rich_capofila")
            
            metadati_submitted = st.form_submit_button("✅ Conferma Dati Generali")

            if metadati_submitted:
                # Validazione del formato Rif. PA
                is_valid_rif, rif_message = validate_rif_pa_format(rif_pa_input_val)
                
                if is_valid_rif:
                    st.success(rif_message)
                    # Aggiorna lo stato sessione con i dati validati/inseriti
                    st.session_state.doc_metadati_richiedente = {
                        'rif_pa': rif_pa_input_val.strip(), # Salva Rif PA validato
                        'cup': cup_val, 
                        'distretto': distretto_val, 
                        'comune_capofila': comune_capofila_val
                    }
                    st.session_state.metadati_confermati_richiedente = True
                    # Avviso se altri campi sono vuoti
                    if not all([cup_val, distretto_val, comune_capofila_val]):
                        st.warning("Dati generali aggiornati, ma alcuni campi (CUP, Distretto, Capofila) sono vuoti.")
                else:
                    # Se Rif PA non valido, mostra errore e non conferma i metadati
                    st.error(rif_message)
                    st.session_state.doc_metadati_richiedente['rif_pa'] = rif_pa_input_val # Mantieni l'input errato per visualizzazione
                    st.session_state.metadati_confermati_richiedente = False 

                log_activity(username_param, "METADATA_SUBMITTED_RICHIEDENTE", f"Input RifPA: {rif_pa_input_val}, Valid: {is_valid_rif}, Dati: {st.session_state.doc_metadati_richiedente}")
                st.rerun() # Ricarica per aggiornare la UI
                
    # Blocca se i metadati non sono confermati
    if not st.session_state.metadati_confermati_richiedente:
        st.info("Inserisci e conferma i Dati Generali del Documento (Rif. PA nel formato corretto) per procedere.")
        st.stop()
    else:
        # Mostra i metadati confermati
        doc_meta_show = st.session_state.doc_metadati_richiedente
        st.markdown(f"**Doc:** Rif. PA: `{doc_meta_show['rif_pa']}`, CUP: `{doc_meta_show['cup']}`, Distr: `{doc_meta_show['distretto']}`, Capofila: `{doc_meta_show['comune_capofila']}`")
    
    st.markdown("---")
    
    # --- Sezione 2: Incolla Dati Spesa ---
    st.subheader("2. Incolla i Dati delle Spese da Excel")
    pasted_data = st.text_area(
        "Incolla qui le 15 colonne di dati (solo i valori, **NON** le intestazioni):",
        height=200,
        key="pasted_excel_data_richiedente",
        help="Formati data comuni (es. GG/MM/AAAA, G/M/YY, DD NomeMese YYYY) sono accettati."
    )

    results_container = st.container() # Container per output validazione e download

    if pasted_data:
        has_blocking_errors_rich = False # Flag per errori bloccanti
        try:
            log_activity(username_param, "PASTE_15_PROCESSING_RICHIEDENTE", f"{len(pasted_data)} chars")
            
            # Leggi i dati incollati come CSV separato da TAB
            data_io = StringIO(pasted_data)
            df_pasted = pd.read_csv(data_io, sep='\t', header=None, dtype=str, na_filter=False)

            # Controllo numero colonne
            if df_pasted.shape[1] != 15:
                results_container.error(f"Errore: Incollate {df_pasted.shape[1]} colonne, attese 15. Controlla la selezione da Excel.")
                st.stop() # Blocca esecuzione se numero colonne errato

            # Assegna nomi colonne attesi
            col_names = ['numero_mandato','data_mandato','comune_titolare_mandato','importo_mandato','comune_centro_estivo','centro_estivo','genitore_cognome_nome','bambino_cognome_nome','codice_fiscale_bambino','valore_contributo_fse','altri_contributi','quota_retta_destinatario','totale_retta','numero_settimane_frequenza','controlli_formali_dichiarati']
            df_pasted.columns = col_names
            df_check = df_pasted.copy() # Lavora su una copia

            # --- Pre-processing e Validazioni Batch ---
            # Pulisci CF e crea colonna '_pulito'
            if 'codice_fiscale_bambino' in df_check.columns:
                df_check['codice_fiscale_bambino_pulito'] = df_check['codice_fiscale_bambino'].astype(str).str.upper().str.strip()
            else:
                 df_check['codice_fiscale_bambino_pulito'] = '' # Crea colonna vuota se manca l'originale

            # Controllo CF Duplicati nel Batch
            batch_errors = []
            cf_counts = df_check[df_check['codice_fiscale_bambino_pulito'] != '']['codice_fiscale_bambino_pulito'].value_counts()
            duplicated_cfs = cf_counts[cf_counts > 1]
            if not duplicated_cfs.empty:
                has_blocking_errors_rich = True # CF duplicato è bloccante
                for cf_dupl, count in duplicated_cfs.items():
                    batch_errors.append(f"❌ Il Codice Fiscale '{cf_dupl}' è presente {count} volte nei dati incollati.")
            
            # Mostra errori di batch (CF duplicati) immediatamente
            if batch_errors:
                results_container.error("Errori a livello di batch rilevati:")
                for err in batch_errors:
                    results_container.error(err)
                # Non serve st.stop() qui, il flag has_blocking_errors_rich impedirà il download

            # Parsing di altri dati (Date, Valute, Settimane)
            df_check['data_mandato_originale'] = df_check['data_mandato']
            df_check['data_mandato'] = pd.to_datetime(df_check['data_mandato_originale'], errors='coerce', dayfirst=True).dt.date

            currency_cols = ['importo_mandato','valore_contributo_fse','altri_contributi','quota_retta_destinatario','totale_retta','controlli_formali_dichiarati']
            for col in currency_cols:
                df_check[col] = df_check[col].apply(parse_excel_currency)

            df_check['numero_settimane_frequenza'] = df_check['numero_settimane_frequenza'].apply(
                lambda x: int(float(x)) if pd.notna(x) and str(x).replace('.', '', 1).isdigit() else 0
            )

            # --- Validazioni per Riga ---
            validation_results = []
            # Aggiungi eventuali errori di batch (CF duplicati) alla tabella dei risultati
            if batch_errors:
                 for err_batch in batch_errors:
                      validation_results.append({
                        'Riga': "Batch", 'Bambino': "N/A", 'Esito CF': "N/A",
                        'Esito Data Mandato': "N/A", 'Esito D=A+B+C': "N/A",
                        'Esito Regole Contr.FSE': "N/A", 'Esito Contr.Formali 5%': "N/A",
                        'Errori Bloccanti': err_batch, 
                        'Verifica Max 300€ FSE per Bambino (batch)': "N/A" # Aggiungi colonna placeholder
                      })

            # Itera sulle righe per validazioni specifiche
            for index, row in df_check.iterrows():
                # Validazione CF (usa colonna pulita)
                cf_to_validate = row.get('codice_fiscale_bambino_pulito', '')
                cf_ok, cf_msg = validate_codice_fiscale(cf_to_validate)
                
                # Validazione Data
                data_parsata_obj = row.get('data_mandato')
                data_originale_str = str(row.get('data_mandato_originale', '')).strip()
                if pd.notna(data_parsata_obj):
                    data_ok = True
                    data_formattata = data_parsata_obj.strftime('%d/%m/%Y')
                    msg_data = f"✅ Data '{data_originale_str}' → {data_formattata}" if data_originale_str != data_formattata else f"✅ OK ({data_formattata})"
                else:
                    data_ok = False
                    msg_data = f"❌ Data '{data_originale_str}' non riconosciuta."
                
                # Altre Validazioni per Riga
                sum_ok, sum_msg = check_sum_d(row)
                contrib_ok, contrib_msg = check_contribution_rules(row)
                cf5_ok, cf5_msg = check_controlli_formali(row, 'controlli_formali_dichiarati')
                
                # Aggrega errori per la riga corrente
                current_errors = []
                if not cf_ok: current_errors.append(cf_msg)
                if not data_ok: current_errors.append(msg_data)
                if not sum_ok: current_errors.append(sum_msg)
                if not contrib_ok: current_errors.append(contrib_msg)
                if not cf5_ok: current_errors.append(cf5_msg)

                # Aggiorna flag generale se ci sono errori bloccanti nella riga
                if current_errors: # Se ci sono errori di qualsiasi tipo in questa riga
                    if any("❌" in e for e in current_errors): # Controlla se almeno uno è bloccante
                        has_blocking_errors_rich = True
                
                # Aggiungi risultato della riga alla lista
                validation_results.append({
                    'Riga': index + 1, 
                    'Bambino': row.get('bambino_cognome_nome','N/A'),
                    'Esito CF': cf_msg, 
                    'Esito Data Mandato': msg_data,
                    'Esito D=A+B+C': sum_msg, 
                    'Esito Regole Contr.FSE': contrib_msg,
                    'Esito Contr.Formali 5%': cf5_msg,
                    'Errori Bloccanti': " ; ".join(current_errors) if current_errors else "Nessuno",
                    'Verifica Max 300€ FSE per Bambino (batch)': '⏳' # Placeholder
                })

            # Crea DataFrame con i risultati della validazione
            df_results = pd.DataFrame(validation_results)
            
            # --- Check Aggregato Max 300€ FSE ---
            col_cap_agg = "Verifica Max 300€ FSE per Bambino (batch)"
            df_results[col_cap_agg] = '✅ OK' # Imposta default (verrà sovrascritto in caso di errore)
            
            if 'codice_fiscale_bambino_pulito' in df_check.columns and 'valore_contributo_fse' in df_check.columns:
                # Escludi righe con CF vuoto dal calcolo
                valid_cf_rows = df_check[df_check['codice_fiscale_bambino_pulito'] != '']
                if not valid_cf_rows.empty:
                    contrib_per_child = valid_cf_rows.groupby('codice_fiscale_bambino_pulito')['valore_contributo_fse'].sum()
                    children_over_cap = contrib_per_child[contrib_per_child > 300.01] # Tolleranza
                    if not children_over_cap.empty:
                        has_blocking_errors_rich = True # Superamento cap è bloccante
                        for cf_val, total_contrib in children_over_cap.items():
                            error_msg_cap = f"❌ Superato cap 300€ ({total_contrib:.2f}€ totali)"
                            # Trova gli indici originali corrispondenti al CF pulito
                            indices = df_check.index[df_check['codice_fiscale_bambino_pulito'] == cf_val].tolist()
                            for idx in indices:
                                # Trova la riga corrispondente nel DataFrame dei risultati
                                row_mask = df_results['Riga'] == idx + 1
                                if not row_mask.empty:
                                    # Aggiorna la colonna del check aggregato
                                    df_results.loc[row_mask, col_cap_agg] = error_msg_cap
                                    # Aggiungi l'errore anche alla colonna 'Errori Bloccanti'
                                    current_errs = df_results.loc[row_mask, 'Errori Bloccanti'].iloc[0]
                                    if error_msg_cap not in current_errs: # Evita di aggiungere lo stesso errore più volte
                                        if current_errs == "Nessuno":
                                            df_results.loc[row_mask, 'Errori Bloccanti'] = error_msg_cap
                                        else:
                                            df_results.loc[row_mask, 'Errori Bloccanti'] += "; " + error_msg_cap

            # --- Visualizza Tabella Risultati ---
            results_container.subheader("3. Risultati della Verifica Dati")
            cols_order = ['Riga','Bambino','Esito CF','Esito Data Mandato','Esito D=A+B+C','Esito Regole Contr.FSE','Esito Contr.Formali 5%', col_cap_agg, 'Errori Bloccanti']
            results_container.dataframe(df_results[cols_order], use_container_width=True, hide_index=True)
            
            # --- Sezione Download (solo se non ci sono errori bloccanti) ---
            if not has_blocking_errors_rich:
                results_container.success("Tutte le verifiche sono OK (✅). Puoi procedere a scaricare i dati.")
                log_activity(username_param, "VALIDATION_SUCCESS_RICHIEDENTE", f"{len(df_check)} rows.")
                
                # Prepara DataFrame finale per output
                df_validated = df_check.copy()
                # Aggiungi metadati
                for key, value in st.session_state.doc_metadati_richiedente.items():
                    df_validated[key] = value
                # Calcola controlli formali finali
                df_validated['controlli_formali'] = round(df_validated['valore_contributo_fse'] * 0.05, 2)
                
                # Gestisci colonne CF: rimuovi originale, rinomina pulito
                if 'codice_fiscale_bambino' in df_validated.columns:
                     df_validated.drop(columns=['codice_fiscale_bambino'], inplace=True, errors='ignore')
                if 'codice_fiscale_bambino_pulito' in df_validated.columns:
                    df_validated.rename(columns={'codice_fiscale_bambino_pulito': 'codice_fiscale_bambino'}, inplace=True)

                # Definisci e seleziona colonne finali per l'output
                final_output_cols = [
                    'rif_pa', 'cup', 'distretto', 'comune_capofila', 'numero_mandato', 'data_mandato', 
                    'comune_titolare_mandato', 'importo_mandato', 'comune_centro_estivo', 'centro_estivo', 
                    'genitore_cognome_nome', 'bambino_cognome_nome', 'codice_fiscale_bambino',
                    'valore_contributo_fse', 'altri_contributi', 'quota_retta_destinatario', 'totale_retta', 
                    'numero_settimane_frequenza', 'controlli_formali'
                ]
                existing_final_cols = [col for col in final_output_cols if col in df_validated.columns]
                df_output_final = df_validated[existing_final_cols].copy()

                # Expander per Anteprima e Download
                with results_container.expander("⬇️ 4. Anteprima Dati Normalizzati e Download", expanded=True):
                    # Anteprima
                    df_display_anteprima = df_output_final.copy()
                    if 'data_mandato' in df_display_anteprima.columns:
                        # Formatta data per visualizzazione
                        df_display_anteprima['data_mandato'] = pd.to_datetime(df_display_anteprima['data_mandato'], errors='coerce').dt.strftime('%d/%m/%Y').fillna('')
                    st.dataframe(df_display_anteprima, use_container_width=True, hide_index=True)

                    # Preparazione Nome File
                    rif_pa_s = sanitize_filename_component(df_output_final['rif_pa'].iloc[0] if not df_output_final.empty and 'rif_pa' in df_output_final.columns else st.session_state.doc_metadati_richiedente.get('rif_pa',''))
                    
                    # Esportazione CSV
                    df_export_csv = df_output_final.copy()
                    if 'data_mandato' in df_export_csv.columns:
                        # Formatta data esplicitamente per CSV
                        df_export_csv['data_mandato'] = pd.to_datetime(df_export_csv['data_mandato'], errors='coerce').dt.strftime('%d/%m/%Y').fillna('')
                    csv_output = df_export_csv.to_csv(index=False, sep=';', decimal=',', encoding='utf-8-sig').encode('utf-8-sig')
                    fn_csv = generate_timestamp_filename(type_prefix="datiSIFER", rif_pa_sanitized=rif_pa_s) + ".csv"
                    st.download_button(label="Scarica CSV per SIFER", data=csv_output, file_name=fn_csv, mime='text/csv', key="rich_dl_csv")
                    
                    # Esportazione Excel (usa df_output_final con oggetti date)
                    excel_output_bytes = convert_df_to_excel_bytes(df_output_final)
                    fn_excel = generate_timestamp_filename(type_prefix="datiSIFER", rif_pa_sanitized=rif_pa_s) + ".xlsx"
                    st.download_button(label="Scarica Excel", data=excel_output_bytes, file_name=fn_excel, mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key="rich_dl_excel")

                # Expander per Quadro di Controllo
                with results_container.expander("📊 5. Quadro di Controllo (Calcolato)", expanded=True):
                    # Calcoli aggregati
                    tot_A = df_output_final['valore_contributo_fse'].sum()
                    tot_5_perc = df_output_final['controlli_formali'].sum() # Usa colonna calcolata
                    tot_C = df_output_final['quota_retta_destinatario'].sum()
                    tot_contrib_compl = tot_A + tot_5_perc

                    # Creazione DataFrame Quadro
                    quadro_data_dict = {
                        "Voce": ["Totale costi diretti (A)", "Quota costi indiretti 5% (calcolata)", "Contributo complessivo", "Totale quote dest. (C)"],
                        "Valore (€)": [tot_A, tot_5_perc, tot_contrib_compl, tot_C]
                    }
                    df_qc = pd.DataFrame(quadro_data_dict)
                    
                    # Visualizzazione Quadro
                    df_qc_display = df_qc.copy()
                    df_qc_display["Valore (€)"] = df_qc_display["Valore (€)"].apply(lambda x: f"{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
                    st.dataframe(df_qc_display, hide_index=True, use_container_width=True)

                    # Download Quadro CSV
                    csv_qc = df_qc.to_csv(index=False, sep=';', decimal=',', encoding='utf-8-sig').encode('utf-8-sig')
                    fn_qc_csv = generate_timestamp_filename(type_prefix="QuadroControllo", rif_pa_sanitized=rif_pa_s, include_seconds=False) + ".csv"
                    st.download_button(label="Scarica Quadro CSV", data=csv_qc, file_name=fn_qc_csv, mime='text/csv', key="rich_qc_csv")

                    # Download Quadro Excel
                    excel_qc_bytes = convert_df_to_excel_bytes(df_qc)
                    fn_qc_excel = generate_timestamp_filename(type_prefix="QuadroControllo", rif_pa_sanitized=rif_pa_s, include_seconds=False) + ".xlsx"
                    st.download_button(label="Scarica Quadro Excel", data=excel_qc_bytes, file_name=fn_qc_excel, mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key="rich_qc_excel")
            
            else: # Se ci sono errori bloccanti
                 results_container.error("Sono stati rilevati errori bloccanti (contrassegnati con ❌). Correggere i dati e reincollare.")
                 log_activity(username_param, "VALIDATION_FAILED_RICHIEDENTE", "Errori bloccanti rilevati.")
        
        # --- Gestione Errori Generali ---
        except pd.errors.EmptyDataError: 
             results_container.warning("Nessun dato da elaborare. Assicurati di aver incollato i dati correttamente.")
        except ValueError as ve: 
             results_container.error(f"Errore nella conversione dei dati: {ve}. Controlla il formato delle date e dei numeri.")
             log_activity(username_param, "PARSING_ERROR_RICHIEDENTE", str(ve))
             # st.exception(ve) # Decommenta per vedere traceback completo se necessario
        except Exception as e: 
             results_container.error(f"Errore imprevisto durante l'elaborazione: {e}")
             log_activity(username_param, "PROCESSING_ERROR_RICHIEDENTE", str(e))
             st.exception(e) # Mostra traceback completo per debug

# --- Funzione Principale dell'App (Router) ---
def main_app_router():
    """Gestisce la navigazione e visualizza la pagina appropriata in base al ruolo."""
    user_role_main = st.session_state.get('user_role', 'user')
    username_main = st.session_state.get('username', 'N/D')
    name_main = st.session_state.get('name', 'Utente')
    authenticator_main = st.session_state.get('authenticator')

    # Controllo sessione authenticator
    if not authenticator_main:
        st.error("Sessione corrotta o scaduta. Effettua nuovamente il login.")
        st.session_state['authentication_status'] = None
        st.rerun()
        return

    # Sidebar Utente e Logout
    st.sidebar.title(f"Utente: {name_main}")
    st.sidebar.write(f"Ruolo: {user_role_main.capitalize()}")
    authenticator_main.logout('Logout', 'sidebar')

    # Routing basato sul ruolo
    if user_role_main == 'richiedente':
        render_richiedente_form(username_main)
    elif user_role_main in ['controllore', 'admin']:
        # Pagina di benvenuto per Controllore/Admin, le funzionalità sono nelle altre pagine
        st.info(f"Benvenuto {name_main}. Seleziona un'opzione dalla navigazione laterale per accedere alle funzionalità del ruolo '{user_role_main.capitalize()}'.")
    else:
        # Ruolo non riconosciuto
        st.error("Ruolo utente non riconosciuto. Contattare l'amministratore.")
        log_activity(username_main, "UNKNOWN_ROLE_ACCESS", f"Ruolo: {user_role_main}")

# --- Blocco Esecuzione Principale ---
if __name__ == "__main__":
    # Assicura esistenza cartella database e inizializza DB/Tabelle
    os.makedirs("database", exist_ok=True, mode=0o755)
    init_db()

    # Inizializza chiavi di session_state se non esistono
    # Chiavi specifiche per il Richiedente
    if 'doc_metadati_richiedente' not in st.session_state:
        st.session_state.doc_metadati_richiedente = {'rif_pa': '', 'cup': '', 'distretto': '', 'comune_capofila': ''}
    if 'metadati_confermati_richiedente' not in st.session_state:
        st.session_state.metadati_confermati_richiedente = False
    # Chiavi generali di autenticazione
    default_auth_keys = {'authentication_status': None, 'name': None, 'username': None, 'authenticator': None, 'user_role': None}
    for k, v_default in default_auth_keys.items():
        st.session_state.setdefault(k, v_default) # setdefault è più sicuro se la chiave potrebbe già esistere

    # Gestione flusso di autenticazione
    if not st.session_state.get('authentication_status'):
        auth_status_main = display_login_form()
        # Se il login non va a buon fine (False o None), ferma l'esecuzione
        if not auth_status_main: 
            st.stop()
    
    # Se l'utente è autenticato, esegui il router principale
    if st.session_state.get('authentication_status') is True: 
        main_app_router()
#cartella/app.py