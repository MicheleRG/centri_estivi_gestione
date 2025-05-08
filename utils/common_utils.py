# cartella/utils/common_utils.py
import re
from datetime import datetime
import pandas as pd
import io
import numpy as np
from typing import Union # Manteniamo Union per compatibilità Python < 3.10 se serve altrove

def sanitize_filename_component(name_part):
    if not isinstance(name_part, str): name_part = str(name_part)
    # Rimuoviamo lo slash dai caratteri da sostituire, dato che è usato nel Rif. PA
    name_part = re.sub(r'[\\*?:"<>|]', '-', name_part) 
    name_part = name_part.strip()
    name_part = re.sub(r'\s+', '-', name_part) # Sostituisce spazi multipli con un trattino
    return name_part

def convert_df_to_excel_bytes(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Dati')
    return output.getvalue()

def generate_timestamp_filename(type_prefix="file", rif_pa_sanitized="", include_seconds=True):
    now = datetime.now()
    time_format = "%Y%m%d_%H%M%S" if include_seconds else "%Y%m%d_%H%M"
    timestamp = now.strftime(time_format)
    
    filename_parts = [type_prefix]
    if rif_pa_sanitized: filename_parts.append(rif_pa_sanitized)
    filename_parts.append(timestamp)
    return "_".join(filename_parts)

# --- Funzioni di Validazione ---
def validate_codice_fiscale(cf):
    if cf and not re.match(r"^[A-Z0-9]{16}$", cf.upper()): return False, "❌ CF non valido (16 caratt. alfanum)."
    if not cf or str(cf).strip() == "": return False, "❌ CF mancante."
    return True, "✅ OK"

def parse_excel_currency(value):
    if pd.isna(value) or str(value).strip() == "": return 0.0
    if isinstance(value, (int, float)): return float(value)
    s_val = str(value).replace("€", "").strip()
    try: return float(s_val) 
    except ValueError:
        s_val_orig = s_val
        if '.' in s_val and ',' in s_val:
            if s_val.rfind('.') > s_val.rfind(','):
                s_val = s_val.replace('.', '', s_val.count('.') -1 if s_val.count('.') > 1 else 0).replace(',', '.')
            else:
                s_val = s_val.replace(',', '')
        elif ',' in s_val:
            s_val = s_val.replace(',', '.')
        try: return float(s_val)
        except ValueError: 
            return 0.0 

def check_controlli_formali(row, col_name_dichiarati='controlli_formali_dichiarati'):
    calculated_val = round(row.get('valore_contributo_fse', 0.0) * 0.05, 2)
    declared_val_check = row.get(col_name_dichiarati)
    
    if pd.notna(declared_val_check) and isinstance(declared_val_check, (int, float, np.number)):
        declared_val = float(declared_val_check)
        if not np.isclose(declared_val, calculated_val):
            return False, f"❌ Dich./Fornito={declared_val:.2f} ≠ Calcolato={calculated_val:.2f}"
        return True, f"✅ OK (Dich./Fornito={declared_val:.2f}, Calcolato={calculated_val:.2f})"
    else:
        return True, f"ℹ️ Calcolato={calculated_val:.2f} (Nessun valore dich./fornito per confronto o colonna mancante)"

def check_sum_d(row):
    a=row.get('valore_contributo_fse',0.0);b=row.get('altri_contributi',0.0);
    c=row.get('quota_retta_destinatario',0.0);d=row.get('totale_retta',0.0)
    calc_sum=round(a+b+c,2);
    if not np.isclose(d,calc_sum): return False, f"❌ Tot.Retta D={d:.2f} ≠ Somma A+B+C={calc_sum:.2f}"
    return True, "✅ OK"

def check_contribution_rules(row):
    val_A=row.get('valore_contributo_fse',0.0)
    num_weeks_val = row.get('numero_settimane_frequenza',0)
    if pd.isna(num_weeks_val) or not isinstance(num_weeks_val, (int, float, np.number)) or num_weeks_val < 0:
        num_weeks = 0
    else:
        num_weeks = int(num_weeks_val)

    total_cost_D=row.get('totale_retta',0.0)

    if num_weeks == 0: 
        return (True,"✅ OK (0 settimane)") if np.isclose(val_A, 0.0) else (False,"❌ 0 sett. ma Contr. FSE (A) > 0")
    
    cost_per_week=round(total_cost_D/num_weeks,2) if num_weeks > 0 else 0 # Evita divisione per zero
    expected_weekly_contrib=min(cost_per_week,100.00)
    expected_total_contrib_row=round(expected_weekly_contrib*num_weeks,2)
    
    if val_A > (expected_total_contrib_row + 0.01): # Tolleranza per float
        return False, f"❌ Contr. FSE (A)={val_A:.2f} supera max calcolato ({expected_total_contrib_row:.2f} = {num_weeks} sett. * {expected_weekly_contrib:.2f}€/sett.)"
    if val_A > 300.01: # Tolleranza
         return False, f"❌ Contr. FSE (A)={val_A:.2f} supera il limite assoluto di 300€ per singola riga"
    if val_A < 0: return False, f"❌ Contr. FSE (A) non può essere negativo"
    return True, "✅ OK"

def validate_rif_pa_format(rif_pa_input: str) -> tuple[bool, str]:
    """
    Valida se il Rif. PA è ESATTAMENTE nel formato ANNO-NUMEROOPERAZIONE/RER.
    ANNO: 4 cifre.
    NUMEROOPERAZIONE: 1 o più cifre.
    Separatori: '-' e '/'.
    Finale: 'RER'.
    Restituisce: (is_valid, message)
    """
    if not rif_pa_input or not isinstance(rif_pa_input, str):
        return False, "❌ Rif. PA non fornito o non è una stringa."
    
    rif_pa_trimmed = rif_pa_input.strip()
    
    # Pattern Regex per il formato esatto: YYYY-NUM+/RER
    pattern = r"^\d{4}-\d+\/RER$" 
    
    if re.fullmatch(pattern, rif_pa_trimmed):
        return True, f"✅ Rif. PA '{rif_pa_trimmed}' ha il formato corretto."
    else:
        return False, f"❌ Rif. PA '{rif_pa_trimmed}' non è nel formato richiesto (AAAA-NUMERO/RER). Esempio: 2023-1234/RER."

# cartella/utils/common_utils.py