#/pages/04_Dashboard_Dati.py 
import streamlit as st
import pandas as pd
from utils.db import get_all_spese, log_activity, delete_spese_by_ids
from utils.common_utils import sanitize_filename_component, convert_df_to_excel_bytes, generate_timestamp_filename

st.set_page_config(page_title="Dashboard Dati", layout="wide")

# --- Autenticazione e Controllo Ruolo ---
if not st.session_state.get('authentication_status', False):
    st.warning("Devi effettuare il login per accedere a questa pagina.")
    if st.button("🏠 Vai alla pagina di Login", key="dash_login_btn_redir"):
        st.switch_page("app.py")
    st.stop()

USER_ROLE_DASH = st.session_state.get('user_role')
USERNAME_DASH = st.session_state.get('username')
NAME_DASH = st.session_state.get('name')
AUTHENTICATOR_DASH = st.session_state.get('authenticator')

if not AUTHENTICATOR_DASH:
    st.error("🚨 Errore di sessione. Riprova il login.")
    if st.button("🏠 Riprova Login", key="dash_login_btn_no_auth"):
        st.switch_page("app.py")
    st.stop()

if USER_ROLE_DASH not in ['admin', 'controllore']:
    st.error("🚫 Accesso negato. Pagina riservata ad Amministratori e Controllori.")
    log_activity(USERNAME_DASH, "PAGE_ACCESS_DENIED", f"Tentativo accesso a Dashboard Dati da ruolo: {USER_ROLE_DASH}")
    st.stop()

st.sidebar.title(f"👤 Utente: {NAME_DASH}")
st.sidebar.write(f"🔖 Ruolo: {USER_ROLE_DASH.capitalize()}")
AUTHENTICATOR_DASH.logout('🚪 Logout', 'sidebar', key='dashboard_logout_sidebar')
# --- Fine Autenticazione ---

page_title_dash = "👑 Dashboard Amministrazione Dati (Admin)" if USER_ROLE_DASH == 'admin' else "📊 Dashboard Visualizzazione Dati (Controllore)"
st.title(page_title_dash)
log_activity(USERNAME_DASH, "PAGE_VIEW", f"Dashboard Dati ({USER_ROLE_DASH})")

st.markdown(f"""
Questa dashboard permette di:
- Visualizzare tutti i dati di spesa presenti nel database.
- Filtrare i dati per una ricerca mirata.
- Scaricare i dati filtrati in formato CSV o Excel.
{( "- **Eliminare massivamente** i dati filtrati (azione irreversibile, solo Admin)." if USER_ROLE_DASH == 'admin' else "")}
""")

# --- Caricamento e Filtri Dati ---
@st.cache_data(ttl=300) # Cache per 5 minuti per non sovraccaricare il DB su refresh frequenti
def load_data_from_db():
    log_activity(USERNAME_DASH, "DB_QUERY_DASHBOARD", "Caricamento dati per dashboard.")
    return get_all_spese()

df_spese_full = load_data_from_db()

if df_spese_full.empty:
    st.info("ℹ️ Nessun dato di spesa presente nel database al momento.")
else:
    st.subheader("🔍 Filtri Dati")
    # Inizializza chiavi di session_state per i filtri se non esistono
    filter_keys_session = ['dash_sel_rifpa', 'dash_sel_comune_ce', 'dash_sel_centro_estivo']
    for k_filt in filter_keys_session:
        st.session_state.setdefault(k_filt, [])

    filter_cols_layout = st.columns([2, 2, 2, 1]) 

    # Opzioni per filtri (ordinate e uniche)
    # Usare .tolist() per evitare problemi con tipi specifici di Pandas/Numpy in widget Streamlit
    rif_pa_opts_list = sorted(df_spese_full['rif_pa'].dropna().unique().tolist())
    selected_rif_pa_val = filter_cols_layout[0].multiselect(
        "Rif. PA", options=rif_pa_opts_list, 
        default=st.session_state.dash_sel_rifpa, # Usa valore da session_state per persistenza
        key="dash_sel_rifpa_widget", # Chiave widget separata da quella di stato
        placeholder="Filtra per Rif. PA..."
    )
    st.session_state.dash_sel_rifpa = selected_rif_pa_val # Aggiorna stato

    comuni_ce_opts_list = sorted(df_spese_full['comune_centro_estivo'].dropna().unique().tolist())
    selected_comune_ce_val = filter_cols_layout[1].multiselect(
        "Comune Centro Estivo", options=comuni_ce_opts_list, 
        default=st.session_state.dash_sel_comune_ce,
        key="dash_sel_comune_ce_widget",
        placeholder="Filtra per Comune CE..."
    )
    st.session_state.dash_sel_comune_ce = selected_comune_ce_val

    # Filtro dinamico per centri estivi
    if selected_comune_ce_val:
        centri_estivi_filtered_opts = sorted(df_spese_full[df_spese_full['comune_centro_estivo'].isin(selected_comune_ce_val)]['centro_estivo'].dropna().unique().tolist())
    else:
        centri_estivi_filtered_opts = sorted(df_spese_full['centro_estivo'].dropna().unique().tolist())
    selected_centro_estivo_val = filter_cols_layout[2].multiselect(
        "Centro Estivo", options=centri_estivi_filtered_opts,
        default=st.session_state.dash_sel_centro_estivo,
        key="dash_sel_centro_estivo_widget",
        placeholder="Filtra per Centro Estivo..."
    )
    st.session_state.dash_sel_centro_estivo = selected_centro_estivo_val

    if filter_cols_layout[3].button("🔄 Reset Filtri", use_container_width=True, key="dash_reset_filters_btn"):
        log_activity(USERNAME_DASH, "FILTERS_RESET_DASHBOARD")
        st.session_state.dash_sel_rifpa = []
        st.session_state.dash_sel_comune_ce = []
        st.session_state.dash_sel_centro_estivo = []
        st.rerun()

    # Applicazione filtri
    df_filtered_dash = df_spese_full.copy()
    if st.session_state.dash_sel_rifpa: 
        df_filtered_dash = df_filtered_dash[df_filtered_dash['rif_pa'].isin(st.session_state.dash_sel_rifpa)]
    if st.session_state.dash_sel_comune_ce: 
        df_filtered_dash = df_filtered_dash[df_filtered_dash['comune_centro_estivo'].isin(st.session_state.dash_sel_comune_ce)]
    if st.session_state.dash_sel_centro_estivo: 
        df_filtered_dash = df_filtered_dash[df_filtered_dash['centro_estivo'].isin(st.session_state.dash_sel_centro_estivo)]

    # --- Visualizzazione Dati Tabellare ---
    expander_title = f"Visualizza/Nascondi Elenco Spese ({len(df_filtered_dash)} risultati filtrati)"
    with st.expander(expander_title, expanded=len(df_filtered_dash) < 500 and len(df_filtered_dash) > 0): # Espanso se pochi risultati
        if df_filtered_dash.empty:
            st.info("Nessun dato corrisponde ai filtri selezionati.")
        else:
            # Ordine e selezione colonne per la visualizzazione
            cols_display_order_dash = [
                'id', 'id_trasmissione', 'rif_pa', 'cup', 'distretto', 'comune_capofila',
                'numero_mandato', 'data_mandato', 'comune_titolare_mandato', 'importo_mandato',
                'comune_centro_estivo', 'centro_estivo', 'bambino_cognome_nome', 'codice_fiscale_bambino',
                'valore_contributo_fse', 'altri_contributi', 'quota_retta_destinatario', 'totale_retta',
                'controlli_formali', 'numero_settimane_frequenza', 'timestamp_caricamento', 'utente_caricamento'
            ]
            cols_to_show_dash = [col for col in cols_display_order_dash if col in df_filtered_dash.columns]
            df_display_dash = df_filtered_dash[cols_to_show_dash].copy()

            # Formattazioni per display
            if 'data_mandato' in df_display_dash.columns:
                df_display_dash['data_mandato'] = pd.to_datetime(df_display_dash['data_mandato'], errors='coerce').dt.strftime('%d/%m/%Y').fillna('N/A')
            if 'timestamp_caricamento' in df_display_dash.columns:
                df_display_dash['timestamp_caricamento'] = pd.to_datetime(df_display_dash['timestamp_caricamento'], errors='coerce').dt.strftime('%d/%m/%Y %H:%M:%S').fillna('N/A')
            if 'id_trasmissione' in df_display_dash.columns: # Troncamento per leggibilità
                 df_display_dash['id_trasmissione'] = df_display_dash['id_trasmissione'].astype(str).apply(lambda x: x[:8] + "..." if pd.notna(x) and len(x) > 8 else x)

            column_config_dash = {
                "id": st.column_config.NumberColumn("ID DB", format="%d", help="ID univoco nel database"),
                "importo_mandato": st.column_config.NumberColumn("Imp. Mandato", format="€ %.2f"),
                "valore_contributo_fse": st.column_config.NumberColumn("Contr. FSE", format="€ %.2f"),
                "altri_contributi": st.column_config.NumberColumn("Altri Contr.", format="€ %.2f"),
                "quota_retta_destinatario": st.column_config.NumberColumn("Quota Retta Dest.", format="€ %.2f"),
                "totale_retta": st.column_config.NumberColumn("Totale Retta", format="€ %.2f"),
                "controlli_formali": st.column_config.NumberColumn("Contr. Formali (5%)", format="€ %.2f"),
                "data_mandato": st.column_config.TextColumn("Data Mandato"),
                "timestamp_caricamento": st.column_config.TextColumn("Caricato il")
            }
            st.dataframe(
                df_display_dash, use_container_width=True, hide_index=True,
                column_config=column_config_dash,
                height=min(600, len(df_display_dash) * 35 + 38) # Altezza dinamica
            )
    
    # --- Download e Azioni Admin ---
    if not df_filtered_dash.empty:
        st.markdown("---")
        st.subheader("📥 Download Dati Filtrati")
        col_dl1_dash, col_dl2_dash = st.columns(2)

        rif_pa_fn_part_dash = "tutti_RifPA"
        if st.session_state.dash_sel_rifpa:
             rif_pa_fn_part_dash = sanitize_filename_component("_".join(st.session_state.dash_sel_rifpa)) if len(st.session_state.dash_sel_rifpa) < 4 else f"{len(st.session_state.dash_sel_rifpa)}_RifPA_selezionati"

        # Per l'export, usiamo il df_filtered_dash originale non formattato per display
        # ma con le colonne selezionate in cols_to_show_dash
        df_export_dash = df_filtered_dash[cols_to_show_dash].copy()
        # Formattazione date per CSV se necessario (ma pd.to_csv gestisce bene oggetti date/datetime)
        # Se 'data_mandato' è oggetto date, to_csv lo formatta in ISO. Se serve GG/MM/AAAA:
        if 'data_mandato' in df_export_dash.columns:
             df_export_dash['data_mandato'] = pd.to_datetime(df_export_dash['data_mandato'], errors='coerce').dt.strftime('%d/%m/%Y')
        if 'timestamp_caricamento' in df_export_dash.columns:
            df_export_dash['timestamp_caricamento'] = pd.to_datetime(df_export_dash['timestamp_caricamento'], errors='coerce').dt.strftime('%d/%m/%Y %H:%M:%S')


        csv_data_dash = df_export_dash.to_csv(index=False, sep=';', decimal=',', encoding='utf-8-sig').encode('utf-8-sig')
        fn_csv_dash = generate_timestamp_filename("export_dati_filtrati", rif_pa_fn_part_dash) + ".csv"
        col_dl1_dash.download_button(label="Scarica Filtrati CSV", data=csv_data_dash, file_name=fn_csv_dash, mime='text/csv', key="dash_dl_csv_btn")

        excel_data_dash = convert_df_to_excel_bytes(df_filtered_dash[cols_to_show_dash]) # Usa df originale per Excel per preservare tipi
        fn_excel_dash = generate_timestamp_filename("export_dati_filtrati", rif_pa_fn_part_dash) + ".xlsx"
        col_dl2_dash.download_button(label="Scarica Filtrati Excel", data=excel_data_dash, file_name=fn_excel_dash, mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key="dash_dl_excel_btn")

        if USER_ROLE_DASH == 'admin':
            st.markdown("---")
            st.subheader("🗑️ Eliminazione Massiva Dati Filtrati (Solo Admin)")
            st.warning(f"🔴 ATTENZIONE: Stai per eliminare **{len(df_filtered_dash)}** record dal database in base ai filtri correnti. Questa azione è **IRREVERSIBILE**.")

            # Usa un form per raggruppare input e bottone, utile per gestione stato
            with st.form("delete_confirmation_form"):
                confirm_text_delete = f"CONFERMO ELIMINAZIONE DI {len(df_filtered_dash)} RECORD"
                
                # Per resettare l'input di testo, si può cambiare la sua chiave o usare un form con clear_on_submit
                # Qui manteniamo l'approccio di cambiare la chiave del text_input se necessario,
                # ma il form aiuta a gestire il submit.
                st.session_state.setdefault('delete_input_key_suffix_dash', 0)
                key_text_input_del = f"admin_delete_confirm_text_input_{st.session_state.delete_input_key_suffix_dash}"

                user_confirmation_delete = st.text_input(
                    f"Per confermare, digita esattamente: '{confirm_text_delete}'", 
                    key=key_text_input_del,
                    placeholder="Digita la frase di conferma qui"
                )
                
                submitted_delete_form = st.form_submit_button(
                    f"Procedi con l'Eliminazione di {len(df_filtered_dash)} Record", 
                    type="primary", 
                    disabled=(user_confirmation_delete != confirm_text_delete)
                )

                if submitted_delete_form: # Questo blocco viene eseguito solo se il form è submittato E il bottone cliccato
                    if user_confirmation_delete == confirm_text_delete:
                        with st.spinner("Eliminazione in corso..."):
                            ids_to_delete_list = df_filtered_dash['id'].tolist()
                            deleted_count_res, msg_delete_res = delete_spese_by_ids(ids_to_delete_list, USERNAME_DASH)
                            
                            if deleted_count_res > 0:
                                st.success(msg_delete_res)
                                log_activity(USERNAME_DASH, "ADMIN_BULK_DELETE_SUCCESS", f"{deleted_count_res} record. Filtri: RifPA={st.session_state.dash_sel_rifpa}, ComuneCE={st.session_state.dash_sel_comune_ce}, Centro={st.session_state.dash_sel_centro_estivo}")
                            else:
                                st.error(f"Eliminazione fallita o nessun record eliminato. Dettaglio: {msg_delete_res}")
                                log_activity(USERNAME_DASH, "ADMIN_BULK_DELETE_FAILED", msg_delete_res)
                            
                            # Incrementa il suffisso della chiave per forzare il reset dell'input di testo al prossimo rerun
                            st.session_state.delete_input_key_suffix_dash += 1
                            # Cancella il valore della vecchia chiave per sicurezza (anche se il rerun dovrebbe resettare i widget con nuove chiavi)
                            if key_text_input_del in st.session_state:
                                del st.session_state[key_text_input_del]
                            st.rerun() # Ricarica per aggiornare la vista e resettare il form
                    else: # Questo caso non dovrebbe essere raggiunto se il bottone è disabilitato correttamente
                        st.error("Conferma non corretta. Eliminazione annullata.")
#/pages/04_Dashboard_Dati.py