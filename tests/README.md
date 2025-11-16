# Tests unitaires - Google Family Link

Ce répertoire contient les tests unitaires pour l'intégration Google Family Link.

## Installation des dépendances de test

```bash
pip install -r requirements-dev.txt
```

## Exécution des tests

### Tous les tests
```bash
pytest tests/
```

### Tests spécifiques au parsing API
```bash
pytest tests/test_api_parsing.py -v
```

### Tests avec couverture
```bash
pytest tests/ --cov=custom_components.familylink --cov-report=html
```

## Structure des tests

### `test_api_parsing.py`

Tests de parsing des endpoints Family Link pour la gestion du temps :

#### Scénarios testés

1. **Tout activé** (`test_get_time_limit_all_enabled`, `test_get_applied_time_limits_daily_enabled`)
   - Bedtime activé (stateFlag=2)
   - School time activé (stateFlag=2)
   - Daily limit activé (stateFlag=2)

2. **Bedtime désactivé** (`test_get_time_limit_bedtime_disabled`)
   - stateFlag=1 pour bedtime
   - Vérifie que bedtime_enabled=False
   - Vérifie que le schedule peut être présent ou vide

3. **School time désactivé** (`test_get_time_limit_school_time_disabled`)
   - stateFlag=1 pour school_time
   - Vérifie que school_time_enabled=False

4. **Daily limit désactivé** (`test_get_applied_time_limits_daily_disabled`)
   - stateFlag=1 dans tuple CAEQBg
   - Vérifie que daily_limit_enabled=False

#### Tests combinés

- `test_combined_all_enabled` : Vérifie tous les contrôles activés ensemble
- `test_empty_response_handling` : Gestion des réponses vides
- `test_missing_state_flags` : Gestion des données incomplètes
- `test_device_lock_states_parsing` : Parsing des états de verrouillage

## Format des données API

### Endpoint `timeLimit`

```python
# Format de la réponse
[
    # Schedule entries (CAEQ* pour bedtime, CAMQ* pour school_time)
    ["CAEQBiABKgQIEhABMgQIABAAOAE", day, [start_hour, start_min], [end_hour, end_min], None],

    # Revision entries (état ON/OFF)
    # type_flag: 1=bedtime, 2=school_time
    # state_flag: 2=ON, 1=OFF
    ["uuid", type_flag, state_flag, "timestamp"]
]
```

### Endpoint `appliedTimeLimits`

```python
# Format de la réponse
[
    None,
    [  # Liste des devices
        [
            [None, None, action_code, device_id],  # Lock state
            "total_ms",  # Total allowed (ms)
            "used_ms",   # Used (ms)
            ...,
            ["CAEQBg", day, state_flag, minutes, None],  # Daily limit
            ...,
            device_id
        ]
    ]
]
```

### Flags importants

- `stateFlag=2` : Activé (ON)
- `stateFlag=1` : Désactivé (OFF)
- `action_code=1` : Device locked
- `action_code=4` : Device unlocked

## Ajout de nouveaux tests

Pour ajouter de nouveaux scénarios :

1. Créer une fixture avec la réponse mock dans le format API réel
2. Créer la fonction de test avec `@pytest.mark.asyncio`
3. Mocker la session HTTP avec `patch.object(client, '_get_session')`
4. Vérifier les assertions sur les valeurs parsées

Exemple :

```python
@pytest.fixture
def mock_new_scenario():
    return [
        # Vos données mock ici
    ]

@pytest.mark.asyncio
async def test_new_scenario(client, mock_new_scenario):
    with patch.object(client, '_get_session') as mock_session:
        # Setup mock
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value=mock_new_scenario)
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock()

        mock_session_instance = AsyncMock()
        mock_session_instance.get = MagicMock(return_value=mock_response)
        mock_session.return_value = mock_session_instance

        # Test
        result = await client.async_get_time_limit()

        # Assertions
        assert result["bedtime_enabled"] is True
```
