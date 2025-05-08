#cartella/utils/db.py
import sqlite3
import pandas as pd
from datetime import datetime, date # Assicurati che 'date' sia importato
import logging
import os
from logging.handlers import RotatingFileHandler
import uuid

# ... (Configurazione logger, path, tabelle, adattatori/convertitori SQLite come prima) ...
# Configurazione del logger 
log_dir = "database"
os.makedirs(log_dir, exist_ok=True)
log_file_path = os.path.join(log_dir, "activity.log")
file_handler = RotatingFileHandler(log_file_path, maxBytes=1024*1024*5, backupCount=2)
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(username)s - %(levelname)s - %(message)s'))
logger = logging.getLogger(__name__)
if not logger.handlers:
    logger.setLevel(logging.INFO)
    logger.addHandler(file_handler)
    logger.propagate = False

DATABASE_PATH = os.path.join(log_dir, 'spese.db')
TABLE_NAME = 'spese_sostenute'
SETTINGS_TABLE_NAME = 'admin_settings'

# Adattatori e convertitori SQLite per date/datetime
def adapt_date_iso(val):
    """Adatta un oggetto date di Python al formato ISO YYYY-MM-DD per SQLite."""
    if isinstance(val, date): return val.isoformat()
    return None
def convert_date(val):
    """Converte una stringa ISO YYYY-MM-DD da SQLite a un oggetto date di Python."""
    if val: 
        try:
            return date.fromisoformat(val.decode())
        except (ValueError, TypeError):
            return None # Restituisce None se la conversione fallisce
    return None
def adapt_datetime_iso(val): 
    """Adatta un oggetto datetime di Python al formato ISO per SQLite."""
    if isinstance(val, datetime): return val.isoformat(sep=' ', timespec='seconds') # Formato comune per DATETIME
    return None
def convert_datetime(val): 
    """Converte una stringa ISO da SQLite a un oggetto datetime di Python."""
    if val:
        try:
             # Prova a parsare con diversi formati comuni se necessario
            return datetime.fromisoformat(val.decode().replace(' ', 'T'))
        except (ValueError, TypeError):
             try:
                 # Fallback per formati senza T o con precisione diversa
                 return datetime.strptime(val.decode(), '%Y-%m-%d %H:%M:%S')
             except (ValueError, TypeError):
                 return None
    return None

sqlite3.register_adapter(date, adapt_date_iso)
sqlite3.register_converter("DATE", convert_date)
sqlite3.register_adapter(datetime, adapt_datetime_iso)
sqlite3.register_converter("DATETIME", convert_datetime) # Assicurati che DATETIME sia usato o usa TEXT

def get_db_connection():
    conn = sqlite3.connect(DATABASE_PATH, detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    # Creazione tabella spese_sostenute (assicurati che data_mandato sia DATE e timestamp DATETIME)
    cursor.execute(f"""
    CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        id_trasmissione TEXT NOT NULL,      
        rif_pa TEXT,                          
        cup TEXT,                             
        distretto TEXT,                       
        comune_capofila TEXT,                 
        numero_mandato TEXT,
        data_mandato DATE, -- Tipo DATE per usare i convertitori
        comune_titolare_mandato TEXT,
        importo_mandato REAL,
        comune_centro_estivo TEXT,
        centro_estivo TEXT,
        genitore_cognome_nome TEXT,
        bambino_cognome_nome TEXT NOT NULL,
        codice_fiscale_bambino TEXT NOT NULL,
        valore_contributo_fse REAL,           
        altri_contributi REAL,                
        quota_retta_destinatario REAL,        
        totale_retta REAL,                    
        numero_settimane_frequenza INTEGER,
        controlli_formali REAL,               
        timestamp_caricamento DATETIME, -- Tipo DATETIME per usare i convertitori
        utente_caricamento TEXT,
        UNIQUE(codice_fiscale_bambino, data_mandato, centro_estivo, rif_pa, cup, id_trasmissione) 
    )
    """)
    # Creazione tabella admin_settings (come prima, potrebbe essere vuota ora)
    cursor.execute(f"""
    CREATE TABLE IF NOT EXISTS {SETTINGS_TABLE_NAME} (
        setting_key TEXT PRIMARY KEY,
        setting_value TEXT
    )
    """)
    conn.commit()
    conn.close()
    logger.info("Database inizializzato.")

# Funzione log_activity (invariata)
def log_activity(username, action, details=""):
    extra_info = {'username': username if username else "System"}
    log_record = logging.LogRecord(
        name=__name__, level=logging.INFO, pathname=__file__, lineno=0, 
        msg=f"{action} - {details}", args=(), exc_info=None, func=''
    )
    log_record.username = username if username else "System"
    logger.handle(log_record)

# --- MODIFICA FUNZIONE add_spesa ---
def add_spesa(data_dict, username): # Rinominato parametro per chiarezza
    """
    Aggiunge una singola riga di spesa al database. 
    Si aspetta che i dati siano già validati e nel tipo corretto, 
    specialmente la data_mandato come oggetto datetime.date.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    id_trasmissione = data_dict.get('id_trasmissione', str(uuid.uuid4()))
        
    try:
        # Preparazione dati per il DB (minima conversione necessaria ora)
        
        # Data Mandato: Assume sia già un oggetto date o None
        data_mandato_obj = data_dict.get('data_mandato')
        if not isinstance(data_mandato_obj, date) and data_mandato_obj is not None:
             # Se per qualche motivo non è un oggetto date, logga un warning e mettilo a None
             log_activity(username, "DB_INSERT_WARNING", f"data_mandato non era oggetto date per {data_dict.get('bambino_cognome_nome')}, valore: {data_mandato_obj}. Impostato a NULL.")
             data_mandato_obj = None
             
        # Valore Contributo FSE e Controlli Formali (calcolo rimane)
        try: 
            # Assicura che sia float, gestendo anche input numerici
            val_contr_fse = float(data_dict.get('valore_contributo_fse', 0.0))
        except (ValueError, TypeError): 
            val_contr_fse = 0.0
        controlli_formali_calcolati = round(val_contr_fse * 0.05, 2)

        # Assicura che gli altri campi numerici siano del tipo corretto (float/int) o None
        # Questa parte è importante se il DataFrame ha ancora tipi misti
        def safe_float(val, default=0.0):
            try: return float(val) if pd.notna(val) else default
            except (ValueError, TypeError): return default
        
        def safe_int(val, default=0):
             try: return int(float(val)) if pd.notna(val) else default # Converte prima a float per gestire "3.0"
             except (ValueError, TypeError): return default

        importo_mandato_db = safe_float(data_dict.get('importo_mandato'))
        altri_contributi_db = safe_float(data_dict.get('altri_contributi'))
        quota_retta_dest_db = safe_float(data_dict.get('quota_retta_destinatario'))
        totale_retta_db = safe_float(data_dict.get('totale_retta'))
        num_sett_freq_db = safe_int(data_dict.get('numero_settimane_frequenza'))

        # Inserimento dati
        cursor.execute(f"""
        INSERT INTO {TABLE_NAME} (
            id_trasmissione, rif_pa, cup, distretto, comune_capofila, 
            numero_mandato, data_mandato, comune_titolare_mandato, importo_mandato,
            comune_centro_estivo, centro_estivo, genitore_cognome_nome, bambino_cognome_nome,
            codice_fiscale_bambino, valore_contributo_fse, altri_contributi,
            quota_retta_destinatario, totale_retta, numero_settimane_frequenza,
            controlli_formali, timestamp_caricamento, utente_caricamento
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) 
        """, (
            id_trasmissione, data_dict.get('rif_pa'), data_dict.get('cup'), data_dict.get('distretto'), data_dict.get('comune_capofila'), 
            data_dict.get('numero_mandato'), 
            data_mandato_obj, # Passa l'oggetto date o None
            data_dict.get('comune_titolare_mandato'), 
            importo_mandato_db,
            data_dict.get('comune_centro_estivo'), data_dict.get('centro_estivo'), data_dict.get('genitore_cognome_nome'), data_dict.get('bambino_cognome_nome'),
            data_dict.get('codice_fiscale_bambino'), 
            val_contr_fse, # Già float
            altri_contributi_db,
            quota_retta_dest_db, 
            totale_retta_db, 
            num_sett_freq_db,
            controlli_formali_calcolati, 
            datetime.now(), # Usa datetime per il timestamp
            username
        ))
        conn.commit()
        # log_activity(username, "DATA_INSERTED_ROW", f"TransID {id_trasmissione[:8]}, SpesaID {cursor.lastrowid}") # Log meno verboso
        return True, f"Riga per {data_dict.get('bambino_cognome_nome', 'N/D')} aggiunta."
    except sqlite3.IntegrityError as e:
        conn.rollback() # Annulla transazione in caso di errore
        log_activity(username, "DB_ERROR_INTEGRITY", f"TransID {id_trasmissione[:8]}, Errore: {e}. Dati: Bambino={data_dict.get('bambino_cognome_nome')}, CF={data_dict.get('codice_fiscale_bambino')}, Data={data_mandato_obj}, RifPA={data_dict.get('rif_pa')}")
        return False, f"Errore: Registrazione duplicata per Rif.PA/Bambino/Data/Centro (Bambino: {data_dict.get('bambino_cognome_nome', 'N/D')})."
    except sqlite3.Error as e:
        conn.rollback()
        log_activity(username, "DB_ERROR_INSERT", f"TransID {id_trasmissione[:8]}, Errore: {e}")
        return False, f"Errore Database: {e}"
    finally:
        conn.close()
# --- FINE MODIFICA FUNZIONE add_spesa ---

# Funzione add_multiple_spese (invariata logicamente, chiama la nuova add_spesa)
def add_multiple_spese(df_spese_con_metadati_e_id, username):
    id_trasmissione = df_spese_con_metadati_e_id['id_trasmissione'].iloc[0] if not df_spese_con_metadati_e_id.empty else 'N/A'
    successful_inserts = 0
    failed_inserts = 0
    errors_detail = []

    for index, row_data in df_spese_con_metadati_e_id.iterrows():
        data_dict = row_data.to_dict() 
        # La conversione della data è già avvenuta nella pagina del Controllore
        # if 'data_mandato' in data_dict and pd.isna(data_dict.get('data_mandato')): 
        #     data_dict['data_mandato'] = None
        
        success, msg = add_spesa(data_dict, username) # Chiama la nuova add_spesa
        if success: 
            successful_inserts += 1
        else: 
            failed_inserts += 1
            # Riga CSV è index + 2 (header + 0-based index)
            errors_detail.append(f"Riga CSV {index+2}: {msg}") 

    if failed_inserts > 0:
        details_str = '; '.join(errors_detail)
        log_activity(username, "DATA_BULK_INSERT_PARTIAL", f"TransID {id_trasmissione[:8]}, Aggiunte {successful_inserts}, Fallite: {failed_inserts}. Errori: {details_str[:500]}")
        return False, f"ID Trasmissione: {id_trasmissione[:8]}...\nAggiunte {successful_inserts} righe. {failed_inserts} righe non importate.\nErrori dettaglio:\n- " + "\n- ".join(errors_detail)
    
    log_activity(username, "DATA_BULK_INSERTED", f"TransID {id_trasmissione[:8]}, Aggiunte {successful_inserts} righe.")
    return True, f"Aggiunte {successful_inserts} righe con successo (ID Trasmissione: {id_trasmissione[:8]}...)."

# Funzione check_rif_pa_exists (invariata)
def check_rif_pa_exists(rif_pa):
    """Controlla se esiste già almeno un record con questo rif_pa."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(f"SELECT 1 FROM {TABLE_NAME} WHERE rif_pa = ? LIMIT 1", (rif_pa,))
    exists = cursor.fetchone()
    conn.close()
    return exists is not None

# Funzione delete_spese_by_ids (invariata)
def delete_spese_by_ids(list_of_ids, username):
    """Elimina una lista di spese dato i loro ID."""
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
        conn.close()

# Funzione get_all_spese (assicurarsi che gestisca le date correttamente lette)
def get_all_spese():
    """Recupera tutte le spese dal database."""
    conn = get_db_connection()
    try:
        df = pd.read_sql_query(f"SELECT * FROM {TABLE_NAME} ORDER BY timestamp_caricamento DESC, id DESC", conn)
        # I convertitori registrati dovrebbero gestire automaticamente la conversione
        # da stringa ISO (letta dal DB) a oggetti date/datetime di Python
        # Se non funzionasse, la conversione manuale sarebbe:
        # if 'data_mandato' in df.columns:
        #     df['data_mandato'] = pd.to_datetime(df['data_mandato'], errors='coerce').dt.date
        # if 'timestamp_caricamento' in df.columns:
        #      df['timestamp_caricamento'] = pd.to_datetime(df['timestamp_caricamento'], errors='coerce')
        return df
    except Exception as e: # Cattura eccezione più generica
        log_activity("System", "DB_ERROR_GET_ALL", f"Errore recupero dati: {e}")
        return pd.DataFrame() # Restituisce DataFrame vuoto in caso di errore
    finally: 
        conn.close()

# Funzioni get_setting, update_setting (probabilmente non più usate, possono essere rimosse o commentate)
# def get_setting(key): ...
# def update_setting(key, value, username): ...

# Funzione get_log_content (invariata)
def get_log_content():
    try:
        with open(log_file_path, 'r', encoding='utf-8') as f: 
            lines = f.readlines()
        return "".join(lines[::-1]) 
    except FileNotFoundError: 
        return "File di log non ancora creato."
    except Exception as e: 
        return f"Errore lettura log: {e}"

# Blocco init_db() (viene chiamato una volta all'import)
# init_db() # Spostato alla fine per assicurare che tutte le funzioni siano definite

if __name__ != "__main__": # Esegui init_db solo quando il modulo viene importato
    init_db()

#cartella/utils/db.py