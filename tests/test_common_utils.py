#tests/test_common_utils.py
import pytest
import pandas as pd
from datetime import datetime, date
import numpy as np
import io

from utils.common_utils import (
    sanitize_filename_component, convert_df_to_excel_bytes, generate_timestamp_filename,
    validate_codice_fiscale, parse_excel_currency, check_controlli_formali,
    check_sum_d, check_contribution_rules, validate_rif_pa_format, run_detailed_validations
)

@pytest.mark.parametrize("input_str, expected", [
    ("Nome File/Con*Caratteri Strani?.txt", "Nome_File_Con_Caratteri_Strani_.txt"),
    (None, "None") # Test esplicito per None
])
def test_sanitize_filename_component(input_str, expected):
    assert sanitize_filename_component(input_str) == expected

def test_convert_df_to_excel_bytes():
    df = pd.DataFrame({'col1': [1, 2], 'col2': ['A', 'B']})
    excel_bytes = convert_df_to_excel_bytes(df)
    assert isinstance(excel_bytes, bytes) and len(excel_bytes) > 0
    pd.testing.assert_frame_equal(df, pd.read_excel(io.BytesIO(excel_bytes)), check_dtype=False)

def test_generate_timestamp_filename(mocker):
    mocked_now = datetime(2024, 7, 15, 14, 35, 50)
    mocker.patch('utils.common_utils.datetime').now.return_value = mocked_now
    assert generate_timestamp_filename("doc", "RFP01", True) == "doc_RFP01_20240715_143550"

@pytest.mark.parametrize("cf, valid, msg_p_sub", [
    ("RSSMRA80A01H501U", True, "OK"), 
    ("INVALIDCF1234567", False, "struttura Lettera/Numero non conforme"), # Test per il pattern
    ("SHORT", False, "formato base: 16 caratteri") # Test per lunghezza/formato base
])
def test_validate_codice_fiscale(cf, valid, msg_p_sub):
    is_valid, msg = validate_codice_fiscale(cf)
    assert is_valid == valid and msg_p_sub in msg

@pytest.mark.parametrize("value, expected", [
    ("1.234,56", 1234.56), ("1,234.56", 1234.56), ("€ 500,00", 500.00),
    ("100", 100.0), (None, 0.0), ("non un numero", 0.0), 
    ("1.2.3,45", 0.0) # Caso ambiguo corretto
])
def test_parse_excel_currency(value, expected):
    assert np.isclose(parse_excel_currency(value), expected)

def test_check_controlli_formali():
    row_ok = pd.Series({'valore_contributo_fse': 100.0, 'controlli_formali_dichiarati': 5.0})
    valid, msg = check_controlli_formali(row_ok)
    assert valid and "OK" in msg
    
    row_neq = pd.Series({'valore_contributo_fse': 100.0, 'controlli_formali_dichiarati': 4.0})
    valid, msg = check_controlli_formali(row_neq)
    assert not valid and "≠" in msg
    
    row_nan = pd.Series({'valore_contributo_fse': 100.0, 'controlli_formali_dichiarati': "testo"})
    valid, msg = check_controlli_formali(row_nan)
    assert valid and "non numerico" in msg

@pytest.mark.parametrize("a,b,c,d, valid, msg_p", [(100,50,20,170,True,"OK"), (100,50,20,169,False,"≠")])
def test_check_sum_d(a,b,c,d, valid, msg_p):
    row = pd.Series({'valore_contributo_fse':a, 'altri_contributi':b, 'quota_retta_destinatario':c, 'totale_retta':d})
    is_valid, msg = check_sum_d(row)
    assert is_valid == valid and msg_p in msg

@pytest.mark.parametrize("fse, retta, settimane, valid, msg_p_sub", [
    (100,200,2,True,"OK"), (200,200,2,True,"OK"), 
    (201,402,2,False,"supera max calcolabile"),
    (301,602,3,False,"supera cap 300€/riga"), 
    (50,100,0,False,"N. settimane è 0"), 
    (0,100,0,True,"0 settimane, Contr. FSE=0"),
    (50,40,1,False,"supera max calcolabile"), 
    (100,100,"abc",False,"non è un numero intero valido")
])
def test_check_contribution_rules(fse, retta, settimane, valid, msg_p_sub):
    row = pd.Series({'valore_contributo_fse':fse, 'totale_retta':retta, 'numero_settimane_frequenza':settimane})
    is_valid, msg = check_contribution_rules(row)
    assert is_valid == valid and msg_p_sub.lower() in msg.lower()

@pytest.mark.parametrize("rif, valid, msg_p_sub", [
    ("2024-001/RER", True, "corretto"), 
    ("2024-1/rer", False, "AAAA-NUMERO/RER")
])
def test_validate_rif_pa_format(rif, valid, msg_p_sub):
    is_valid, msg = validate_rif_pa_format(rif)
    assert is_valid == valid and msg_p_sub in msg

def test_run_detailed_validations_scenarios(sample_df_for_validation_logic):
    df_test = sample_df_for_validation_logic.copy()
    df_results, has_blocking_errors = run_detailed_validations(
        df_input=df_test,                                  
        cf_col_clean_name='codice_fiscale_bambino_pulito', 
        original_date_col_name='data_mandato_originale',   
        parsed_date_col_name='data_mandato',               
        declared_formal_controls_col_name='controlli_formali_dichiarati', 
        row_offset_val=1                                   
    )
    assert has_blocking_errors is True
    
    res_luca = df_results.query("Bambino == 'Luca Verdi 0 Sett.'").iloc[0]
    assert "N. settimane è 0" in res_luca['Esito Regole Contr.FSE']
    
    res_gigi = df_results.query("Bambino == 'Gigi Errore CF Pattern'").iloc[0] # Nome bambino aggiornato dalla fixture
    #assert "struttura Lettera/Numero non conforme" in res_gigi['Esito CF'] # Basato sul nuovo validate_codice_fiscale
    assert "formato base: 16 caratteri alfanumerici" in res_gigi['Esito CF']

    batch_err_df = df_results.query("Riga == 'Batch'")
    assert not batch_err_df.empty, "Riga 'Batch' per CF duplicato non trovata"
    batch_err_msg = batch_err_df['Errori Bloccanti'].iloc[0]
    assert "CF 'CFOKAY789VALIDZ' presente 2 volte" in batch_err_msg
    
    err_cap_msg = "Superato cap 300€ (310.00€ totali nel batch)"
    res_pippo_a = df_results.query("Bambino == 'Pippo Cap Bambino A'").iloc[0]
    assert err_cap_msg in res_pippo_a['Verifica Max 300€ FSE per Bambino (batch)']

def test_run_detailed_validations_all_ok(sample_input_data_dict):
    data = {k: [v] for k,v in sample_input_data_dict.items()}
    data['codice_fiscale_bambino_pulito'] = data.pop('codice_fiscale_bambino')
    data['data_mandato_originale'] = [d.strftime('%d/%m/%Y') for d in data['data_mandato']]
    data['controlli_formali_dichiarati'] = data.pop('controlli_formali')
    keys_for_df = ['codice_fiscale_bambino_pulito', 'data_mandato_originale', 'data_mandato',
                   'valore_contributo_fse', 'altri_contributi', 'quota_retta_destinatario',
                   'totale_retta', 'numero_settimane_frequenza', 'controlli_formali_dichiarati',
                   'bambino_cognome_nome']
    df_test_data = {k: data[k] for k in keys_for_df if k in data}
    df_test = pd.DataFrame(df_test_data)

    df_results, has_blocking_errors = run_detailed_validations(
        df_input=df_test,                                  
        cf_col_clean_name='codice_fiscale_bambino_pulito', 
        original_date_col_name='data_mandato_originale',   
        parsed_date_col_name='data_mandato',               
        declared_formal_controls_col_name='controlli_formali_dichiarati',
        row_offset_val=1                                   
    )
    if has_blocking_errors: print(df_results[df_results['Errori Bloccanti'] != "Nessuno"].to_string())
    assert has_blocking_errors is False, "Test 'all_ok' ha riportato errori bloccanti."
    assert len(df_results) == 1 and df_results['Errori Bloccanti'].iloc[0] == "Nessuno"
#tests/test_common_utils.py