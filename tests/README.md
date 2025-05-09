# Test per l'Applicazione Centri Estivi

Questa cartella contiene una sequenza completa di test per l'applicazione Centri Estivi utilizzando pytest.

## Struttura dei Test

I test sono organizzati nei seguenti file:

- `conftest.py`: Contiene fixture comuni utilizzate in tutti i test
- `test_common_utils.py`: Test per le funzioni di validazione e utilità in `common_utils.py`
- `test_utils.py`: Test per le funzioni di utilità generali e autenticazione
- `test_db.py`: Test per le funzioni di database

## Prerequisiti

Per eseguire i test, è necessario installare pytest e altre dipendenze:

```bash
pip install pytest pytest-cov
```

## Esecuzione dei Test

Per eseguire tutti i test:

```bash
pytest
```

Per eseguire un file di test specifico:

```bash
pytest tests/test_common_utils.py
```

Per eseguire un test specifico:

```bash
pytest tests/test_common_utils.py::test_validate_codice_fiscale_valid
```

## Generazione Report di Copertura

Per generare un report di copertura dei test:

```bash
pytest --cov=utils tests/
```

Per un report dettagliato in HTML:

```bash
pytest --cov=utils --cov-report=html tests/
```

Il report HTML sarà disponibile nella cartella `htmlcov`.

## Aggiungere Nuovi Test

Per aggiungere nuovi test:

1. Creare un nuovo file di test con il prefisso `test_` (es. `test_nuovo_modulo.py`)
2. Implementare funzioni di test con il prefisso `test_` (es. `def test_nuova_funzionalita():`) 
3. Utilizzare le fixture esistenti in `conftest.py` o crearne di nuove

## Note sui Mock

Alcuni test utilizzano mock per simulare componenti esterni come il database. Questo permette di testare le funzioni senza dipendere da risorse esterne.

Esempio di utilizzo di mock:

```python
from unittest.mock import patch, MagicMock

def test_funzione_con_mock():
    with patch('modulo.funzione_da_mockare', return_value='valore_mock'):
        # Test con il mock
        assert funzione_da_testare() == 'risultato_atteso'
```