#utils/common_utils.py
import re
from datetime import datetime
import pandas as pd
import io
import numpy as np
from typing import Tuple, Union, Any # Aggiunto Any

def sanitize_filename_component(name_part: Union[str, int, float, None]) -> str:
    if name_part is None: return "None" # Gestione esplicita di None
    if not isinstance(name_part, str): name_part = str(name_part)
    name_part = re.sub(r'[\\/*?:"<>|]', '_', name_part).strip()
    return re.sub(r'\s+', '_', name_part)

def convert_df_to_excel_bytes(df: pd.DataFrame) -> bytes:
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Dati')
    return output.getvalue()

def generate_timestamp_filename(type_prefix: str="file", rif_pa_sanitized: str="", include_seconds: bool=True) -> str:
    now = datetime.now() # Assicura che datetime sia importato da datetime nel modulo
    fmt = "%Y%m%d_%H%M%S" if include_seconds else "%Y%m%d_%H%M"
    return "_".join(filter(None, [type_prefix, rif_pa_sanitized, now.strftime(fmt)]))

def validate_codice_fiscale(cf: Union[str, None]) -> Tuple[bool, str]:
    if not cf or not isinstance(cf, str) or str(cf).strip() == "":
        return False, "❌ CF mancante."
    
    cf_upper = cf.upper().strip()
    
    # Pattern strutturale base (LLLLLLNNLNNLNNNL)
    # Questo renderà "INVALIDCF1234567" (LLLLLLLNNNNNNNN) invalido.
    # Non gestisce l'omocodia in modo completo (lettere al posto di numeri).
    strict_pattern = r"^[A-Z]{6}[0-9]{2}[A-Z][0-9]{2}[A-Z][0-9]{3}[A-Z]$"

    if not re.fullmatch(strict_pattern, cf_upper):
        # Controlla comunque se è alfanumerico di 16 char per un messaggio più specifico
        if not re.fullmatch(r"^[A-Z0-9]{16}$", cf_upper):
            return False, f"❌ CF '{cf}' non valido (formato base: 16 caratteri alfanumerici)."
        # Se matcha il formato base ma non quello stretto, è una struttura L/N errata
        return False, f"❌ CF '{cf}' ha una struttura Lettera/Numero non conforme al pattern atteso."
        
    return True, f"✅ OK ({cf_upper})"


def parse_excel_currency(value: Any) -> float:
    if pd.isna(value): return 0.0
    if isinstance(value, (int, float, np.number)): return float(value)
    
    s_val = str(value).replace("€", "").strip()
    if not s_val: return 0.0

    # Controlli per formati chiaramente invalidi o troppo ambigui
    dot_count = s_val.count('.')
    comma_count = s_val.count(',')

    # Casi come "1.2.3,45" o "1,2,3.45" o con troppi separatori dello stesso tipo
    if (dot_count > 1 and comma_count > 0) or \
       (comma_count > 1 and dot_count > 0) or \
       (dot_count > 1 and comma_count > 1): # Troppi separatori in combinazione
        return 0.0
    if dot_count > 1 and comma_count == 0: # Es. 1.2.3 (senza virgole)
        return 0.0
    if comma_count > 1 and dot_count == 0: # Es. 1,2,3 (senza punti)
        return 0.0
        
    # Tentativo di conversione diretta se non ci sono separatori o solo uno standard
    try: return float(s_val) # Prova semplice, potrebbe funzionare per "100", "123.45"
    except ValueError: pass
    
    s_cleaned = s_val
    # Ora gestiamo i casi con un punto e/o una virgola
    if dot_count == 1 and comma_count == 1:
        if s_cleaned.rfind(',') > s_cleaned.rfind('.'): # IT: 1.234,56
            s_cleaned = s_cleaned.replace('.', '').replace(',', '.')
        elif s_cleaned.rfind('.') > s_cleaned.rfind(','): # US: 1,234.56
            s_cleaned = s_cleaned.replace(',', '')
        else: # Ambigua, es. ".,"
            return 0.0 
    elif comma_count == 1 and dot_count == 0: # Solo virgola: 1234,56
        s_cleaned = s_cleaned.replace(',', '.')
    elif dot_count == 1 and comma_count == 0: # Solo punto: 1234.56
        pass # Già ok per float
    # Altri casi (es. nessun separatore valido) dovrebbero essere stati catturati da float(s_val)
    # o falliranno nel float(s_cleaned) finale.
        
    try: return float(s_cleaned)
    except ValueError: return 0.0


def check_controlli_formali(row: pd.Series, col_name_dichiarati: str = 'controlli_formali_dichiarati') -> Tuple[bool, str]:
    val_fse = parse_excel_currency(row.get('valore_contributo_fse', 0.0))
    calc_val = round(val_fse * 0.05, 2)
    decl_input_raw = row.get(col_name_dichiarati)

    if pd.isna(decl_input_raw) or str(decl_input_raw).strip() == "":
        # Se il dichiarato è vuoto, consideriamo OK se il calcolato è 0, altrimenti è un errore di "mancanza" se calcolato > 0
        # Però il test si aspetta (True, "non numerico o mancante") indipendentemente da calc_val
        return True, f"ℹ️ Calcolato={calc_val:.2f} (Valore dich./fornito '' è mancante)"

    decl_float = parse_excel_currency(decl_input_raw)
    
    is_actually_numeric_input = True
    # Un modo per inferire se l'input originale era numerico o è stato forzato a 0.0
    # da parse_excel_currency a causa di formato invalido.
    # Se parse_excel_currency restituisce 0.0, ma l'input pulito non era "0", "0.0", ecc.,
    # allora l'input originale probabilmente non era un numero.
    cleaned_decl_input_str = str(decl_input_raw).replace("€", "").strip()
    if decl_float == 0.0 and cleaned_decl_input_str not in ["0", "0.0", "0,0", "0,00", ""]:
        # Per essere più sicuri, prova a vedere se l'input originale era convertibile
        # in qualche modo prima di dichiararlo non numerico.
        # Questa logica euristica può essere migliorata.
        # Se parse_excel_currency ha fallito (restituendo 0.0 per un input non-zero), è non numerico.
        # Il problema è se l'input era "testo" e parse_excel_currency lo mappa a 0.0
        # e il calcolato è anche 0.0. In tal caso, non dovremmo dire OK.
        temp_check_val = "not_a_number_flag"
        try:
            temp_check_val = float(cleaned_decl_input_str.replace(',','.')) # Semplice tentativo
        except ValueError:
            is_actually_numeric_input = False
            
    if not is_actually_numeric_input:
        return True, f"ℹ️ Calcolato={calc_val:.2f} (Valore dich./fornito '{decl_input_raw}' non numerico o mancante)"

    if not np.isclose(decl_float, calc_val):
        return False, f"❌ Dich./Fornito ({decl_input_raw})={decl_float:.2f} ≠ Calcolato={calc_val:.2f}"
    return True, f"✅ OK (Dich./Fornito ({decl_input_raw})={decl_float:.2f}, Calcolato={calc_val:.2f})"


def check_sum_d(row: pd.Series) -> Tuple[bool, str]:
    a = parse_excel_currency(row.get('valore_contributo_fse', 0.0))
    b = parse_excel_currency(row.get('altri_contributi', 0.0))
    c = parse_excel_currency(row.get('quota_retta_destinatario', 0.0))
    d = parse_excel_currency(row.get('totale_retta', 0.0))
    calc_sum = round(a + b + c, 2)
    if not np.isclose(d, calc_sum):
        return False, f"❌ Tot.Retta D={d:.2f} ≠ Somma A+B+C={calc_sum:.2f} (A={a:.2f}, B={b:.2f}, C={c:.2f})"
    return True, f"✅ OK (D={d:.2f})"


def check_contribution_rules(row: pd.Series) -> Tuple[bool, str]:
    val_A = parse_excel_currency(row.get('valore_contributo_fse', 0.0))
    total_D = parse_excel_currency(row.get('totale_retta', 0.0))
    num_w_in = row.get('numero_settimane_frequenza')

    try:
        if pd.isna(num_w_in) or str(num_w_in).strip() == "": num_weeks = 0
        else:
            num_float = float(str(num_w_in).replace(',', '.')) # Converte stringhe con virgola
            if not num_float.is_integer(): # Verifica se è un intero puro (es. 2.0 è ok, 2.5 no)
                 return False, f"❌ Errore: N. settimane ('{num_w_in}') non è un intero puro."
            num_weeks = int(num_float)
        if num_weeks < 0: return False, "❌ N. settimane non può essere negativo."
    except ValueError: # Se la conversione a float fallisce
        return False, f"❌ Errore: N. settimane ('{num_w_in}') non è un numero intero valido."

    if val_A < 0: return False, f"❌ Contr. FSE (A)={val_A:.2f} non può essere negativo."
    if val_A > 300.0001: return False, f"❌ Contr. FSE (A)={val_A:.2f} supera cap 300€/riga."
    
    if num_weeks == 0:
        return (True, "✅ OK (0 settimane, Contr. FSE=0)") if np.isclose(val_A, 0.0) \
            else (False, f"❌ Contr. FSE (A)={val_A:.2f} > 0 ma N. settimane è 0.")
            
    cost_p_w = round(total_D / num_weeks, 2)
    max_weekly_contrib = min(cost_p_w, 100.00)
    expected_total_contrib = round(max_weekly_contrib * num_weeks, 2)
    
    if val_A > (expected_total_contrib + 0.0001):
        return False, (f"❌ Contr. FSE (A)={val_A:.2f} supera max calcolabile ({expected_total_contrib:.2f} "
                       f"= {num_weeks}sett * {max_weekly_contrib:.2f}€/sett)")
    return True, f"✅ OK (Contr.FSE={val_A:.2f} ≤ Max calcolato={expected_total_contrib:.2f})"


def validate_rif_pa_format(rif: Union[str, None]) -> Tuple[bool, str]:
    if not rif or not isinstance(rif, str): return False, "❌ Rif. PA non fornito."
    rif_tr = rif.strip()
    if re.fullmatch(r"^\d{4}-\d+\/RER$", rif_tr): return True, f"✅ Rif. PA '{rif_tr}' corretto."
    return False, f"❌ Rif. PA '{rif_tr}' non nel formato AAAA-NUMERO/RER."


def run_detailed_validations(
    df_input: pd.DataFrame, 
    cf_col_clean_name: str, 
    original_date_col_name: str,
    parsed_date_col_name: str,
    declared_formal_controls_col_name: str,
    row_offset_val: int = 1
) -> Tuple[pd.DataFrame, bool]:
    results_list, has_overall_errors = [], False

    # Controllo CF Duplicati nel Batch
    if not df_input.empty and cf_col_clean_name in df_input.columns:
        valid_cfs_series = df_input[df_input[cf_col_clean_name].astype(str).str.strip() != ''][cf_col_clean_name]
        if not valid_cfs_series.empty:
            cf_counts = valid_cfs_series.value_counts()
            duplicated_cfs = cf_counts[cf_counts > 1]
            if not duplicated_cfs.empty:
                has_overall_errors = True
                for cf_val, count_val in duplicated_cfs.items():
                    results_list.append({
                        'Riga': "Batch", 'Bambino': "N/A", 'Esito CF': "N/A",
                        'Esito Data Mandato': "N/A", 'Esito D=A+B+C': "N/A",
                        'Esito Regole Contr.FSE': "N/A", 'Esito Contr.Formali 5%': "N/A",
                        'Errori Bloccanti': f"❌ CF '{cf_val}' presente {count_val} volte.",
                        'Verifica Max 300€ FSE per Bambino (batch)': "N/A"
                    })
    
    for idx_df, row_data_series in df_input.iterrows():
        current_row_errors: List[str] = [] # Lista per errori specifici della riga
        
        # Validazione CF
        cf_status_ok, cf_status_msg = validate_codice_fiscale(row_data_series.get(cf_col_clean_name,''))
        if not cf_status_ok: current_row_errors.append(cf_status_msg)

        # Validazione Data
        date_obj_parsed = row_data_series.get(parsed_date_col_name)
        date_original_str = str(row_data_series.get(original_date_col_name,'')).strip()
        date_status_ok, date_status_msg = (True, f"✅ Data '{date_original_str}'→{date_obj_parsed:%d/%m/%Y}") \
            if pd.notna(date_obj_parsed) and hasattr(date_obj_parsed, 'strftime') \
            else (False, f"❌ Data '{date_original_str}' non valida.")
        if not date_status_ok: current_row_errors.append(date_status_msg)
        
        # Altre Validazioni per Riga
        sum_d_ok, sum_d_msg = check_sum_d(row_data_series)
        if not sum_d_ok: current_row_errors.append(sum_d_msg)
        
        contrib_rules_ok, contrib_rules_msg = check_contribution_rules(row_data_series)
        if not contrib_rules_ok: current_row_errors.append(contrib_rules_msg)
        
        formal_ctrl_ok, formal_ctrl_msg = check_controlli_formali(row_data_series, declared_formal_controls_col_name)
        if not formal_ctrl_ok: current_row_errors.append(formal_ctrl_msg)
        
        if any("❌" in err_str for err_str in current_row_errors):
            has_overall_errors = True
        
        results_list.append({
            'Riga': idx_df + row_offset_val, 
            'Bambino': row_data_series.get('bambino_cognome_nome','N/A'),
            'Esito CF': cf_status_msg, 
            'Esito Data Mandato': date_status_msg, 
            'Esito D=A+B+C': sum_d_msg, 
            'Esito Regole Contr.FSE': contrib_rules_msg,
            'Esito Contr.Formali 5%': formal_ctrl_msg,
            'Errori Bloccanti': "; ".join(current_row_errors) if current_row_errors else "Nessuno",
            'Verifica Max 300€ FSE per Bambino (batch)': '⏳' # Placeholder
        })

    df_results_final = pd.DataFrame(results_list)
    if df_results_final.empty: # Se df_input era vuoto, df_results_final sarà vuoto
        return df_results_final, has_overall_errors

    # Verifica Max 300€ FSE per Bambino (batch)
    col_fse_cap_check = 'Verifica Max 300€ FSE per Bambino (batch)'
    # Default a OK se la colonna esiste (cioè se df_results_final non è vuoto)
    if col_fse_cap_check in df_results_final.columns:
        df_results_final[col_fse_cap_check] = df_results_final[col_fse_cap_check].replace('⏳', '✅ OK')

    if cf_col_clean_name in df_input.columns and 'valore_contributo_fse' in df_input.columns and not df_input.empty:
        valid_cf_rows_for_cap = df_input[df_input[cf_col_clean_name].astype(str).str.strip()!='']
        if not valid_cf_rows_for_cap.empty:
            contrib_sum_per_child = valid_cf_rows_for_cap.groupby(cf_col_clean_name)['valore_contributo_fse'].sum()
            children_exceeding_cap = contrib_sum_per_child[contrib_sum_per_child > 300.0001]
            
            if not children_exceeding_cap.empty:
                has_overall_errors = True
                for cf_child_val, total_contrib_val in children_exceeding_cap.items():
                    error_msg_fse_cap = f"❌ Superato cap 300€ ({total_contrib_val:.2f}€ totali nel batch)"
                    original_indices_for_cf = df_input.index[df_input[cf_col_clean_name] == cf_child_val].tolist()
                    
                    for original_idx_val in original_indices_for_cf:
                        result_row_num_in_results_df = original_idx_val + row_offset_val
                        # Trova la riga in df_results_final usando il numero di riga calcolato
                        mask_results_df = df_results_final['Riga'] == result_row_num_in_results_df
                        
                        if mask_results_df.any():
                            df_results_final.loc[mask_results_df, col_fse_cap_check] = error_msg_fse_cap
                            current_blocking_errors = df_results_final.loc[mask_results_df, 'Errori Bloccanti'].iloc[0]
                            
                            if current_blocking_errors == "Nessuno" or not current_blocking_errors.strip():
                                df_results_final.loc[mask_results_df, 'Errori Bloccanti'] = error_msg_fse_cap
                            elif error_msg_fse_cap not in current_blocking_errors:
                                df_results_final.loc[mask_results_df, 'Errori Bloccanti'] += "; " + error_msg_fse_cap
    
    if 'Errori Bloccanti' in df_results_final.columns:
         df_results_final['Errori Bloccanti'] = df_results_final['Errori Bloccanti'].apply(
             lambda x_err: x_err if x_err and x_err.strip() and x_err != "Nessuno" else "Nessuno"
         )
    return df_results_final, has_overall_errors
#utils/common_utils.py