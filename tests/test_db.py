#tests/test_db.py
import pytest
import sqlite3
import os
import pandas as pd
from datetime import date, datetime
from unittest.mock import ANY
import re # Aggiunto per test_delete_spese_by_ids

from utils import db as app_db
from utils.db import TABLE_NAME

def test_init_db(test_db_conn_engine):
    db_conn, mock_db_logger = test_db_conn_engine
    cursor = db_conn.cursor()
    cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{TABLE_NAME}'")
    assert cursor.fetchone() is not None, f"Tabella {TABLE_NAME} non creata nella fixture."
    
    mock_db_logger.info.reset_mock()
    app_db.init_db(existing_conn=db_conn)
    
    found_log = any(
        cr.args[0] == "DB_INIT - Schema DB verificato/creato." and \
        cr.kwargs.get('extra',{}).get('username') == "System_DB"
        for cr in mock_db_logger.info.call_args_list
    )
    assert found_log, f"Log DB_INIT (2a chiamata) non trovato. Logs: {[c.args[0] for c in mock_db_logger.info.call_args_list]}"

def test_add_spesa_success(test_db_conn_engine, sample_input_data_dict):
    db_conn, mock_db_logger = test_db_conn_engine
    data = {**sample_input_data_dict, 'id_trasmissione': "uuid-s01"}
    username = "test_adder"
    mock_db_logger.info.reset_mock()
    
    success, msg = app_db.add_spesa(data, username, existing_conn=db_conn)
    assert success, f"add_spesa fallito: {msg}"
    assert "aggiunta" in msg.lower()

    row = db_conn.execute(f"SELECT * FROM {TABLE_NAME} WHERE id_trasmissione=?", (data['id_trasmissione'],)).fetchone()
    assert row is not None, "Riga non trovata nel DB"
    assert row['bambino_cognome_nome'] == data['bambino_cognome_nome']
    
    assert any("DB_INSERT_SUCCESS" in cr.args[0] and cr.kwargs['extra']['username'] == username for cr in mock_db_logger.info.call_args_list)

def test_add_spesa_duplicate_error(test_db_conn_engine, sample_input_data_dict):
    db_conn, mock_db_logger = test_db_conn_engine
    data = {**sample_input_data_dict, 'id_trasmissione': "uuid-d01"}
    
    app_db.add_spesa(data, "first_user", existing_conn=db_conn)
    mock_db_logger.info.reset_mock()
    success, msg = app_db.add_spesa(data, "user2_dup", existing_conn=db_conn)
    
    assert not success 
    assert ("violazione unicità" in msg.lower() or "unique constraint failed" in msg.lower()), f"Messaggio inatteso: {msg}"
    assert any("DB_ERROR_INTEGRITY" in cr.args[0] and cr.kwargs['extra']['username'] == "user2_dup" for cr in mock_db_logger.info.call_args_list)

def test_add_spesa_no_id_trasmissione(test_db_conn_engine, sample_input_data_dict):
    db_conn, mock_db_logger = test_db_conn_engine
    data = sample_input_data_dict.copy(); data.pop('id_trasmissione', None)
    username = "user_no_idt"
    mock_db_logger.info.reset_mock()

    success, msg = app_db.add_spesa(data, username, existing_conn=db_conn)
    assert not success and "id trasmissione mancante" in msg.lower()
    assert any(
        cr.args[0] == "DB_INSERT_ERROR - add_spesa: id_trasmissione mancante." and \
        cr.kwargs.get('extra',{}).get('username') == username
        for cr in mock_db_logger.info.call_args_list
    ), f"Log atteso non trovato. Logs: {[c.args[0] for c in mock_db_logger.info.call_args_list]}"

def test_add_spesa_bad_date_type(test_db_conn_engine, sample_input_data_dict):
    db_conn, mock_db_logger = test_db_conn_engine
    data = {**sample_input_data_dict, 'id_trasmissione': "uuid-bd01", 'data_mandato': "bad_date"}
    username = "user_baddate"
    mock_db_logger.info.reset_mock()
    success, _ = app_db.add_spesa(data, username, existing_conn=db_conn)
    assert success, "add_spesa dovrebbe avere successo con data_mandato=NULL"
    row = db_conn.execute(f"SELECT data_mandato FROM {TABLE_NAME} WHERE id_trasmissione=?",(data['id_trasmissione'],)).fetchone()
    assert row['data_mandato'] is None
    assert any("DB_INSERT_WARNING" in cr.args[0] and cr.kwargs['extra']['username'] == username for cr in mock_db_logger.info.call_args_list)

def test_add_multiple_spese_success(test_db_conn_engine, sample_input_data_dict):
    db_conn, mock_db_logger = test_db_conn_engine
    id_b = "batch-multi-ok"
    df = pd.DataFrame([
        {**sample_input_data_dict, 'id_trasmissione':id_b, 'codice_fiscale_bambino': "CFM01_OK"},
        {**sample_input_data_dict, 'id_trasmissione':id_b, 'codice_fiscale_bambino': "CFM02_OK"}])
    username = "user_multi_ok"
    mock_db_logger.info.reset_mock()
    success, msg = app_db.add_multiple_spese(df, username, existing_conn=db_conn)
    assert success, f"add_multiple_spese fallito: {msg}"
    assert "2 righe con successo" in msg.lower()
    assert db_conn.execute(f"SELECT COUNT(*) FROM {TABLE_NAME} WHERE id_trasmissione=?",(id_b,)).fetchone()[0] == 2
    assert any("DATA_BULK_INSERTED" in cr.args[0] for cr in mock_db_logger.info.call_args_list)

def test_add_multiple_spese_partial_fail(test_db_conn_engine, sample_input_data_dict):
    db_conn, mock_db_logger = test_db_conn_engine
    id_b = "batch-multi-partial"
    
    d1_data = sample_input_data_dict.copy()
    d1_data['codice_fiscale_bambino'] = "CFMP01_PARTIAL_UNIQUE" 
    d1 = {**d1_data, 'id_trasmissione':id_b}
    d_dup = d1.copy() 
    d2_data = sample_input_data_dict.copy()
    d2_data['codice_fiscale_bambino'] = "CFMP02_PARTIAL_UNIQUE"
    d2 = {**d2_data, 'id_trasmissione':id_b}
    
    df = pd.DataFrame([d1, d_dup, d2])
    username = "user_multi_partial"
    mock_db_logger.info.reset_mock()
    
    success, msg = app_db.add_multiple_spese(df, username, existing_conn=db_conn)
        
    assert not success, "add_multiple_spese dovrebbe restituire success=False per fallimento parziale"
    
    msg_lower = msg.lower()
    assert "parziale:" in msg_lower, f"Stringa 'parziale:' non trovata in '{msg_lower}'"
    assert "2 ok" in msg_lower, f"Stringa '2 ok' non trovata in '{msg_lower}'"
    assert "1 ko" in msg_lower, f"Stringa '1 ko' non trovata in '{msg_lower}'"
    assert "violazione unicità" in msg_lower or "unique constraint" in msg_lower, "L'errore di unicità non è menzionato"

    count = db_conn.execute(f"SELECT COUNT(*) FROM {TABLE_NAME} WHERE id_trasmissione=?", (id_b,)).fetchone()[0]
    assert count == 2, f"Conteggio errato nel DB, atteso 2, trovato {count}"
    
    assert any("DATA_BULK_INSERT_PARTIAL" in cr.args[0] for cr in mock_db_logger.info.call_args_list), \
        "Log DATA_BULK_INSERT_PARTIAL non trovato."

def test_add_multiple_spese_empty_df(test_db_conn_engine, sample_input_data_dict):
    db_conn, _ = test_db_conn_engine
    df = pd.DataFrame(columns=sample_input_data_dict.keys())
    success, msg = app_db.add_multiple_spese(df, "user_empty", existing_conn=db_conn)
    assert success and "nessuna riga da importare" in msg.lower()

def test_check_rif_pa_exists(test_db_conn_engine, sample_input_data_dict):
    db_conn, _ = test_db_conn_engine
    assert not app_db.check_rif_pa_exists("NONEXIST-RER", existing_conn=db_conn)
    data = {**sample_input_data_dict, 'id_trasmissione': "uuid-chkrif"}
    app_db.add_spesa(data, "user_chk", existing_conn=db_conn)
    assert app_db.check_rif_pa_exists(data['rif_pa'], existing_conn=db_conn)

def test_delete_spese_by_ids(test_db_conn_engine, sample_input_data_dict):
    db_conn, mock_db_logger = test_db_conn_engine
    ids_to_delete = []
    for i in range(2):
        d = {**sample_input_data_dict, 'id_trasmissione':f"del{i}", 'codice_fiscale_bambino':f"CFDEL_UNIQUE_{i}"}
        success_add, msg_add = app_db.add_spesa(d, "user_dsetup", existing_conn=db_conn)
        assert success_add, f"Fallimento add_spesa per iterazione {i}: {msg_add}"
        
        match = re.search(r"ID DB: (\d+)", msg_add)
        assert match, f"Impossibile estrarre ID DB dal messaggio: '{msg_add}'"
        last_id = int(match.group(1))
        ids_to_delete.append(last_id)
            
    assert len(ids_to_delete) == 2 and None not in ids_to_delete, f"IDs recuperati: {ids_to_delete}"

    username="user_del"; mock_db_logger.info.reset_mock()
    count, msg = app_db.delete_spese_by_ids(ids_to_delete, username, existing_conn=db_conn)
    
    assert count == 2, f"Conteggio eliminati errato: {count}, atteso 2. IDs: {ids_to_delete}"
    assert "2 record eliminati" in msg.lower()
    assert db_conn.execute(f"SELECT COUNT(*) FROM {TABLE_NAME} WHERE id IN (?,?)", tuple(ids_to_delete)).fetchone()[0] == 0
    assert any("DATA_BULK_DELETED" in cr.args[0] for cr in mock_db_logger.info.call_args_list)

def test_get_all_spese(test_db_conn_engine, sample_input_data_dict):
    db_conn, _ = test_db_conn_engine
    assert app_db.get_all_spese(existing_conn=db_conn).empty

    base_data = {key: sample_input_data_dict[key] for key in [
        'rif_pa', 'bambino_cognome_nome', 'codice_fiscale_bambino', 'data_mandato',
        'numero_mandato', 'comune_titolare_mandato', 'importo_mandato', 'comune_centro_estivo',
        'centro_estivo', 'genitore_cognome_nome', 'valore_contributo_fse', 'altri_contributi',
        'quota_retta_destinatario', 'totale_retta', 'numero_settimane_frequenza', 'controlli_formali'
    ]}
    base_data.update({'cup': 'CUP_MAN', 'distretto': 'DIST_MAN', 'comune_capofila': 'CAPOF_MAN'})

    d1 = {**base_data, 'id_trasmissione':"getall1",'codice_fiscale_bambino':"CFGA1_MAN",'timestamp_caricamento':datetime(2024,1,1,10,0,0)}
    d2 = {**base_data, 'id_trasmissione':"getall2",'codice_fiscale_bambino':"CFGA2_MAN",'timestamp_caricamento':datetime(2024,1,1,12,0,0)}
    
    with db_conn:
        for d_in in [d1, d2]:
            cols_to_insert = list(d_in.keys()) + ['utente_caricamento']
            vals_to_insert = list(d_in.values()) + ['manual_user_getall']
            placeholders = ','.join(['?'] * len(cols_to_insert))
            # Assicurati che tutte le colonne NOT NULL siano coperte.
            # L'ordine delle colonne in d_in DEVE corrispondere all'ordine in cols_to_insert
            # Per semplicità, qui assumiamo che l'ordine sia corretto se d_in è un dict e lo convertiamo.
            # Più sicuro: definire esplicitamente le colonne nell'INSERT
            current_cols = [
                'id_trasmissione', 'rif_pa', 'cup', 'distretto', 'comune_capofila', 'numero_mandato', 'data_mandato',
                'comune_titolare_mandato', 'importo_mandato', 'comune_centro_estivo', 'centro_estivo',
                'genitore_cognome_nome', 'bambino_cognome_nome', 'codice_fiscale_bambino', 'valore_contributo_fse',
                'altri_contributi', 'quota_retta_destinatario', 'totale_retta', 'numero_settimane_frequenza',
                'controlli_formali', 'timestamp_caricamento', 'utente_caricamento'
            ]
            current_vals = tuple(d_in.get(col, 'default_val_if_missing') for col in current_cols[:-1]) + ('manual_user_getall',) # Escluso utente_caricamento se già in d_in

            # Ricostruisci vals_to_insert in base all'ordine di current_cols
            final_vals = []
            for col_name in current_cols:
                if col_name == 'utente_caricamento':
                    final_vals.append('manual_user_getall')
                else:
                    final_vals.append(d_in.get(col_name))
            
            db_conn.execute(f"INSERT INTO {TABLE_NAME} ({', '.join(current_cols)}) VALUES ({', '.join(['?']*len(current_cols))})", tuple(final_vals))
            
    df = app_db.get_all_spese(existing_conn=db_conn)
    assert len(df) == 2, f"Numero di righe errato: {len(df)}"
    assert pd.api.types.is_datetime64_any_dtype(df['timestamp_caricamento'])
    assert df['id_trasmissione'].iloc[0] == "getall2" # d2 è più recente
    assert df['id_trasmissione'].iloc[1] == "getall1"


def test_get_log_content(mocker):
    from utils.db import log_file_path
    mocker.patch('builtins.open', side_effect=FileNotFoundError)
    assert "non ancora creato" in app_db.get_log_content().lower()

    mock_open = mocker.patch('builtins.open', mocker.mock_open(read_data="L1\nL2\nL3\n"))
    content = app_db.get_log_content()
    assert content == "L3\nL2\nL1\n", f"Contenuto log errato: Actual='{content}', Expected='L3\\nL2\\nL1\\n'"
    mock_open.assert_called_once_with(log_file_path, 'r', encoding='utf-8')

def test_log_activity_writes_to_mocked_logger(test_db_conn_engine):
    _ , mock_db_logger = test_db_conn_engine
    mock_db_logger.info.reset_mock() # Resetta il mock del METODO info

    app_db.log_activity("user_log_test", "ACTION_TEST", "Detail test")
    
    assert mock_db_logger.info.called, "logger.info non è stato chiamato da log_activity"
    
    call_args_tuple = mock_db_logger.info.call_args
    assert call_args_tuple is not None, "Nessun argomento catturato per logger.info"
    msg_arg = call_args_tuple.args[0]
    extra_arg = call_args_tuple.kwargs.get('extra', {})
    
    assert extra_arg.get('username') == "user_log_test"
    assert "ACTION_TEST - Detail test" == msg_arg
#tests/test_db.py