#cartella/utils/db.py
import sqlite3
import pandas as pd
from datetime import datetime, date
import logging
import os
from logging.handlers import RotatingFileHandler
import uuid
from typing import Union # <<< IMPORTANTE: Aggiungi questo import

# Configurazione del logger
log_dir = "database"
os.makedirs(log_dir, exist_ok=True,  mode=0o755)
log_file_path = os.path.join(log_dir, "activity.log")

logger = logging.getLogger(__name__)
if not logger.handlers:
    logger.setLevel(logging.INFO)
    file_handler = RotatingFileHandler(log_file_path, maxBytes=1024*1024*5, backupCount=2, encoding='utf-8')
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(username)s - %(levelname)s - %(message)s'))
    logger.addHandler(file_handler)
    logger.propagate = False

DATABASE_PATH = os.path.join(log_dir, 'spese.db')
TABLE_NAME = 'spese_sostenute'

# Adattatori e convertitori SQLite per date/datetime
def adapt_date_iso(val: date) -> Union[str, None]: # MODIFICATO QUI
    return val.isoformat() if isinstance(val, date) else None

def convert_date_from_db(val_bytes: bytes) -> Union[date, None]: # MODIFICATO QUI
    if val_bytes:
        try:
            return date.fromisoformat(val_bytes.decode())
        except (ValueError, TypeError):
            try:
                return datetime.strptime(val_bytes.decode(), '%Y-%m-%d %H:%M:%S').date()
            except (ValueError, TypeError):
                 return None
    return None

def adapt_datetime_iso(val: datetime) -> Union[str, None]: # MODIFICATO QUI
    return val.isoformat(sep=' ', timespec='seconds') if isinstance(val, datetime) else None

def convert_datetime_from_db(val_bytes: bytes) -> Union[datetime, None]: # MODIFICATO QUI
    if val_bytes:
        try:
            return datetime.fromisoformat(val_bytes.decode().replace(' ', 'T'))
        except (ValueError, TypeError):
            try:
                return datetime.strptime(val_bytes.decode(), '%Y-%m-%d %H:%M:%S')
            except (ValueError, TypeError):
                try:
                    return datetime.strptime(val_bytes.decode(), '%Y-%m-%d %H:%M:%S.%f')
                except(ValueError, TypeError):
                    return None
    return None

sqlite3.register_adapter(date, adapt_date_iso)
sqlite3.register_converter("DATE", convert_date_from_db)
sqlite3.register_adapter(datetime, adapt_datetime_iso)
sqlite3.register_converter("DATETIME", convert_datetime_from_db)

def get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DATABASE_PATH, detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(f"""
    CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        id_trasmissione TEXT NOT NULL,      
        rif_pa TEXT NOT NULL,                          
        cup TEXT,                             
        distretto TEXT,                       
        comune_capofila TEXT,                 
        numero_mandato TEXT,
        data_mandato DATE, 
        comune_titolare_mandato TEXT,
        importo_mandato REAL DEFAULT 0.0,
        comune_centro_estivo TEXT,
        centro_estivo TEXT,
        genitore_cognome_nome TEXT,
        bambino_cognome_nome TEXT NOT NULL,
        codice_fiscale_bambino TEXT NOT NULL,
        valore_contributo_fse REAL DEFAULT 0.0,           
        altri_contributi REAL DEFAULT 0.0,                
        quota_retta_destinatario REAL DEFAULT 0.0,        
        totale_retta REAL DEFAULT 0.0,                    
        numero_settimane_frequenza INTEGER DEFAULT 0,
        controlli_formali REAL DEFAULT 0.0,          
        timestamp_caricamento DATETIME NOT NULL, 
        utente_caricamento TEXT NOT NULL,
        UNIQUE(id_trasmissione, codice_fiscale_bambino, data_mandato, centro_estivo, valore_contributo_fse) 
    )
    """)
    conn.commit()
    conn.close()
    logger.info("Database schema verificato/inizializzato.")

def log_activity(username: Union[str, None], action: str, details: str = ""): # MODIFICATO QUI
    effective_username = username if username else "System"
    log_record = logging.LogRecord(
        name=__name__, level=logging.INFO, pathname=__file__, lineno=0, 
        msg=f"{action} - {details}", args=(), exc_info=None, func=''
    )
    log_record.username = effective_username
    logger.handle(log_record)

def add_spesa(data_dict: dict, username: str) -> tuple[bool, str]:
    conn = get_db_connection()
    cursor = conn.cursor()
    
    id_trasmissione = data_dict.get('id_trasmissione')
    if not id_trasmissione:
        log_activity(username, "DB_INSERT_ERROR", "id_trasmissione mancante nel data_dict per add_spesa.")
        return False, "Errore interno: ID Trasmissione mancante."

    data_mandato_obj = data_dict.get('data_mandato')
    if data_mandato_obj is not None and not isinstance(data_mandato_obj, date):
         log_activity(username, "DB_INSERT_WARNING", f"data_mandato non era oggetto date per {data_dict.get('bambino_cognome_nome')}, tipo: {type(data_mandato_obj)}. Sarà NULL.")
         data_mandato_obj = None

    query_cols = [
        'id_trasmissione', 'rif_pa', 'cup', 'distretto', 'comune_capofila', 
        'numero_mandato', 'data_mandato', 'comune_titolare_mandato', 'importo_mandato',
        'comune_centro_estivo', 'centro_estivo', 'genitore_cognome_nome', 'bambino_cognome_nome',
        'codice_fiscale_bambino', 'valore_contributo_fse', 'altri_contributi',
        'quota_retta_destinatario', 'totale_retta', 'numero_settimane_frequenza',
        'controlli_formali', 
        'timestamp_caricamento', 'utente_caricamento'
    ]
    
    values_tuple = (
        id_trasmissione, data_dict.get('rif_pa'), data_dict.get('cup'), data_dict.get('distretto'), data_dict.get('comune_capofila'),
        data_dict.get('numero_mandato'), data_mandato_obj, data_dict.get('comune_titolare_mandato'), data_dict.get('importo_mandato', 0.0),
        data_dict.get('comune_centro_estivo'), data_dict.get('centro_estivo'), data_dict.get('genitore_cognome_nome'), data_dict.get('bambino_cognome_nome'),
        data_dict.get('codice_fiscale_bambino'), data_dict.get('valore_contributo_fse', 0.0), data_dict.get('altri_contributi', 0.0),
        data_dict.get('quota_retta_destinatario', 0.0), data_dict.get('totale_retta', 0.0), data_dict.get('numero_settimane_frequenza', 0),
        data_dict.get('controlli_formali', 0.0), 
        datetime.now(), username
    )

    try:
        placeholders = ", ".join(["?"] * len(query_cols))
        cursor.execute(f"INSERT INTO {TABLE_NAME} ({', '.join(query_cols)}) VALUES ({placeholders})", values_tuple)
        conn.commit()
        return True, f"Riga per {data_dict.get('bambino_cognome_nome', 'N/D')} aggiunta (ID DB: {cursor.lastrowid})."
    except sqlite3.IntegrityError as e:
        conn.rollback()
        log_activity(username, "DB_ERROR_INTEGRITY", f"TransID {id_trasmissione[:8]}..., Errore: {e}. CF={data_dict.get('codice_fiscale_bambino')}, Data={data_mandato_obj}, RifPA={data_dict.get('rif_pa')}")
        return False, f"Errore: Violazione vincolo di unicità per {data_dict.get('bambino_cognome_nome', 'N/D')} (possibile duplicato). Dettaglio: {e}"
    except sqlite3.Error as e:
        conn.rollback()
        log_activity(username, "DB_ERROR_INSERT", f"TransID {id_trasmissione[:8]}..., Errore SQL: {e}")
        return False, f"Errore Database durante l'inserimento: {e}"
    finally:
        if conn:
            conn.close()

def add_multiple_spese(df_spese: pd.DataFrame, username: str) -> tuple[bool, str]:
    if df_spese.empty:
        return True, "Nessuna riga da importare."

    id_trasmissione_batch = df_spese['id_trasmissione'].iloc[0] if 'id_trasmissione' in df_spese.columns and not df_spese.empty else 'N/A_BATCH'
    
    successful_inserts = 0
    failed_inserts = 0
    errors_detail = []

    for index, row_data in df_spese.iterrows():
        data_dict = row_data.to_dict()
        success, msg = add_spesa(data_dict, username)
        if success:
            successful_inserts += 1
        else:
            failed_inserts += 1
            errors_detail.append(f"Riga Dati {index + 1}: {msg}") 

    if failed_inserts > 0:
        details_str = '; '.join(errors_detail)
        log_activity(username, "DATA_BULK_INSERT_PARTIAL", f"TransID {id_trasmissione_batch[:8]}..., Aggiunte {successful_inserts}, Fallite: {failed_inserts}. Errori: {details_str[:500]}")
        error_summary = f"ID Trasmissione: {id_trasmissione_batch[:8]}...\nParzialmente completato: Aggiunte {successful_inserts} righe. {failed_inserts} righe non importate."
        if errors_detail:
            error_summary += "\nErrori dettaglio:\n- " + "\n- ".join(errors_detail)
        return False, error_summary
    
    log_activity(username, "DATA_BULK_INSERTED", f"TransID {id_trasmissione_batch[:8]}..., Aggiunte {successful_inserts} righe.")
    return True, f"Aggiunte {successful_inserts} righe con successo (ID Trasmissione: {id_trasmissione_batch[:8]}...)."

def check_rif_pa_exists(rif_pa: str) -> bool:
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(f"SELECT 1 FROM {TABLE_NAME} WHERE rif_pa = ? LIMIT 1", (rif_pa,))
        exists = cursor.fetchone()
        return exists is not None
    finally:
        if conn:
            conn.close()

def delete_spese_by_ids(list_of_ids: list[int], username: str) -> tuple[int, str]:
    if not list_of_ids:
        return 0, "Nessun ID fornito per l'eliminazione."
    
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        placeholders = ', '.join(['?'] * len(list_of_ids))
        query = f"DELETE FROM {TABLE_NAME} WHERE id IN ({placeholders})"
        cursor.execute(query, list_of_ids)
        conn.commit()
        deleted_count = cursor.rowcount
        log_activity(username, "DATA_BULK_DELETED", f"{deleted_count} record eliminati. IDs (fino a 10): {list_of_ids[:10]}")
        return deleted_count, f"{deleted_count} record eliminati con successo."
    except sqlite3.Error as e:
        conn.rollback()
        log_activity(username, "DB_ERROR_BULK_DELETE", f"Errore eliminazione massiva: {e}")
        return 0, f"Errore database durante l'eliminazione: {e}"
    finally:
        if conn:
            conn.close()

def get_all_spese() -> pd.DataFrame:
    conn = get_db_connection()
    try:
        df = pd.read_sql_query(f"SELECT * FROM {TABLE_NAME} ORDER BY timestamp_caricamento DESC, id DESC", conn)
        return df
    except Exception as e:
        log_activity("System", "DB_ERROR_GET_ALL", f"Errore recupero dati: {e}")
        return pd.DataFrame()
    finally:
        if conn:
            conn.close()

def get_log_content() -> str:
    try:
        with open(log_file_path, 'r', encoding='utf-8') as f: 
            lines = f.readlines()
        return "".join(lines[::-1])
    except FileNotFoundError: 
        return "File di log non ancora creato o non trovato."
    except Exception as e: 
        return f"Errore durante la lettura del file di log: {e}"
#cartella/utils/db.py