#cartella/utils/common_utils.py
import re
from datetime import datetime
import pandas as pd
import io
import numpy as np
# from typing import Union # Rimosso perché non utilizzato

def sanitize_filename_component(name_part: str) -> str:
    """
    Pulisce una stringa per renderla sicura come parte di un nome file.
    Sostituisce caratteri non validi e spazi multipli.
    """
    if not isinstance(name_part, str):
        name_part = str(name_part)
    name_part = re.sub(r'[\\/*?:"<>|]', '_', name_part) # Rimosso \ dal set di caratteri, non è problematico in Linux/Mac e a volte utile
    name_part = name_part.strip()
    name_part = re.sub(r'\s+', '_', name_part)
    return name_part

def convert_df_to_excel_bytes(df: pd.DataFrame) -> bytes:
    """
    Converte un DataFrame Pandas in bytes rappresentanti un file Excel (.xlsx).
    """
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Dati')
    return output.getvalue()

def generate_timestamp_filename(type_prefix: str = "file", rif_pa_sanitized: str = "", include_seconds: bool = True) -> str:
    """
    Genera un nome file con un timestamp e parti opzionali.
    """
    now = datetime.now()
    time_format = "%Y%m%d_%H%M%S" if include_seconds else "%Y%m%d_%H%M"
    timestamp = now.strftime(time_format)
    
    filename_parts = [type_prefix]
    if rif_pa_sanitized:
        filename_parts.append(rif_pa_sanitized)
    filename_parts.append(timestamp)
    
    return "_".join(filter(None, filename_parts)) # Usa filter(None, ...) per gestire parti vuote

# --- Funzioni di Validazione ---
def validate_codice_fiscale(cf: str) -> tuple[bool, str]:
    """
    Valida il formato base di un codice fiscale italiano (16 caratteri alfanumerici).
    Restituisce: (is_valid, message)
    """
    if not cf or not isinstance(cf, str) or str(cf).strip() == "":
        return False, "❌ CF mancante."
    
    cf_upper = cf.upper().strip()
    
    if not re.fullmatch(r"^[A-Z0-9]{16}$", cf_upper): # Usato re.fullmatch per chiarezza
        return False, f"❌ CF '{cf}' non valido (formato: 16 caratteri alfanumerici)."
        
    return True, f"✅ OK ({cf_upper})" # Mostra il CF validato per conferma

def parse_excel_currency(value) -> float:
    """
    Converte un valore (potenzialmente da Excel/CSV) in un float, gestendo NaN,
    simbolo Euro, e separatori decimali/migliaia comuni. Restituisce 0.0 in caso di errore.
    """
    if pd.isna(value) or str(value).strip() == "":
        return 0.0
    if isinstance(value, (int, float, np.number)): # Aggiunto np.number per maggiore copertura
        return float(value)
    
    s_val = str(value).replace("€", "").strip()
    
    # Tentativo 1: conversione diretta (per numeri semplici o già formattati correttamente come stringhe)
    try:
        return float(s_val)
    except ValueError:
        pass # Continua se fallisce

    # Tentativo 2: gestione separatori . e ,
    s_val_cleaned = s_val
    if '.' in s_val_cleaned and ',' in s_val_cleaned:
        if s_val_cleaned.rfind('.') > s_val_cleaned.rfind(','): # Formato IT/EU: 1.234,56
            s_val_cleaned = s_val_cleaned.replace('.', '').replace(',', '.')
        else: # Formato US/UK: 1,234.56
            s_val_cleaned = s_val_cleaned.replace(',', '')
    elif ',' in s_val_cleaned: # Solo virgola come decimale: 1234,56
        s_val_cleaned = s_val_cleaned.replace(',', '.')
    # Se c'è solo '.', si presume sia un decimale corretto (es. 1234.56) o un intero (1234.)
    # e il tentativo di float() dovrebbe gestirlo.

    try:
        return float(s_val_cleaned)
    except ValueError:
        # print(f"Warning: Impossibile convertire '{s_val}' (originale: '{value}') in numero. Usato 0.0.") # Per debug
        return 0.0

def check_controlli_formali(row: pd.Series, col_name_dichiarati: str = 'controlli_formali_dichiarati') -> tuple[bool, str]:
    """
    Verifica se il valore dei controlli formali dichiarato/fornito corrisponde al 5%
    calcolato del valore_contributo_fse.
    Restituisce: (is_valid, message)
    """
    valore_fse_input = row.get('valore_contributo_fse', 0.0)
    
    try:
        valore_fse = float(valore_fse_input) if pd.notna(valore_fse_input) else 0.0
    except (ValueError, TypeError):
         valore_fse = 0.0

    calculated_val = round(valore_fse * 0.05, 2)
    declared_val_input = row.get(col_name_dichiarati)
    
    declared_val_float = None
    if pd.notna(declared_val_input):
        try:
            # Tentiamo di parsare il dichiarato usando la stessa logica delle valute,
            # nel caso arrivi formattato (es. "1,50" invece di 1.50)
            declared_val_float = parse_excel_currency(declared_val_input)
        except (ValueError, TypeError): # parse_excel_currency già gestisce e restituisce 0.0
            declared_val_float = 0.0 # O un valore che indica errore di parsing se necessario
                                     # Ma per il confronto, se non è un numero, è diverso.

    if declared_val_float is not None: # Sarà sempre non None se parse_excel_currency restituisce float
        if not np.isclose(declared_val_float, calculated_val):
            return False, f"❌ Dich./Fornito ({declared_val_input})={declared_val_float:.2f} ≠ Calcolato={calculated_val:.2f}"
        else:
            return True, f"✅ OK (Dich./Fornito ({declared_val_input})={declared_val_float:.2f}, Calcolato={calculated_val:.2f})"
    else: # Questo caso non dovrebbe più verificarsi se parse_excel_currency restituisce sempre float
        return True, f"ℹ️ Calcolato={calculated_val:.2f} (Valore dich./fornito '{declared_val_input}' non numerico o mancante)"


def check_sum_d(row: pd.Series) -> tuple[bool, str]:
    """
    Verifica se Totale Retta (D) è la somma di Contr. FSE (A), Altri Contr. (B), Quota Retta (C).
    Tutti i valori sono attesi come numerici (float) nella riga.
    Restituisce: (is_valid, message)
    """
    try:
        # Si assume che le colonne siano già state parsate a float da parse_excel_currency
        a = row.get('valore_contributo_fse', 0.0)
        b = row.get('altri_contributi', 0.0)
        c = row.get('quota_retta_destinatario', 0.0)
        d = row.get('totale_retta', 0.0)

        # Verifica aggiuntiva che siano effettivamente float, anche se dovrebbero esserlo
        if not all(isinstance(val, (float, int, np.number)) for val in [a,b,c,d]):
             return False, "❌ Errore: valori A, B, C, o D non numerici (pre-parsing fallito)."

    except KeyError as e: # Se una colonna manca del tutto
         return False, f"❌ Errore: colonna mancante per il calcolo della somma D=A+B+C (colonna: {e})."
         
    calc_sum = round(a + b + c, 2)
    
    if not np.isclose(d, calc_sum):
        return False, f"❌ Tot.Retta D={d:.2f} ≠ Somma A+B+C={calc_sum:.2f} (A={a:.2f}, B={b:.2f}, C={c:.2f})"
        
    return True, f"✅ OK (D={d:.2f})"

def check_contribution_rules(row: pd.Series) -> tuple[bool, str]:
    """
    Verifica le regole sul contributo FSE (A):
    - Non negativo.
    - <= 100€/settimana.
    - <= 300€ per riga.
    - 0 se settimane = 0.
    Tutti i valori sono attesi come numerici (float/int) nella riga.
    Restituisce: (is_valid, message)
    """
    try:
        val_A = row.get('valore_contributo_fse', 0.0)
        total_cost_D = row.get('totale_retta', 0.0)
        num_weeks_val = row.get('numero_settimane_frequenza', 0) # Già atteso come int

        if not all(isinstance(v, (float, int, np.number)) for v in [val_A, total_cost_D]):
            return False, "❌ Errore: Valori non numerici per Contr. FSE o Totale Retta (pre-parsing fallito)."
        if not isinstance(num_weeks_val, (int, np.integer)): # numero_settimane_frequenza dovrebbe essere int
            return False, "❌ Errore: N. settimane non è un intero (pre-parsing fallito)."
        num_weeks = int(num_weeks_val)

    except KeyError as e:
         return False, f"❌ Errore: colonna mancante per verifica regole contributo (colonna: {e})."

    if val_A < 0: # Tolleranza per <0 non necessaria, deve essere >=0
        return False, f"❌ Contr. FSE (A)={val_A:.2f} non può essere negativo."

    # Limite assoluto per riga
    # Usiamo np.isclose per il confronto ">" aggiungendo una piccola tolleranza al limite,
    # o confrontando direttamente se val_A > (limite + epsilon)
    # Qui, un confronto diretto è più chiaro:
    if val_A > 300.0001: # Leggera tolleranza per l'input
         return False, f"❌ Contr. FSE (A)={val_A:.2f} supera il limite assoluto di 300€ per singola riga."

    if num_weeks == 0:
        if not np.isclose(val_A, 0.0): # Se 0 settimane, il contributo FSE deve essere 0
            return False, f"❌ Contr. FSE (A)={val_A:.2f} > 0 ma N. settimane è 0."
        else:
            return True, "✅ OK (0 settimane, Contr. FSE=0)" # Messaggio più specifico
            
    # Se num_weeks > 0
    # Costo per settimana della retta totale D
    # Se total_cost_D è 0 e num_weeks > 0, cost_per_week è 0.
    cost_per_week = round(total_cost_D / num_weeks, 2) if num_weeks > 0 else 0.0
    
    # Il contributo settimanale FSE non può superare 100€ né il costo settimanale effettivo
    max_weekly_contrib_allowed = min(cost_per_week, 100.00)
    
    # Contributo FSE totale atteso per la riga, basato sulle settimane e sul cap settimanale
    expected_total_contrib_for_row = round(max_weekly_contrib_allowed * num_weeks, 2)
    
    # Il contributo FSE dichiarato (val_A) non deve superare quello calcolato/atteso
    # val_A vs expected_total_contrib_for_row
    # Esempio: 3 settimane, costo retta 50€/sett. -> max_weekly_contrib_allowed = 50€. expected_total_contrib_for_row = 150€.
    #          val_A non può superare 150€.
    # Esempio: 3 settimane, costo retta 120€/sett. -> max_weekly_contrib_allowed = 100€. expected_total_contrib_for_row = 300€.
    #          val_A non può superare 300€.

    if val_A > (expected_total_contrib_for_row + 0.0001): # Tolleranza per confronto
        return False, (f"❌ Contr. FSE (A)={val_A:.2f} supera il massimo calcolabile per N. settimane ({expected_total_contrib_for_row:.2f} = "
                       f"{num_weeks} sett. * {max_weekly_contrib_allowed:.2f}€/sett. (min tra costo/sett: {cost_per_week:.2f} e cap 100€))")
         
    return True, f"✅ OK (Contr.FSE={val_A:.2f} ≤ Max calcolato={expected_total_contrib_for_row:.2f})"


def validate_rif_pa_format(rif_pa_input: str) -> tuple[bool, str]:
    """
    Valida se il Rif. PA è ESATTAMENTE nel formato ANNO-NUMEROOPERAZIONE/RER.
    Restituisce: (is_valid, message)
    """
    if not rif_pa_input or not isinstance(rif_pa_input, str):
        return False, "❌ Rif. PA non fornito o non è una stringa."
    
    rif_pa_trimmed = rif_pa_input.strip()
    pattern = r"^\d{4}-\d+\/RER$" 
    
    if re.fullmatch(pattern, rif_pa_trimmed): # Usato re.fullmatch per chiarezza
        return True, f"✅ Rif. PA '{rif_pa_trimmed}' ha il formato corretto."
    else:
        return False, f"❌ Rif. PA '{rif_pa_trimmed}' non è nel formato richiesto (AAAA-NUMERO/RER). Esempio: 2023-1234/RER."

# NUOVA FUNZIONE PER CENTRALIZZARE LE VALIDAZIONI DETTAGLIATE
def run_detailed_validations(
    df_to_validate: pd.DataFrame,
    cf_col_clean: str,  # Nome della colonna con CF pulito (es. 'codice_fiscale_bambino_pulito')
    original_date_col: str, # Nome della colonna con la data originale stringa
    parsed_date_col: str,   # Nome della colonna con la data parsata a oggetto date
    declared_formal_controls_col: str, # Nome della colonna con i controlli formali dichiarati/da CSV
    row_offset_for_messages: int = 1 # 1 per Richiedente (0-indexed +1), 2 per Controllore (CSV header + 0-indexed +1)
) -> tuple[pd.DataFrame, bool]:
    """
    Esegue una serie di validazioni su un DataFrame pre-processato.
    Args:
        df_to_validate: DataFrame con dati già parsati (date, valute, settimane come int).
                        Deve contenere le colonne per CF, date, importi, settimane, etc.
                        e la colonna cf_col_clean.
        cf_col_clean: Il nome della colonna contenente i codici fiscali puliti e pronti per la validazione.
        original_date_col: Nome della colonna stringa originale per la data.
        parsed_date_col: Nome della colonna con la data già parsata a oggetto datetime.date.
        declared_formal_controls_col: Nome della colonna per i controlli formali dichiarati.
        row_offset_for_messages: Usato per numerare le righe nei messaggi di errore (es. riga Excel/CSV).
    Returns:
        pd.DataFrame: DataFrame con i risultati della validazione per ogni riga.
        bool: True se ci sono errori bloccanti, False altrimenti.
    """
    validation_results_list = []
    has_blocking_errors_overall = False

    # --- 1. Controllo CF Duplicati nel Batch ---
    # Considera solo CF non vuoti per il controllo duplicati
    valid_cfs_for_dup_check = df_to_validate[df_to_validate[cf_col_clean].str.strip() != ''][cf_col_clean]
    if not valid_cfs_for_dup_check.empty:
        cf_counts = valid_cfs_for_dup_check.value_counts()
        duplicated_cfs_series = cf_counts[cf_counts > 1]
        if not duplicated_cfs_series.empty:
            has_blocking_errors_overall = True
            for cf_dupl, count in duplicated_cfs_series.items():
                err_msg = f"❌ Il Codice Fiscale '{cf_dupl}' è presente {count} volte nel batch."
                validation_results_list.append({
                    'Riga': "Batch", 'Bambino': "N/A", 'Esito CF': "N/A",
                    'Esito Data Mandato': "N/A", 'Esito D=A+B+C': "N/A",
                    'Esito Regole Contr.FSE': "N/A", 'Esito Contr.Formali 5%': "N/A",
                    'Errori Bloccanti': err_msg,
                    'Verifica Max 300€ FSE per Bambino (batch)': "N/A"
                })

    # --- 2. Validazioni per Riga ---
    for index, row in df_to_validate.iterrows():
        row_errors = []
        
        # Validazione CF
        cf_to_val = row.get(cf_col_clean, '')
        cf_ok, cf_msg = validate_codice_fiscale(cf_to_val)
        if not cf_ok: row_errors.append(cf_msg)

        # Validazione Data (già parsata, qui formattiamo il messaggio)
        data_obj = row.get(parsed_date_col)
        data_orig_str = str(row.get(original_date_col, '')).strip()
        data_ok, msg_data = False, f"❌ Data '{data_orig_str}' non riconosciuta."
        if pd.notna(data_obj) and hasattr(data_obj, 'strftime'): # Verifica che sia un oggetto data/datetime valido
            data_ok = True
            data_fmt = data_obj.strftime('%d/%m/%Y')
            msg_data = f"✅ Data '{data_orig_str}' → {data_fmt}" if data_orig_str != data_fmt else f"✅ OK ({data_fmt})"
        if not data_ok: row_errors.append(msg_data)
            
        # Altre Validazioni per Riga
        sum_ok, sum_msg = check_sum_d(row)
        if not sum_ok: row_errors.append(sum_msg)
        
        contrib_ok, contrib_msg = check_contribution_rules(row)
        if not contrib_ok: row_errors.append(contrib_msg)
        
        cf5_ok, cf5_msg = check_controlli_formali(row, declared_formal_controls_col)
        if not cf5_ok: row_errors.append(cf5_msg)

        if any("❌" in e for e in row_errors):
            has_blocking_errors_overall = True
        
        validation_results_list.append({
            'Riga': index + row_offset_for_messages,
            'Bambino': row.get('bambino_cognome_nome', 'N/A'),
            'Esito CF': cf_msg,
            'Esito Data Mandato': msg_data,
            'Esito D=A+B+C': sum_msg,
            'Esito Regole Contr.FSE': contrib_msg,
            'Esito Contr.Formali 5%': cf5_msg,
            'Errori Bloccanti': " ; ".join(row_errors) if row_errors else "Nessuno",
            'Verifica Max 300€ FSE per Bambino (batch)': '⏳' # Placeholder, verrà aggiornato dopo
        })

    df_results = pd.DataFrame(validation_results_list)

    # --- 3. Check Aggregato Max 300€ FSE per Bambino (nel batch) ---
    col_cap_agg = "Verifica Max 300€ FSE per Bambino (batch)"
    if not df_results.empty and col_cap_agg in df_results.columns: # Assicurati che la colonna esista
        df_results[col_cap_agg] = '✅ OK' # Default

    if cf_col_clean in df_to_validate.columns and 'valore_contributo_fse' in df_to_validate.columns:
        # Escludi righe con CF vuoto dal calcolo aggregato
        valid_cf_rows_for_agg = df_to_validate[df_to_validate[cf_col_clean].str.strip() != '']
        if not valid_cf_rows_for_agg.empty:
            contrib_per_child = valid_cf_rows_for_agg.groupby(cf_col_clean)['valore_contributo_fse'].sum()
            children_over_cap = contrib_per_child[contrib_per_child > 300.0001] # Tolleranza
            
            if not children_over_cap.empty:
                has_blocking_errors_overall = True
                for cf_val, total_contrib in children_over_cap.items():
                    error_msg_cap = f"❌ Superato cap 300€ ({total_contrib:.2f}€ totali nel batch)"
                    
                    # Trova gli indici originali (nel df_to_validate) corrispondenti al CF
                    original_indices = df_to_validate.index[df_to_validate[cf_col_clean] == cf_val].tolist()
                    
                    for orig_idx in original_indices:
                        # Trova la riga corrispondente nel DataFrame dei risultati (df_results)
                        # basandosi sull'indice originale + offset
                        row_mask_results = df_results['Riga'] == (orig_idx + row_offset_for_messages)
                        
                        if not df_results.loc[row_mask_results].empty:
                            df_results.loc[row_mask_results, col_cap_agg] = error_msg_cap
                            current_errs = df_results.loc[row_mask_results, 'Errori Bloccanti'].iloc[0]
                            if error_msg_cap not in current_errs:
                                if current_errs == "Nessuno" or current_errs == "":
                                    df_results.loc[row_mask_results, 'Errori Bloccanti'] = error_msg_cap
                                else:
                                    df_results.loc[row_mask_results, 'Errori Bloccanti'] += "; " + error_msg_cap
    
    # Assicurarsi che 'Errori Bloccanti' sia 'Nessuno' se vuoto
    if 'Errori Bloccanti' in df_results.columns:
        df_results['Errori Bloccanti'] = df_results['Errori Bloccanti'].apply(lambda x: x if x and x.strip() != "Nessuno" else "Nessuno")

    return df_results, has_blocking_errors_overall

# cartella/utils/common_utils.py