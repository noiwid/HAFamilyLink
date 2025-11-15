# Guide de test - Google Family Link Integration

Ce document décrit les tests unitaires et d'intégration pour l'intégration Google Family Link.

## Installation

### Dépendances de test

```bash
pip install -r requirements-dev.txt
```

Les dépendances incluent :
- `pytest` : Framework de test
- `pytest-asyncio` : Support des tests asynchrones
- `pytest-mock` : Mocking avancé
- `pytest-cov` : Couverture de code
- `pytest-homeassistant-custom-component` : Utilitaires pour composants HA

## Exécution des tests

### Tous les tests
```bash
pytest
```

### Tests spécifiques
```bash
# Tests de parsing API
pytest tests/test_api_parsing.py

# Tests avec verbose
pytest -v

# Tests avec couverture
pytest --cov=custom_components.familylink --cov-report=html
```

### Tests par marker
```bash
# Tests unitaires uniquement (avec mocks)
pytest -m unit

# Tests d'intégration (nécessite accès API réel)
pytest -m integration
```

## Structure des tests

```
tests/
├── __init__.py              # Initialisation du package de tests
├── conftest.py              # Fixtures partagées et configuration
├── README.md                # Documentation des tests
└── test_api_parsing.py      # Tests de parsing des endpoints
```

## Tests de parsing API (`test_api_parsing.py`)

### Objectif

Valider le parsing des réponses des endpoints Google Family Link pour la gestion du temps.

### Endpoints testés

1. **`async_get_time_limit`**
   - Parse bedtime_enabled et school_time_enabled
   - Basé sur `type_flag` et `state_flag` dans les révisions

2. **`async_get_applied_time_limits`**
   - Parse daily_limit_enabled
   - Basé sur tuples CAEQBg avec `state_flag`

### Scénarios de test

#### 1. Tout activé
- `test_get_time_limit_all_enabled` : Bedtime + School time activés
- `test_get_applied_time_limits_daily_enabled` : Daily limit activé avec minutes

**Données testées :**
```python
# timeLimit response
["487088e7-38b4-4f18-a5fb-4aab64ba9d2f", 1, 2, "timestamp"]  # bedtime ON
["579e5e01-8dfd-42f3-be6b-d77984842202", 2, 2, "timestamp"]  # school ON

# appliedTimeLimits response
["CAEQBg", 1, 2, 120, None]  # daily_limit ON, 120 minutes
```

**Assertions :**
- `bedtime_enabled == True`
- `school_time_enabled == True`
- `daily_limit_enabled == True`
- `daily_limit_minutes == 120`

#### 2. Bedtime désactivé
- `test_get_time_limit_bedtime_disabled`

**Données testées :**
```python
["487088e7-38b4-4f18-a5fb-4aab64ba9d2f", 1, 1, "timestamp"]  # bedtime OFF (stateFlag=1)
["579e5e01-8dfd-42f3-be6b-d77984842202", 2, 2, "timestamp"]  # school ON
```

**Assertions :**
- `bedtime_enabled == False`
- `school_time_enabled == True`
- `bedtime_schedule` peut être présent ou vide

#### 3. School time désactivé
- `test_get_time_limit_school_time_disabled`

**Données testées :**
```python
["487088e7-38b4-4f18-a5fb-4aab64ba9d2f", 1, 2, "timestamp"]  # bedtime ON
["579e5e01-8dfd-42f3-be6b-d77984842202", 2, 1, "timestamp"]  # school OFF (stateFlag=1)
```

**Assertions :**
- `bedtime_enabled == True`
- `school_time_enabled == False`

#### 4. Daily limit désactivé
- `test_get_applied_time_limits_daily_disabled`

**Données testées :**
```python
["CAEQBg", 1, 1, 120, None]  # daily_limit OFF (stateFlag=1)
```

**Assertions :**
- `daily_limit_enabled == False`
- `daily_limit_minutes == 120` (valeur sauvegardée)

#### 5. Tests combinés et edge cases
- `test_combined_all_enabled` : Tous les contrôles activés
- `test_empty_response_handling` : Réponses vides
- `test_missing_state_flags` : Données incomplètes
- `test_device_lock_states_parsing` : États de verrouillage

## Format des données API

### Flags de statut

| Flag | Signification |
|------|---------------|
| `stateFlag=2` | Activé (ON) |
| `stateFlag=1` | Désactivé (OFF) |
| `type_flag=1` | Bedtime/Downtime |
| `type_flag=2` | School time |
| `action_code=1` | Device locked |
| `action_code=4` | Device unlocked |

### Structure `timeLimit`

```python
[
    # Schedules (CAEQ* = bedtime, CAMQ* = school_time)
    ["CAEQBiABKgQIEhABMgQIABAAOAE", day, [start_h, start_m], [end_h, end_m], None],

    # Revisions (état ON/OFF)
    ["uuid", type_flag, state_flag, "timestamp"]
]
```

### Structure `appliedTimeLimits`

```python
[
    None,
    [  # Devices
        [
            [None, None, action_code, device_id],  # Lock state
            "total_ms",    # Total allowed (millisecondes)
            "used_ms",     # Utilisé (millisecondes)
            ...,
            ["CAEQBg", day, state_flag, minutes, None],  # Daily limit
            ...,
            device_id
        ]
    ]
]
```

## Ajouter de nouveaux tests

### Template de test

```python
@pytest.fixture
def mock_new_scenario():
    """Description du scénario."""
    return [
        # Vos données mock ici
    ]

@pytest.mark.asyncio
async def test_new_scenario(client, mock_new_scenario):
    """Description du test."""
    with patch.object(client, '_get_session') as mock_session:
        # Setup mock response
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value=mock_new_scenario)
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock()

        mock_session_instance = AsyncMock()
        mock_session_instance.get = MagicMock(return_value=mock_response)
        mock_session.return_value = mock_session_instance

        # Execute
        result = await client.async_get_time_limit()

        # Assert
        assert result["bedtime_enabled"] is True
        assert result["school_time_enabled"] is False
```

### Bonnes pratiques

1. **Utiliser des données réelles** : Les mock responses doivent refléter la structure réelle de l'API
2. **Tester les edge cases** : Réponses vides, données manquantes, valeurs nulles
3. **Assertions claires** : Messages d'erreur explicites
4. **Documentation** : Commenter les scénarios complexes
5. **Isolation** : Chaque test doit être indépendant

## Couverture de code

### Générer un rapport de couverture

```bash
pytest --cov=custom_components.familylink --cov-report=html
```

Le rapport HTML sera disponible dans `htmlcov/index.html`.

### Objectifs de couverture

- **Parsing API** : 100% (critique pour la fiabilité)
- **Client API** : >90% (tests unitaires + mocks)
- **Services** : >80% (tests d'intégration)
- **Sensors** : >80% (tests unitaires)

## CI/CD

Les tests sont exécutés automatiquement via GitHub Actions sur :
- Push vers `main`
- Pull requests
- Tags de version

Configuration : `.github/workflows/test.yml`

## Debugging

### Activer les logs détaillés

```bash
pytest -v --log-cli-level=DEBUG
```

### Désactiver les warnings

```bash
pytest --disable-warnings
```

### Arrêter au premier échec

```bash
pytest -x
```

### Mode interactif (PDB)

```bash
pytest --pdb
```

## Ressources

- [Documentation pytest](https://docs.pytest.org/)
- [pytest-asyncio](https://pytest-asyncio.readthedocs.io/)
- [Home Assistant Testing](https://developers.home-assistant.io/docs/development_testing)
- [Google Family Link API Analysis](./GOOGLE_FAMILY_LINK_API_ANALYSIS.md)
