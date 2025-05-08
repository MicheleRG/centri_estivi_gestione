#cartella/pages/04_Dashboard_Dati.py 
import streamlit as st
import pandas as pd
from utils.db import get_all_spese, log_activity, delete_spese_by_ids
from utils.common_utils import sanitize_filename_component, convert_df_to_excel_bytes, generate_timestamp_filename

st.set_page_config(page_title="Dashboard Dati", layout="wide")

# --- Autenticazione e Controllo Ruolo ---
if 'authentication_status' not in st.session_state or not st.session_state.get('authentication_status'):
    st.warning("Devi effettuare il login per accedere a questa pagina.")
    if st.button("🏠 Vai alla pagina di Login", key="dashboard_login_btn1"): st.switch_page("app.py")
    st.stop()

USER_ROLE_CURRENT = st.session_state.get('user_role', 'user')
USERNAME_CURRENT = st.session_state.get('username', 'N/D')
NAME_CURRENT = st.session_state.get('name', 'N/D')
AUTHENTICATOR_CURRENT = st.session_state.get('authenticator')

if not AUTHENTICATOR_CURRENT:
    st.error("Errore di sessione.")
    if st.button("🏠 Riprova Login", key="dashboard_login_btn2"): st.switch_page("app.py")
    st.stop()

if USER_ROLE_CURRENT not in ['admin', 'controllore']:
    st.error("Accesso negato. Pagina riservata ad Amministratori e Controllori.")
    log_activity(USERNAME_CURRENT, "DASHBOARD_ACCESS_DENIED", f"Tentativo da ruolo: {USER_ROLE_CURRENT}")
    st.stop()

st.sidebar.title(f"Utente: {NAME_CURRENT}")
st.sidebar.write(f"Ruolo: {USER_ROLE_CURRENT.capitalize()}")
AUTHENTICATOR_CURRENT.logout('Logout', 'sidebar', key='dashboard_logout')
# --- Fine Autenticazione ---

page_title = "👑 Dashboard Amministrazione Dati" if USER_ROLE_CURRENT == 'admin' else "📊 Dashboard Visualizzazione Dati"
st.title(page_title)
log_activity(USERNAME_CURRENT, "PAGE_VIEW", f"Dashboard Dati ({USER_ROLE_CURRENT})")

st.markdown(f"""
Questa dashboard permette agli **{USER_ROLE_CURRENT.capitalize()}** di:
- Visualizzare tutti i dati di spesa presenti nel database (l'elenco è inizialmente espanso).
- Filtrare i dati per una ricerca mirata.
- Scaricare i dati filtrati in formato CSV o Excel.
""")
if USER_ROLE_CURRENT == 'admin':
    st.markdown("- **Eliminare massivamente** i dati filtrati (azione irreversibile!).")


# --- Visualizzazione Dati Tabellare ---
with st.spinner("Caricamento dati dal database..."):
    df_spese_full = get_all_spese()

if df_spese_full.empty:
    st.info("Nessun dato di spesa presente nel database.")
else:
    st.subheader("Filtri Dati")
    filter_cols = st.columns([2, 2, 2, 1]) 

    rif_pa_opts = sorted(df_spese_full['rif_pa'].dropna().unique().tolist())
    selected_rif_pa = filter_cols[0].multiselect("Rif. PA", options=rif_pa_opts, placeholder="Filtra per Rif. PA...", key="dash_sel_rifpa")

    comuni_ce_opts = sorted(df_spese_full['comune_centro_estivo'].dropna().unique().tolist())
    selected_comune_ce = filter_cols[1].multiselect("Comune Centro Estivo", options=comuni_ce_opts, placeholder="Filtra per Comune...", key="dash_sel_comune")

    if selected_comune_ce:
        centri_opts_filtered = sorted(df_spese_full[df_spese_full['comune_centro_estivo'].isin(selected_comune_ce)]['centro_estivo'].dropna().unique().tolist())
    else:
        centri_opts_filtered = sorted(df_spese_full['centro_estivo'].dropna().unique().tolist())
    selected_centro_estivo = filter_cols[2].multiselect("Centro Estivo", options=centri_opts_filtered, placeholder="Filtra per Centro...", key="dash_sel_centro")

    if filter_cols[3].button("🔄 Reset Filtri", use_container_width=True, key="dash_reset_filters"):
        log_activity(USERNAME_CURRENT, "FILTERS_RESET_DASHBOARD")
        st.session_state.dash_sel_rifpa = []
        st.session_state.dash_sel_comune = []
        st.session_state.dash_sel_centro = []
        st.rerun()

    df_filtered = df_spese_full.copy()
    if selected_rif_pa: df_filtered = df_filtered[df_filtered['rif_pa'].isin(selected_rif_pa)]
    if selected_comune_ce: df_filtered = df_filtered[df_filtered['comune_centro_estivo'].isin(selected_comune_ce)]
    if selected_centro_estivo: df_filtered = df_filtered[df_filtered['centro_estivo'].isin(selected_centro_estivo)]

    # Elenco spese in expander
    with st.expander(f"Visualizza/Nascondi Elenco Spese ({len(df_filtered)} risultati filtrati)", expanded=True):
        if df_filtered.empty and (selected_rif_pa or selected_comune_ce or selected_centro_estivo): # Mostra solo se filtri attivi e nessun risultato
            st.info("Nessun dato corrisponde ai filtri selezionati.")
        elif df_filtered.empty: # Nessun filtro attivo e nessun dato
             st.info("La tabella è vuota (nessun dato o nessun filtro applicato che restituisce risultati).")
        else:
            cols_display_order = [
                'id', 'id_trasmissione', 'rif_pa', 'cup', 'distretto', 'comune_capofila',
                'numero_mandato', 'data_mandato', 'comune_titolare_mandato', 'importo_mandato',
                'comune_centro_estivo', 'centro_estivo', 'bambino_cognome_nome', 'codice_fiscale_bambino',
                'valore_contributo_fse', 'altri_contributi', 'quota_retta_destinatario', 'totale_retta',
                'controlli_formali', 'numero_settimane_frequenza', 'timestamp_caricamento', 'utente_caricamento'
            ]
            cols_to_show = [col for col in cols_display_order if col in df_filtered.columns]

            df_display = df_filtered[cols_to_show].copy()
            if 'data_mandato' in df_display.columns:
                df_display['data_mandato'] = pd.to_datetime(df_display['data_mandato'], errors='coerce').dt.strftime('%d/%m/%Y')
            if 'timestamp_caricamento' in df_display.columns:
                df_display['timestamp_caricamento'] = pd.to_datetime(df_display['timestamp_caricamento'], errors='coerce').dt.strftime('%d/%m/%Y %H:%M:%S')
            if 'id_trasmissione' in df_display.columns:
                 df_display['id_trasmissione'] = df_display['id_trasmissione'].astype(str).apply(lambda x: x[:8] + "..." if pd.notna(x) and len(x) > 8 else x)

            column_config = {
                "id": st.column_config.NumberColumn("ID DB", format="%d"),
                "importo_mandato": st.column_config.NumberColumn("Importo Mandato", format="€ %.2f"),
                "valore_contributo_fse": st.column_config.NumberColumn("Contr. FSE", format="€ %.2f"),
                "altri_contributi": st.column_config.NumberColumn("Altri Contr.", format="€ %.2f"),
                "quota_retta_destinatario": st.column_config.NumberColumn("Quota Retta", format="€ %.2f"),
                "totale_retta": st.column_config.NumberColumn("Totale Retta", format="€ %.2f"),
                "controlli_formali": st.column_config.NumberColumn("Contr. Formali", format="€ %.2f"),
                "data_mandato": st.column_config.TextColumn("Data Mandato"),
                "timestamp_caricamento": st.column_config.TextColumn("Timestamp Caricamento")
            }

            st.dataframe(
                df_display,
                use_container_width=True,
                hide_index=True,
                column_config=column_config,
                height=min(600, len(df_display) * 35 + 38)
            )

    if not df_filtered.empty:
        st.markdown("---")
        st.subheader("📥 Download Dati Filtrati")
        col_dl1, col_dl2 = st.columns(2)

        rif_pa_fn_part = "tutti"
        if selected_rif_pa:
             rif_pa_fn_part = sanitize_filename_component("_".join(selected_rif_pa)) if len(selected_rif_pa) < 4 else f"{len(selected_rif_pa)}_RifPA"

        csv_data = df_filtered[cols_to_show].to_csv(
            index=False, sep=';', decimal=',', encoding='utf-8-sig', date_format='%d/%m/%Y'
        ).encode('utf-8-sig')
        fn_csv = generate_timestamp_filename("export_dati", rif_pa_fn_part) + ".csv"
        col_dl1.download_button(label="Scarica Filtrati CSV", data=csv_data, file_name=fn_csv, mime='text/csv', key="dash_dl_csv")

        excel_data = convert_df_to_excel_bytes(df_filtered[cols_to_show])
        fn_excel = generate_timestamp_filename("export_dati", rif_pa_fn_part) + ".xlsx"
        col_dl2.download_button(label="Scarica Filtrati Excel", data=excel_data, file_name=fn_excel, mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key="dash_dl_excel")

    if USER_ROLE_CURRENT == 'admin':
        if not df_filtered.empty:
            st.markdown("---")
            st.subheader("🗑️ Eliminazione Massiva Dati Filtrati (Solo Admin)")
            st.warning(f"ATTENZIONE: Stai per eliminare **{len(df_filtered)}** record dal database in base ai filtri correnti. Questa azione è **IRREVERSIBILE**.")

            confirm_text = f"Confermo eliminazione di {len(df_filtered)} record"
            
            if 'delete_input_key_suffix' not in st.session_state:
                st.session_state.delete_input_key_suffix = 0

            user_confirmation = st.text_input(
                f"Per confermare, digita esattamente: '{confirm_text}'", 
                key=f"admin_delete_confirm_text_input_{st.session_state.delete_input_key_suffix}"
            )

            if st.button(f"Procedi con l'Eliminazione di {len(df_filtered)} Record", type="primary", disabled=(user_confirmation != confirm_text), key="admin_confirm_delete_final_btn"):
                if user_confirmation == confirm_text:
                    with st.spinner("Eliminazione in corso..."):
                        ids_to_delete = df_filtered['id'].tolist()
                        deleted_count, msg = delete_spese_by_ids(ids_to_delete, USERNAME_CURRENT)
                        if deleted_count > 0:
                            st.success(msg)
                            log_activity(USERNAME_CURRENT, "ADMIN_BULK_DELETE_SUCCESS", f"{deleted_count} record. Filtri: RifPA={selected_rif_pa}, ComuneCE={selected_comune_ce}, Centro={selected_centro_estivo}")
                        else:
                            st.error(f"Eliminazione fallita o nessun record eliminato. Dettaglio: {msg}")
                            log_activity(USERNAME_CURRENT, "ADMIN_BULK_DELETE_FAILED", msg)
                        
                        st.session_state.delete_input_key_suffix += 1
                        old_key = f"admin_delete_confirm_text_input_{st.session_state.delete_input_key_suffix -1}"
                        if old_key in st.session_state:
                            del st.session_state[old_key]
                        st.rerun()
#cartella/pages/04_Dashboard_Dati.py