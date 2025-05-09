#utils/db.py
import sqlite3
import pandas as pd
from datetime import datetime, date
import logging
import os
from logging.handlers import RotatingFileHandler
import uuid
from typing import Union, Optional, Tuple, List, Dict, Any # Aggiunto Any

# Configurazione del logger
log_dir = "database"
os.makedirs(log_dir, exist_ok=True, mode=0o755) # Permessi standard
log_file_path = os.path.join(log_dir, "activity.log")

logger = logging.getLogger(__name__) # Logger specifico per questo modulo
if not logger.handlers: # Aggiungi handler solo se non esistono già
    logger.setLevel(logging.INFO)
    file_handler = RotatingFileHandler(log_file_path, maxBytes=1024*1024*5, backupCount=2, encoding='utf-8')
    # Formatter che si aspetta 'username'. log_activity o 'extra' devono fornirlo.
    formatter = logging.Formatter('%(asctime)s - %(username)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    logger.propagate = False # Evita duplicazione log se il root logger ha handler

DATABASE_PATH = os.path.join(log_dir, 'spese.db')
TABLE_NAME = 'spese_sostenute'

# --- Adattatori e Convertitori SQLite per Date/Datetime ---
def adapt_date_iso(val: date) -> Union[str, None]:
    return val.isoformat() if isinstance(val, date) else None

def convert_date_from_db(val_bytes: bytes) -> Union[date, None]:
    if not val_bytes: return None
    try: return date.fromisoformat(val_bytes.decode())
    except (ValueError, TypeError):
        try: return datetime.strptime(val_bytes.decode(), '%Y-%m-%d %H:%M:%S').date()
        except (ValueError, TypeError): return None

def adapt_datetime_iso(val: datetime) -> Union[str, None]:
    return val.isoformat(sep=' ', timespec='seconds') if isinstance(val, datetime) else None

def convert_datetime_from_db(val_bytes: bytes) -> Union[datetime, None]:
    if not val_bytes: return None
    decoded_val = val_bytes.decode()
    try: return datetime.fromisoformat(decoded_val.replace(' ', 'T'))
    except (ValueError, TypeError):
        try: return datetime.strptime(decoded_val, '%Y-%m-%d %H:%M:%S')
        except (ValueError, TypeError):
            try: return datetime.strptime(decoded_val, '%Y-%m-%d %H:%M:%S.%f')
            except (ValueError, TypeError): return None

sqlite3.register_adapter(date, adapt_date_iso)
sqlite3.register_converter("DATE", convert_date_from_db)
sqlite3.register_adapter(datetime, adapt_datetime_iso)
sqlite3.register_converter("DATETIME", convert_datetime_from_db)

def get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DATABASE_PATH, detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def log_activity(username: Optional[str], action: str, details: str = ""):
    effective_username = username if username else "System_Event" # Default se username non fornito
    logger.info(f"{action} - {details}", extra={'username': effective_username})

def init_db(existing_conn: Optional[sqlite3.Connection] = None):
    is_external_conn = existing_conn is not None
    conn = existing_conn if is_external_conn else get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
            id INTEGER PRIMARY KEY AUTOINCREMENT, id_trasmissione TEXT NOT NULL, rif_pa TEXT NOT NULL, cup TEXT, 
            distretto TEXT, comune_capofila TEXT, numero_mandato TEXT, data_mandato DATE, 
            comune_titolare_mandato TEXT, importo_mandato REAL DEFAULT 0.0, comune_centro_estivo TEXT, 
            centro_estivo TEXT, genitore_cognome_nome TEXT, bambino_cognome_nome TEXT NOT NULL, 
            codice_fiscale_bambino TEXT NOT NULL, valore_contributo_fse REAL DEFAULT 0.0, 
            altri_contributi REAL DEFAULT 0.0, quota_retta_destinatario REAL DEFAULT 0.0, 
            totale_retta REAL DEFAULT 0.0, numero_settimane_frequenza INTEGER DEFAULT 0, 
            controlli_formali REAL DEFAULT 0.0, timestamp_caricamento DATETIME NOT NULL, 
            utente_caricamento TEXT NOT NULL,
            UNIQUE(id_trasmissione, codice_fiscale_bambino, data_mandato, centro_estivo, valore_contributo_fse) 
        )""")
        if not is_external_conn: conn.commit()
        log_activity("System_DB", "DB_INIT", "Schema DB verificato/creato.")
    except sqlite3.Error as e:
        log_activity("System_DB_Error", "DB_INIT_FAILED", f"Errore durante init_db: {e}")
        # Rilancia l'eccezione se non è gestita diversamente, o gestiscila qui
        raise
    finally:
        if not is_external_conn and conn: conn.close()

def add_spesa(data_dict: Dict[str, Any], username: str, existing_conn: Optional[sqlite3.Connection] = None) -> Tuple[bool, str]:
    is_external_conn = existing_conn is not None
    conn = existing_conn if is_external_conn else get_db_connection()
    
    id_trasm = str(data_dict.get('id_trasmissione', ''))
    if not id_trasm:
        log_activity(username, "DB_INSERT_ERROR", "add_spesa: id_trasmissione mancante.")
        if not is_external_conn and conn: conn.close()
        return False, "Errore interno: ID Trasmissione mancante."

    data_mandato = data_dict.get('data_mandato')
    if data_mandato is not None and not isinstance(data_mandato, date):
        log_activity(username, "DB_INSERT_WARNING", f"add_spesa: data_mandato non tipo date ({type(data_mandato)}). Impostato a NULL.")
        data_mandato = None
    
    cols = ['id_trasmissione','rif_pa','cup','distretto','comune_capofila','numero_mandato','data_mandato',
            'comune_titolare_mandato','importo_mandato','comune_centro_estivo','centro_estivo',
            'genitore_cognome_nome','bambino_cognome_nome','codice_fiscale_bambino','valore_contributo_fse',
            'altri_contributi','quota_retta_destinatario','totale_retta','numero_settimane_frequenza',
            'controlli_formali','timestamp_caricamento','utente_caricamento']
    
    def get_val(key: str, default: Any = None) -> Any:
        return data_dict.get(key, default)

    vals = (id_trasm, get_val('rif_pa'), get_val('cup'), get_val('distretto'), get_val('comune_capofila'),
            get_val('numero_mandato'), data_mandato, get_val('comune_titolare_mandato'),
            get_val('importo_mandato', 0.0), get_val('comune_centro_estivo'), get_val('centro_estivo'),
            get_val('genitore_cognome_nome'), get_val('bambino_cognome_nome'),
            get_val('codice_fiscale_bambino'), get_val('valore_contributo_fse', 0.0),
            get_val('altri_contributi', 0.0), get_val('quota_retta_destinatario', 0.0),
            get_val('totale_retta', 0.0), get_val('numero_settimane_frequenza', 0),
            get_val('controlli_formali', 0.0), datetime.now(), username)
    
    cursor = conn.cursor()
    try:
        cursor.execute(f"INSERT INTO {TABLE_NAME} ({', '.join(cols)}) VALUES ({', '.join(['?']*len(cols))})", vals)
        if not is_external_conn: conn.commit()
        log_activity(username, "DB_INSERT_SUCCESS", f"Riga per {get_val('bambino_cognome_nome', 'N/D')} (ID DB: {cursor.lastrowid}), TransID: {id_trasm[:8]}.")
        return True, f"Riga per {get_val('bambino_cognome_nome', 'N/D')} aggiunta (ID DB: {cursor.lastrowid})."
    except sqlite3.IntegrityError as e:
        if not is_external_conn: conn.rollback()
        log_activity(username, "DB_ERROR_INTEGRITY", f"add_spesa: TransID {id_trasm[:8]}..., Errore: {e}, CF={get_val('codice_fiscale_bambino')}")
        return False, f"Errore: Violazione unicità (possibile duplicato per CF={get_val('codice_fiscale_bambino')}). Dettaglio: {e}"
    except sqlite3.Error as e:
        if not is_external_conn: conn.rollback()
        log_activity(username, "DB_ERROR_INSERT", f"add_spesa: TransID {id_trasm[:8]}..., Errore SQL: {e}")
        return False, f"Errore Database durante inserimento: {e}"
    finally:
        if not is_external_conn and conn: conn.close()

def add_multiple_spese(df_spese: pd.DataFrame, username: str, existing_conn: Optional[sqlite3.Connection] = None) -> Tuple[bool, str]:
    if df_spese.empty: return True, "Nessuna riga da importare."
    is_external_conn = existing_conn is not None
    conn_to_use = existing_conn if is_external_conn else get_db_connection()
    
    id_batch = df_spese['id_trasmissione'].iloc[0] if 'id_trasmissione' in df_spese.columns and not df_spese.empty else 'N/A_BATCH_' + str(uuid.uuid4())[:8]
    success_count, fail_count, errors_detail_list = 0, 0, []

    try:
        for idx, row_series in df_spese.iterrows():
            data_d = row_series.to_dict()
            ok, msg_single = add_spesa(data_d, username, existing_conn=conn_to_use)
            if ok: success_count += 1
            else: fail_count += 1; errors_detail_list.append(f"Riga (idx DataFrame {idx}): {msg_single}")
        
        if fail_count > 0:
            if not is_external_conn: conn_to_use.rollback()
            err_details = '; '.join(errors_detail_list)
            log_activity(username, "DATA_BULK_INSERT_PARTIAL", f"ID Batch {id_batch[:8]}, OK:{success_count}, KO:{fail_count}, Errori:{err_details[:500]}")
            return False, f"ID Batch: {id_batch[:8]} Parziale: {success_count} OK, {fail_count} KO.\nErrori:\n- " + "\n- ".join(errors_detail_list)
        
        if not is_external_conn: conn_to_use.commit()
        log_activity(username, "DATA_BULK_INSERTED", f"ID Batch {id_batch[:8]}, Aggiunte {success_count} righe.")
        return True, f"Aggiunte {success_count} righe con successo (ID Batch: {id_batch[:8]}...)."
    except Exception as e_multi:
        if not is_external_conn: conn_to_use.rollback()
        log_activity(username, "DATA_BULK_ERROR_FATAL", f"ID Batch {id_batch[:8]}, Errore fatale: {e_multi}")
        return False, f"Errore fatale durante import massivo (ID Batch {id_batch[:8]}): {e_multi}"
    finally:
        if not is_external_conn and conn_to_use: conn_to_use.close()

def check_rif_pa_exists(rif_pa: str, existing_conn: Optional[sqlite3.Connection] = None) -> bool:
    is_external_conn = existing_conn is not None
    conn = existing_conn if is_external_conn else get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(f"SELECT 1 FROM {TABLE_NAME} WHERE rif_pa = ? LIMIT 1", (rif_pa,))
        return cursor.fetchone() is not None
    finally:
        if not is_external_conn and conn: conn.close()

def delete_spese_by_ids(ids: List[int], username: str, existing_conn: Optional[sqlite3.Connection] = None) -> Tuple[int, str]:
    if not ids: return 0, "Nessun ID fornito per l'eliminazione."
    is_external_conn = existing_conn is not None
    conn = existing_conn if is_external_conn else get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(f"DELETE FROM {TABLE_NAME} WHERE id IN ({','.join(['?']*len(ids))})", tuple(ids))
        if not is_external_conn: conn.commit()
        deleted_rows = cursor.rowcount
        log_activity(username, "DATA_BULK_DELETED", f"{deleted_rows} record eliminati. IDs (primi 5): {ids[:5]}")
        return deleted_rows, f"{deleted_rows} record eliminati con successo."
    except sqlite3.Error as e:
        if not is_external_conn: conn.rollback()
        log_activity(username, "DB_ERROR_BULK_DELETE", f"Errore eliminazione: {e}")
        return 0, f"Errore database durante l'eliminazione: {e}"
    finally:
        if not is_external_conn and conn: conn.close()

def get_all_spese(existing_conn: Optional[sqlite3.Connection] = None) -> pd.DataFrame:
    is_external_conn = existing_conn is not None
    conn = existing_conn if is_external_conn else get_db_connection()
    try:
        return pd.read_sql_query(f"SELECT * FROM {TABLE_NAME} ORDER BY timestamp_caricamento DESC, id DESC", conn)
    except Exception as e:
        log_activity("System_DB_Access", "DB_ERROR_GET_ALL", f"Errore recupero tutte le spese: {e}")
        return pd.DataFrame()
    finally:
        if not is_external_conn and conn: conn.close()

def get_log_content() -> str:
    try:
        with open(log_file_path, 'r', encoding='utf-8') as f: lines = f.readlines()
        return "".join(lines[::-1]) 
    except FileNotFoundError: 
        logger.warning(f"File di log '{log_file_path}' non trovato.", extra={'username': 'System_LogReader'})
        return "File di log non ancora creato o non trovato."
    except Exception as e: 
        logger.error(f"Errore lettura file di log '{log_file_path}': {e}", extra={'username': 'System_LogReader'})
        return f"Errore durante la lettura del file di log: {e}"
#utils/db.py