#tests/conftest.py
import sys
import os

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import pytest
import sqlite3
import pandas as pd
from datetime import date, datetime 
from unittest.mock import patch

from utils import db as app_db

@pytest.fixture(scope="function")
def test_db_conn_engine():
    original_db_path = app_db.DATABASE_PATH
    app_db.DATABASE_PATH = ":memory:"
    with patch('utils.db.logger') as mock_db_logger_obj:
        conn = app_db.get_db_connection()
        app_db.init_db(conn) # Passa la connessione a init_db
        yield conn, mock_db_logger_obj # Fornisce conn e logger mockato
        conn.close()
    app_db.DATABASE_PATH = original_db_path

@pytest.fixture
def mock_uuid(mocker):
    mocked_uuid = mocker.patch('uuid.uuid4')
    mocked_uuid.return_value = "mocked-uuid-value-123"
    return mocked_uuid

@pytest.fixture
def sample_input_data_dict(): # Per testare inserimenti singoli e dati base
    return {
        'rif_pa': '2024-INPUT01/RER', 'cup': 'CUPINP01', 'distretto': 'DISTINP01',
        'comune_capofila': 'Capofila Input', 'numero_mandato': 'MANDINP01',
        'data_mandato': date(2024, 4, 15), 'comune_titolare_mandato': 'Titolare Input',
        'importo_mandato': 1200.0, 'comune_centro_estivo': 'Comune CE Input',
        'centro_estivo': 'CE Input', 'genitore_cognome_nome': 'Genitore Input Verdi',
        'bambino_cognome_nome': 'Bambino Input Verdi', 'codice_fiscale_bambino': 'VRDTST01A01H501A', # Valido
        'valore_contributo_fse': 180.0, 'altri_contributi': 20.0,
        'quota_retta_destinatario': 10.0, 'totale_retta': 210.0,
        'numero_settimane_frequenza': 2, # Deve essere int per check_contribution_rules
        'controlli_formali': 9.0,
    }

@pytest.fixture
def sample_df_for_validation_logic(): # Per testare run_detailed_validations
    return pd.DataFrame({
        'codice_fiscale_bambino_pulito': ["MRORSS80A01F205X", "VRDLCA80A01F205Y", "BNCLRD80A01F205Z", "INVALID!", "CFOKAY789VALIDZ", "CFOKAY789VALIDZ"], # "INVALID!" fallirà il pattern
        'data_mandato_originale':        ["01/01/2024",         "29/02/2024",         "15/05/2024",         "30/04/2024",       "11/11/2024",      "12/11/2024"],
        'data_mandato': [ date(2024,1,1),   date(2024,2,29),   date(2024,5,15), date(2024,4,30),  date(2024,11,11),  date(2024,11,12) ],
        'valore_contributo_fse':        [100.0,   150.0,   301.0,    50.0,  160.0,  150.0], # 301>cap riga; 160+150=310 > cap bambino
        'altri_contributi':             [0.0,     20.0,    10.0,     5.0,   10.0,    0.0],
        'quota_retta_destinatario':     [0.0,     30.0,    10.0,     5.0,   10.0,    0.0],
        'totale_retta':                 [100.0,   200.0,   321.0,    60.0,  180.0,  150.0],
        'numero_settimane_frequenza':   [1,       0,       3,        1,     2,      1], # int
        'controlli_formali_dichiarati': [5.0,     7.5,     15.05,    2.0,   8.0,   "non_valido"],
        'bambino_cognome_nome':         ['Mario Rossi Valid', 'Luca Verdi 0 Sett.', 'Clara Bianchi Cap Riga', 'Gigi Errore CF Pattern', 'Pippo Cap Bambino A', 'Pippo Cap Bambino B']
    })
#tests/conftest.py