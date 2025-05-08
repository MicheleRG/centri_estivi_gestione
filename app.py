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
    validate_rif_pa_format # Usa la validazione di formato
)
import os
from io import StringIO
import numpy as np
import uuid

# Configurazione pagina
st.set_page_config(page_title="Comunicazione Spese Centri Estivi", layout="wide", initial_sidebar_state="expanded")

# --- Funzioni UI ---
def display_login_form():
    st.subheader("Accesso Utente")
    try:
        with open('config.yaml') as file:
            config_data = yaml.load(file, Loader=SafeLoader)
    except FileNotFoundError:
        st.error("Errore: File 'config.yaml' non trovato. L'applicazione non può avviarsi.")
        log_activity("System", "CONFIG_ERROR", "config.yaml not found")
        st.session_state['authentication_status'] = None
        st.stop()
        return None
    except yaml.YAMLError as e:
        st.error(f"Errore critico nel parsing del file 'config.yaml': {e}. Controllare la sintassi del file.")
        log_activity("System", "CONFIG_YAML_ERROR", str(e))
        st.session_state['authentication_status'] = None
        st.stop()
        return None
    except Exception as e:
        st.error(f"Errore critico nel caricamento di config.yaml (generico): {e}")
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
        st.session_state['authenticator'] = authenticator
    except KeyError as e:
        st.error(f"Errore nella configurazione: chiave '{e}' mancante nel file 'config.yaml'.")
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

    name, authentication_status, username = None, None, None
    try:
        name, authentication_status, username = authenticator.login()
    except KeyError as e:
        st.error(f"Errore (KeyError) durante il tentativo di login: '{e}'. Prova a cancellare i cookie.")
        log_activity("System", "LOGIN_KEY_ERROR", str(e))
        authentication_status = None
        st.session_state['authentication_status'] = None
    except Exception as e_login:
        st.error(f"Si è verificato un errore generico durante il processo di login: {e_login}")
        log_activity("System", "LOGIN_WIDGET_ERROR", str(e_login))
        authentication_status = None
        st.session_state['authentication_status'] = None

    st.session_state['authentication_status'] = authentication_status

    if authentication_status is True:
        st.session_state.update({'name': name, 'username': username})
        try:
            st.session_state['user_role'] = config_data['credentials']['usernames'][username].get('role', 'user')
            log_activity(username, "LOGIN_SUCCESS", f"Role: {st.session_state['user_role']}")
        except KeyError:
            st.session_state['user_role'] = 'user'
            log_activity(username, "LOGIN_CONFIG_WARNING", f"Ruolo utente per '{username}' non trovato, impostato a 'user'.")
            st.warning(f"Configurazione ruolo per '{username}' non trovata.")
    elif authentication_status is False:
        st.error('Username o password non corretti.')
        if username:
            log_activity(username, "LOGIN_FAILED_CREDENTIALS")

    return authentication_status


# Funzione per il Richiedente
def render_richiedente_form(username_param):
    st.title("📝 Comunicazione Spesa Centri Estivi (Verifica e Download)")
    log_activity(username_param, "PAGE_VIEW", "Richiedente - Verifica e Download")

    st.markdown("""
    Benvenuto! Questa sezione ti permette di:
    1.  Inserire i dati generali del tuo documento (il Rif. PA deve essere nel formato ANNO-OPERAZIONE/RER).
    2.  Copiare e incollare le righe di spesa da un foglio Excel.
    3.  Verificare la correttezza formale e sostanziale dei dati inseriti.
    4.  Scaricare i dati "normalizzati" e il quadro di controllo in formato CSV o Excel.
    **Nota:** I dati verificati qui **NON** vengono salvati automaticamente in alcun database da questa interfaccia.
    Dovrai caricare il file CSV scaricato nel sistema SIFER.
    """)

    st.subheader("1. Dati Generali del Documento")
    if 'doc_metadati_richiedente' not in st.session_state:
        st.session_state.doc_metadati_richiedente = {'rif_pa': '', 'cup': '', 'distretto': '', 'comune_capofila': ''}
    if 'metadati_confermati_richiedente' not in st.session_state:
        st.session_state.metadati_confermati_richiedente = False

    with st.expander("Inserisci/Modifica Dati Documento", expanded=not st.session_state.metadati_confermati_richiedente):
        with st.form("metadati_documento_form_richiedente"):
            doc_meta = st.session_state.doc_metadati_richiedente
            c1, c2 = st.columns(2)
            rif_pa_input_val = c1.text_input("Rif. PA n° (formato: AAAA-NUMERO/RER)", value=doc_meta.get('rif_pa', ''), key="rich_rifpa_input")
            cup_val = c2.text_input("CUP", value=doc_meta.get('cup', ''), key="rich_cup")
            distretto_val = c1.text_input("Distretto", value=doc_meta.get('distretto', ''), key="rich_distr")
            comune_capofila_val = c2.text_input("Comune/Unione Capofila", value=doc_meta.get('comune_capofila', ''), key="rich_capofila")
            
            metadati_submitted = st.form_submit_button("✅ Conferma Dati Generali")

            if metadati_submitted:
                is_valid_rif, rif_message = validate_rif_pa_format(rif_pa_input_val)
                
                if is_valid_rif:
                    st.success(rif_message)
                    st.session_state.doc_metadati_richiedente = {
                        'rif_pa': rif_pa_input_val.strip(),
                        'cup': cup_val, 
                        'distretto': distretto_val, 
                        'comune_capofila': comune_capofila_val
                    }
                    st.session_state.metadati_confermati_richiedente = True
                    if not all([cup_val, distretto_val, comune_capofila_val]):
                        st.warning("Dati generali aggiornati, ma alcuni campi (CUP, Distretto, Capofila) sono vuoti.")
                else:
                    st.error(rif_message)
                    st.session_state.doc_metadati_richiedente['rif_pa'] = rif_pa_input_val 
                    st.session_state.metadati_confermati_richiedente = False 

                log_activity(username_param, "METADATA_SUBMITTED_RICHIEDENTE", f"Input RifPA: {rif_pa_input_val}, Valid: {is_valid_rif}, Dati: {st.session_state.doc_metadati_richiedente}")
                st.rerun()
                
    if not st.session_state.metadati_confermati_richiedente:
        st.info("Inserisci e conferma i Dati Generali del Documento per procedere. Il Rif. PA deve essere nel formato AAAA-NUMERO/RER."); st.stop()
    else:
        doc_meta_show = st.session_state.doc_metadati_richiedente
        st.markdown(f"**Doc:** Rif. PA: `{doc_meta_show['rif_pa']}`, CUP: `{doc_meta_show['cup']}`, Distr: `{doc_meta_show['distretto']}`, Capofila: `{doc_meta_show['comune_capofila']}`")
    
    st.markdown("---")
    st.subheader("2. Incolla i Dati delle Spese da Excel")
    pasted_data = st.text_area(
        "Incolla qui le 15 colonne di dati (solo i valori, **NON** le intestazioni di colonna):",
        height=200,
        key="pasted_excel_data_richiedente",
        help="Formati data comuni sono accettati. L'elaborazione inizierà automaticamente."
    )

    results_container = st.container()

    if pasted_data:
        has_blocking_errors_rich = False 
        try:
            log_activity(username_param, "PASTE_15_PROCESSING_RICHIEDENTE", f"{len(pasted_data)} chars")
            data_io = StringIO(pasted_data)
            df_pasted = pd.read_csv(data_io, sep='\t', header=None, dtype=str, na_filter=False)

            if df_pasted.shape[1] != 15:
                results_container.error(f"Errore: Incollate {df_pasted.shape[1]} colonne, attese 15. Controlla la selezione da Excel.")
                st.stop()

            col_names = ['numero_mandato','data_mandato','comune_titolare_mandato','importo_mandato','comune_centro_estivo','centro_estivo','genitore_cognome_nome','bambino_cognome_nome','codice_fiscale_bambino','valore_contributo_fse','altri_contributi','quota_retta_destinatario','totale_retta','numero_settimane_frequenza','controlli_formali_dichiarati']
            df_pasted.columns = col_names
            df_check = df_pasted.copy()

            # Prepara colonna CF pulita
            if 'codice_fiscale_bambino' in df_check.columns:
                df_check['codice_fiscale_bambino_pulito'] = df_check['codice_fiscale_bambino'].astype(str).str.upper().str.strip()
            else:
                 df_check['codice_fiscale_bambino_pulito'] = ''

            # Controlli Preliminari sul Batch (CF Duplicati)
            batch_errors = []
            cf_counts = df_check[df_check['codice_fiscale_bambino_pulito'] != '']['codice_fiscale_bambino_pulito'].value_counts()
            duplicated_cfs = cf_counts[cf_counts > 1]
            if not duplicated_cfs.empty:
                has_blocking_errors_rich = True
                for cf_dupl, count in duplicated_cfs.items():
                    batch_errors.append(f"❌ Il Codice Fiscale '{cf_dupl}' è presente {count} volte.")
            
            if batch_errors: # Mostra subito errori CF duplicati
                results_container.error("Errori a livello di batch rilevati:")
                for err in batch_errors:
                    results_container.error(err)

            # Pulisci e valida altri dati
            df_check['data_mandato_originale'] = df_check['data_mandato']
            df_check['data_mandato_parsed_temp'] = pd.to_datetime(
                df_check['data_mandato_originale'], errors='coerce', dayfirst=True
            )
            df_check['data_mandato'] = df_check['data_mandato_parsed_temp'].dt.date

            currency_cols = ['importo_mandato','valore_contributo_fse','altri_contributi','quota_retta_destinatario','totale_retta','controlli_formali_dichiarati']
            for col in currency_cols:
                df_check[col] = df_check[col].apply(parse_excel_currency)

            df_check['numero_settimane_frequenza'] = df_check['numero_settimane_frequenza'].apply(
                lambda x: int(float(x)) if pd.notna(x) and str(x).strip().replace('.', '', 1).isdigit() else 0
            )

            # Inizializza risultati validazione
            validation_results = []
            # Aggiungi errori batch (se presenti) alla tabella
            if batch_errors:
                 for err_batch in batch_errors:
                      validation_results.append({
                        'Riga': "Batch", 'Bambino': "N/A", 'Esito CF': "N/A",
                        'Esito Data Mandato': "N/A", 'Esito D=A+B+C': "N/A",
                        'Esito Regole Contr.FSE': "N/A", 'Esito Contr.Formali 5%': "N/A",
                        'Errori Bloccanti': err_batch, 'Verifica Max 300€ FSE per Bambino (batch)': "N/A"
                      })

            # Loop validazione per riga
            for index, row in df_check.iterrows():
                cf_to_validate = row.get('codice_fiscale_bambino_pulito', '')
                cf_ok, cf_msg = validate_codice_fiscale(cf_to_validate)
                
                data_originale_str = str(row.get('data_mandato_originale', '')).strip()
                data_parsata_obj = row.get('data_mandato')
                if pd.notna(data_parsata_obj):
                    data_ok = True
                    data_formattata_ggmmaaaa = data_parsata_obj.strftime('%d/%m/%Y')
                    msg_data_mandato = f"✅ Data '{data_originale_str}' interpretata come {data_formattata_ggmmaaaa}" if data_originale_str != data_formattata_ggmmaaaa else f"✅ OK ({data_formattata_ggmmaaaa})"
                else:
                    data_ok = False
                    msg_data_mandato = f"❌ Data '{data_originale_str}' non riconosciuta."
                
                sum_ok, sum_msg = check_sum_d(row)
                contrib_ok, contrib_msg = check_contribution_rules(row)
                cf5_ok, cf5_msg = check_controlli_formali(row, 'controlli_formali_dichiarati')
                
                current_errors = []
                if not cf_ok: current_errors.append(cf_msg)
                if not data_ok: current_errors.append(msg_data_mandato)
                if not sum_ok: current_errors.append(sum_msg)
                if not contrib_ok: current_errors.append(contrib_msg)
                if not cf5_ok: current_errors.append(cf5_msg)

                if any("❌" in e for e in current_errors):
                    has_blocking_errors_rich = True
                
                validation_results.append({
                    'Riga': index + 1, 
                    'Bambino': row.get('bambino_cognome_nome','N/A'),
                    'Esito CF': cf_msg, 'Esito Data Mandato': msg_data_mandato,
                    'Esito D=A+B+C': sum_msg, 'Esito Regole Contr.FSE': contrib_msg,
                    'Esito Contr.Formali 5%': cf5_msg,
                    'Errori Bloccanti': " ; ".join(current_errors) if current_errors else "Nessuno",
                    'Verifica Max 300€ FSE per Bambino (batch)': '⏳' # Placeholder
                })

            df_results = pd.DataFrame(validation_results)
            
            # Check aggregato Max 300€ FSE
            col_name_cap_check_agg = "Verifica Max 300€ FSE per Bambino (batch)";
            df_results[col_name_cap_check_agg] = '✅ OK' # Imposta default (anche per righe Batch)
            
            if 'codice_fiscale_bambino_pulito' in df_check.columns and 'valore_contributo_fse' in df_check.columns:
                valid_cf_rows = df_check[df_check['codice_fiscale_bambino_pulito'] != '']
                if not valid_cf_rows.empty:
                    contrib_per_child = valid_cf_rows.groupby('codice_fiscale_bambino_pulito')['valore_contributo_fse'].sum()
                    children_over_cap = contrib_per_child[contrib_per_child > 300.01]
                    if not children_over_cap.empty:
                        has_blocking_errors_rich = True
                        for cf_val, total_contrib in children_over_cap.items():
                            error_msg_cap = f"❌ Superato cap 300€ ({total_contrib:.2f}€ totali)"
                            indices = df_check.index[df_check['codice_fiscale_bambino_pulito'] == cf_val].tolist()
                            for idx in indices:
                                row_mask = df_results['Riga'] == idx + 1
                                if not row_mask.empty:
                                    df_results.loc[row_mask, col_name_cap_check_agg] = error_msg_cap
                                    current_row_errors = df_results.loc[row_mask, 'Errori Bloccanti'].iloc[0]
                                    if error_msg_cap not in current_row_errors:
                                         df_results.loc[row_mask, 'Errori Bloccanti'] += ("; " + error_msg_cap) if current_row_errors != "Nessuno" else error_msg_cap

            # Visualizza Tabella Risultati
            results_container.subheader("3. Risultati della Verifica Dati")
            cols_order_results = ['Riga','Bambino','Esito CF','Esito Data Mandato','Esito D=A+B+C','Esito Regole Contr.FSE','Esito Contr.Formali 5%', col_name_cap_check_agg, 'Errori Bloccanti']
            results_container.dataframe(df_results[cols_order_results], use_container_width=True, hide_index=True)
            
            # Sezione Download / Preparazione Output
            if not has_blocking_errors_rich:
                results_container.success("Tutte le verifiche sono OK (✅). Puoi procedere a scaricare i dati.")
                log_activity(username_param, "VALIDATION_SUCCESS_RICHIEDENTE", f"{len(df_check)} rows.")
                
                df_validated_final_rich = df_check.copy()
                for key, value in st.session_state.doc_metadati_richiedente.items():
                    df_validated_final_rich[key] = value
                df_validated_final_rich['controlli_formali'] = round(df_validated_final_rich['valore_contributo_fse'] * 0.05, 2)
                
                # FIX COLONNE DUPLICATE
                if 'codice_fiscale_bambino' in df_validated_final_rich.columns:
                     df_validated_final_rich.drop(columns=['codice_fiscale_bambino'], inplace=True, errors='ignore')
                if 'codice_fiscale_bambino_pulito' in df_validated_final_rich.columns:
                    df_validated_final_rich.rename(columns={'codice_fiscale_bambino_pulito': 'codice_fiscale_bambino'}, inplace=True)

                # Colonne finali per output
                final_output_cols = [
                    'rif_pa', 'cup', 'distretto', 'comune_capofila', 'numero_mandato', 'data_mandato', 
                    'comune_titolare_mandato', 'importo_mandato', 'comune_centro_estivo', 'centro_estivo', 
                    'genitore_cognome_nome', 'bambino_cognome_nome', 'codice_fiscale_bambino',
                    'valore_contributo_fse', 'altri_contributi', 'quota_retta_destinatario', 'totale_retta', 
                    'numero_settimane_frequenza', 'controlli_formali'
                ]
                existing_final_cols = [col for col in final_output_cols if col in df_validated_final_rich.columns]
                df_output_final = df_validated_final_rich[existing_final_cols].copy()

                # Sezione Download (invariata rispetto all'ultima versione)
                with results_container.expander("⬇️ 4. Anteprima Dati Normalizzati per SIFER e Download", expanded=True):
                    df_display_anteprima = df_output_final.copy()
                    if 'data_mandato' in df_display_anteprima.columns:
                        df_display_anteprima['data_mandato'] = pd.to_datetime(df_display_anteprima['data_mandato'], errors='coerce').dt.strftime('%d/%m/%Y').fillna('')
                    st.dataframe(df_display_anteprima, use_container_width=True, hide_index=True)

                    rif_pa_s = sanitize_filename_component(df_output_final['rif_pa'].iloc[0] if not df_output_final.empty and 'rif_pa' in df_output_final.columns else st.session_state.doc_metadati_richiedente.get('rif_pa',''))
                    
                    df_export_csv = df_output_final.copy()
                    if 'data_mandato' in df_export_csv.columns:
                        df_export_csv['data_mandato'] = pd.to_datetime(df_export_csv['data_mandato'], errors='coerce')
                        df_export_csv['data_mandato'] = df_export_csv['data_mandato'].dt.strftime('%d/%m/%Y').fillna('')
                    csv_output = df_export_csv.to_csv(index=False, sep=';', decimal=',', encoding='utf-8-sig').encode('utf-8-sig')
                    fn_csv = generate_timestamp_filename(type_prefix="datiSIFER", rif_pa_sanitized=rif_pa_s) + ".csv"
                    st.download_button(label="Scarica CSV per SIFER", data=csv_output, file_name=fn_csv, mime='text/csv', key="rich_dl_csv")

                    excel_output_bytes = convert_df_to_excel_bytes(df_output_final)
                    fn_excel = generate_timestamp_filename(type_prefix="datiSIFER", rif_pa_sanitized=rif_pa_s) + ".xlsx"
                    st.download_button(label="Scarica Excel", data=excel_output_bytes, file_name=fn_excel, mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key="rich_dl_excel")

                # Quadro Controllo (invariato rispetto all'ultima versione)
                with results_container.expander("📊 5. Quadro di Controllo (Calcolato)", expanded=True):
                    tot_A = df_output_final['valore_contributo_fse'].sum()
                    tot_5_perc = df_output_final['controlli_formali'].sum()
                    tot_C = df_output_final['quota_retta_destinatario'].sum()
                    tot_contrib_compl = tot_A + tot_5_perc

                    quadro_data_dict = {
                        "Voce": ["Totale costi diretti (A)", "Quota costi indiretti 5% (calcolata)", "Contributo complessivo", "Totale quote dest. (C)"],
                        "Valore (€)": [tot_A, tot_5_perc, tot_contrib_compl, tot_C]
                    }
                    df_qc = pd.DataFrame(quadro_data_dict)
                    df_qc_display = df_qc.copy()
                    df_qc_display["Valore (€)"] = df_qc_display["Valore (€)"].apply(lambda x: f"{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
                    st.dataframe(df_qc_display, hide_index=True, use_container_width=True)

                    csv_qc = df_qc.to_csv(index=False, sep=';', decimal=',', encoding='utf-8-sig').encode('utf-8-sig')
                    fn_qc_csv = generate_timestamp_filename(type_prefix="QuadroControllo", rif_pa_sanitized=rif_pa_s, include_seconds=False) + ".csv"
                    st.download_button(label="Scarica Quadro CSV", data=csv_qc, file_name=fn_qc_csv, mime='text/csv', key="rich_qc_csv")

                    excel_qc_bytes = convert_df_to_excel_bytes(df_qc)
                    fn_qc_excel = generate_timestamp_filename(type_prefix="QuadroControllo", rif_pa_sanitized=rif_pa_s, include_seconds=False) + ".xlsx"
                    st.download_button(label="Scarica Quadro Excel", data=excel_qc_bytes, file_name=fn_qc_excel, mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key="rich_qc_excel")

            else: # Se ci sono errori bloccanti
                 results_container.error("Sono stati rilevati errori bloccanti (contrassegnati con ❌). Correggere i dati e reincollare.")
                 log_activity(username_param, "VALIDATION_FAILED_RICHIEDENTE", "Errori bloccanti rilevati.")
        
        except pd.errors.EmptyDataError: 
             results_container.warning("Nessun dato da elaborare.")
        except ValueError as ve: 
             results_container.error(f"Errore nella conversione dei dati: {ve}. Controlla formati.")
             log_activity(username_param, "PARSING_ERROR_RICHIEDENTE", str(ve))
        except Exception as e: 
             results_container.error(f"Errore imprevisto: {e}")
             log_activity(username_param, "PROCESSING_ERROR_RICHIEDENTE", str(e))
             st.exception(e) 

# Funzione Principale dell'App (Router)
def main_app_router():
    user_role_main = st.session_state.get('user_role', 'user')
    username_main = st.session_state.get('username', 'N/D')
    name_main = st.session_state.get('name', 'Utente')
    authenticator_main = st.session_state.get('authenticator')

    if not authenticator_main:
        st.error("Sessione corrotta o scaduta. Effettua nuovamente il login.")
        st.session_state['authentication_status'] = None; st.rerun(); return

    st.sidebar.title(f"Utente: {name_main}")
    st.sidebar.write(f"Ruolo: {user_role_main.capitalize()}")
    authenticator_main.logout('Logout', 'sidebar')

    if user_role_main == 'richiedente':
        render_richiedente_form(username_main)
    elif user_role_main in ['controllore', 'admin']:
        st.info(f"Benvenuto {name_main}. Seleziona un'opzione dalla navigazione laterale per accedere alle funzionalità del ruolo '{user_role_main.capitalize()}'.")
    else:
        st.error("Ruolo utente non riconosciuto. Contattare l'amministratore.")
        log_activity(username_main, "UNKNOWN_ROLE_ACCESS", f"Ruolo: {user_role_main}")

# Blocco Esecuzione Principale
if __name__ == "__main__":
    os.makedirs("database", exist_ok=True, mode=0o755)
    init_db()

    if 'doc_metadati_richiedente' not in st.session_state:
        st.session_state.doc_metadati_richiedente = {'rif_pa': '', 'cup': '', 'distretto': '', 'comune_capofila': ''}
    if 'metadati_confermati_richiedente' not in st.session_state:
        st.session_state.metadati_confermati_richiedente = False

    default_ss_keys = {'authentication_status': None, 'name': None, 'username': None, 'authenticator': None, 'user_role': None}
    for k, v_default in default_ss_keys.items():
        if k not in st.session_state: st.session_state[k] = v_default

    if not st.session_state.get('authentication_status'):
        auth_status_main = display_login_form()
        if not auth_status_main:
            st.stop()

    if st.session_state.get('authentication_status') is True:
        main_app_router()
#cartella/app.py