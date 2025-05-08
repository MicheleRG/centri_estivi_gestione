# cartella/utils/common_utils.py
import re
from datetime import datetime
import pandas as pd
import io
import numpy as np
from typing import Union # Manteniamo per altre eventuali funzioni

def sanitize_filename_component(name_part):
    """
    Pulisce una stringa per renderla sicura come parte di un nome file.
    Sostituisce caratteri non validi e spazi multipli.
    """
    if not isinstance(name_part, str):
        name_part = str(name_part)
    # Sostituisci caratteri non validi con '_'
    name_part = re.sub(r'[\\*?:"<>|]', '_', name_part)
    name_part = name_part.strip()
    # Sostituisci uno o più spazi con '_'
    name_part = re.sub(r'\s+', '_', name_part)
    return name_part

def convert_df_to_excel_bytes(df):
    """
    Converte un DataFrame Pandas in bytes rappresentanti un file Excel (.xlsx).
    """
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Dati')
    # output.seek(0) # Non necessario per getvalue()
    return output.getvalue()

def generate_timestamp_filename(type_prefix="file", rif_pa_sanitized="", include_seconds=True):
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
    
    # Unisci con underscore per un nome file leggibile
    return "_".join(filename_parts)

# --- Funzioni di Validazione ---
def validate_codice_fiscale(cf):
    """
    Valida il formato base di un codice fiscale italiano (16 caratteri alfanumerici).
    Restituisce: (is_valid, message)
    """
    if not cf or not isinstance(cf, str) or str(cf).strip() == "":
        return False, "❌ CF mancante."
    
    cf_upper = cf.upper().strip()
    
    if not re.match(r"^[A-Z0-9]{16}$", cf_upper):
        return False, f"❌ CF '{cf}' non valido (16 caratt. alfanum)."
        
    return True, "✅ OK"

def parse_excel_currency(value):
    """
    Converte un valore (potenzialmente da Excel/CSV) in un float, gestendo NaN,
    simbolo Euro, e separatori decimali/migliaia comuni. Restituisce 0.0 in caso di errore.
    """
    if pd.isna(value) or str(value).strip() == "":
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    
    s_val = str(value).replace("€", "").strip()
    
    try:
        # Tentativo diretto (potrebbe funzionare per formati semplici o già numerici come stringa)
        return float(s_val)
    except ValueError:
        # Gestione formati con separatori . e ,
        s_val_orig = s_val
        if '.' in s_val and ',' in s_val:
            # Determina quale è il separatore decimale controllando l'ultima occorrenza
            if s_val.rfind('.') > s_val.rfind(','): # Formato stile IT/EU: 1.234,56
                # Rimuovi i separatori delle migliaia (.), sostituisci la virgola decimale con un punto
                s_val = s_val.replace('.', '').replace(',', '.')
            else: # Formato stile US/UK: 1,234.56
                # Rimuovi i separatori delle migliaia (,)
                s_val = s_val.replace(',', '')
        elif ',' in s_val: # Formato con solo virgola decimale: 1234,56
            s_val = s_val.replace(',', '.')
        
        # Ultimo tentativo di conversione dopo la pulizia
        try:
            return float(s_val)
        except ValueError:
            # Impossibile convertire, restituisci 0.0 (o logga/avvisa se necessario)
            # print(f"Warning: Impossibile convertire '{s_val_orig}' in numero. Usato 0.0.")
            return 0.0

def check_controlli_formali(row, col_name_dichiarati='controlli_formali_dichiarati'):
    """
    Verifica se il valore dei controlli formali dichiarato/fornito corrisponde al 5%
    calcolato del valore_contributo_fse.
    Restituisce: (is_valid, message)
    """
    valore_fse = row.get('valore_contributo_fse', 0.0)
    # Assicura che valore_fse sia numerico
    try:
        valore_fse = float(valore_fse) if pd.notna(valore_fse) else 0.0
    except (ValueError, TypeError):
         valore_fse = 0.0 # Se non numerico, consideralo 0 per il calcolo

    calculated_val = round(valore_fse * 0.05, 2)
    declared_val_check = row.get(col_name_dichiarati)
    
    declared_val_float = None
    if pd.notna(declared_val_check):
        try:
            declared_val_float = float(declared_val_check)
        except (ValueError, TypeError):
            declared_val_float = None # Non è un numero valido

    if declared_val_float is not None:
        # Confronta solo se il valore dichiarato è un numero valido
        if not np.isclose(declared_val_float, calculated_val):
            return False, f"❌ Dich./Fornito={declared_val_float:.2f} ≠ Calcolato={calculated_val:.2f}"
        else:
            return True, f"✅ OK (Dich./Fornito={declared_val_float:.2f}, Calcolato={calculated_val:.2f})"
    else:
        # Nessun valore dichiarato/fornito valido per confronto
        return True, f"ℹ️ Calcolato={calculated_val:.2f} (Nessun valore dich./fornito valido per confronto)"

def check_sum_d(row):
    """
    Verifica se Totale Retta (D) è la somma di Contr. FSE (A), Altri Contr. (B), Quota Retta (C).
    Restituisce: (is_valid, message)
    """
    try:
        a = float(row.get('valore_contributo_fse',0.0)) if pd.notna(row.get('valore_contributo_fse')) else 0.0
        b = float(row.get('altri_contributi',0.0)) if pd.notna(row.get('altri_contributi')) else 0.0
        c = float(row.get('quota_retta_destinatario',0.0)) if pd.notna(row.get('quota_retta_destinatario')) else 0.0
        d = float(row.get('totale_retta',0.0)) if pd.notna(row.get('totale_retta')) else 0.0
    except (ValueError, TypeError):
         return False, "❌ Errore: valori A, B, C, o D non numerici."
         
    calc_sum = round(a + b + c, 2)
    
    # Usa np.isclose per gestire le imprecisioni dei float
    if not np.isclose(d, calc_sum):
        return False, f"❌ Tot.Retta D={d:.2f} ≠ Somma A+B+C={calc_sum:.2f}"
        
    return True, "✅ OK"

def check_contribution_rules(row):
    """
    Verifica le regole sul contributo FSE (A):
    - Non negativo.
    - <= 100€/settimana.
    - <= 300€ per riga (check aggregato è separato).
    - 0 se settimane = 0.
    Restituisce: (is_valid, message)
    """
    try:
        val_A = float(row.get('valore_contributo_fse',0.0)) if pd.notna(row.get('valore_contributo_fse')) else 0.0
        total_cost_D = float(row.get('totale_retta',0.0)) if pd.notna(row.get('totale_retta')) else 0.0
        num_weeks_val = row.get('numero_settimane_frequenza',0)
        if pd.isna(num_weeks_val) or not isinstance(num_weeks_val, (int, float, np.number)) or num_weeks_val < 0:
            num_weeks = 0
        else:
            num_weeks = int(float(num_weeks_val)) # Assicura intero
    except (ValueError, TypeError):
        return False, "❌ Errore: Valori non numerici per Contr. FSE, Totale Retta o Settimane."

    if val_A < 0:
        return False, f"❌ Contr. FSE (A)={val_A:.2f} non può essere negativo"

    if num_weeks == 0:
        if not np.isclose(val_A, 0.0):
            return False, "❌ 0 settimane ma Contr. FSE (A) > 0"
        else:
            return True, "✅ OK (0 settimane)"
            
    # Se num_weeks > 0
    cost_per_week = round(total_cost_D / num_weeks, 2)
    expected_weekly_contrib = min(cost_per_week, 100.00) # Max 100€/settimana
    expected_total_contrib_row = round(expected_weekly_contrib * num_weeks, 2)
    
    # Aggiungiamo una piccola tolleranza per i confronti float
    tolerance = 0.01
    
    if val_A > (expected_total_contrib_row + tolerance):
        return False, f"❌ Contr. FSE (A)={val_A:.2f} supera max calcolato per N.settimane ({expected_total_contrib_row:.2f} = {num_weeks} sett. * {expected_weekly_contrib:.2f}€/sett.)"
        
    if val_A > (300.00 + tolerance):
         return False, f"❌ Contr. FSE (A)={val_A:.2f} supera il limite assoluto di 300€ per singola riga"
         
    return True, "✅ OK"

def validate_rif_pa_format(rif_pa_input: str) -> tuple[bool, str]:
    """
    Valida se il Rif. PA è ESATTAMENTE nel formato ANNO-NUMEROOPERAZIONE/RER.
    Restituisce: (is_valid, message)
    """
    if not rif_pa_input or not isinstance(rif_pa_input, str):
        return False, "❌ Rif. PA non fornito o non è una stringa."
    
    rif_pa_trimmed = rif_pa_input.strip()
    
    # Pattern Regex per il formato esatto: YYYY-NUM+/RER
    # ^         : inizio stringa
    # \d{4}     : esattamente 4 cifre (anno)
    # -         : trattino letterale
    # \d+       : una o più cifre (numero operazione)
    # \/        : slash letterale (escape con \)
    # RER       : lettere RER letterali
    # $         : fine stringa
    pattern = r"^\d{4}-\d+\/RER$" 
    
    if re.fullmatch(pattern, rif_pa_trimmed):
        return True, f"✅ Rif. PA '{rif_pa_trimmed}' ha il formato corretto."
    else:
        return False, f"❌ Rif. PA '{rif_pa_trimmed}' non è nel formato richiesto (AAAA-NUMERO/RER). Esempio: 2023-1234/RER."

# cartella/utils/common_utils.py