# Résumé des tests - Google Family Link

## Fichiers créés

```
HAFamilyLink/
├── pytest.ini                          # Configuration pytest
├── TESTING.md                          # Guide complet de test
└── tests/
    ├── __init__.py                     # Initialisation du package
    ├── conftest.py                     # Fixtures partagées
    ├── README.md                       # Documentation des tests
    ├── API_RESPONSE_EXAMPLES.md        # Exemples de réponses API
    └── test_api_parsing.py             # Tests de parsing (482 lignes)
```

## Tests implémentés (test_api_parsing.py)

### Total : 11 tests unitaires

#### Tests async_get_time_limit (4 tests)
1. ✓ `test_get_time_limit_all_enabled` - Bedtime + School time activés
2. ✓ `test_get_time_limit_bedtime_disabled` - Bedtime désactivé (stateFlag=1)
3. ✓ `test_get_time_limit_school_time_disabled` - School time désactivé (stateFlag=1)
4. ✓ `test_empty_response_handling` - Réponses vides

#### Tests async_get_applied_time_limits (3 tests)
5. ✓ `test_get_applied_time_limits_daily_enabled` - Daily limit activé avec minutes
6. ✓ `test_get_applied_time_limits_daily_disabled` - Daily limit désactivé (stateFlag=1)
7. ✓ `test_device_lock_states_parsing` - États de verrouillage

#### Tests combinés et edge cases (4 tests)
8. ✓ `test_combined_all_enabled` - Tous les contrôles activés
9. ✓ `test_empty_response_handling` - Gestion des réponses vides
10. ✓ `test_missing_state_flags` - Gestion des données incomplètes
11. ✓ `test_device_lock_states_parsing` - Parsing lock/unlock

## Scénarios couverts

### Scénario 1 : Tout activé ✓
- bedtime_enabled = True (stateFlag=2)
- school_time_enabled = True (stateFlag=2)
- daily_limit_enabled = True (stateFlag=2)
- daily_limit_minutes = 120

### Scénario 2 : Bedtime désactivé ✓
- bedtime_enabled = False (stateFlag=1)
- school_time_enabled = True
- bedtime_schedule peut être présent ou vide

### Scénario 3 : School time désactivé ✓
- bedtime_enabled = True
- school_time_enabled = False (stateFlag=1)
- school_time_schedule peut être présent ou vide

### Scénario 4 : Daily limit désactivé ✓
- daily_limit_enabled = False (stateFlag=1)
- daily_limit_minutes conserve la valeur (config sauvegardée)

## Fixtures mock

### Mock responses pour timeLimit
- `mock_time_limit_all_enabled` - Tout activé
- `mock_time_limit_bedtime_disabled` - Bedtime OFF
- `mock_time_limit_school_time_disabled` - School time OFF

### Mock responses pour appliedTimeLimits
- `mock_applied_time_limits_all_enabled` - Daily limit ON
- `mock_applied_time_limits_daily_disabled` - Daily limit OFF

### Fixtures utilitaires
- `mock_hass` - Mock Home Assistant
- `mock_config` - Mock configuration
- `client` - Client FamilyLinkClient configuré

## Assertions principales

### Pour async_get_time_limit
```python
assert result["bedtime_enabled"] is True/False
assert result["school_time_enabled"] is True/False
assert isinstance(result["bedtime_schedule"], list)
assert isinstance(result["school_time_schedule"], list)
```

### Pour async_get_applied_time_limits
```python
assert device_info["daily_limit_enabled"] is True/False
assert device_info["daily_limit_minutes"] == 120
assert device_info["total_allowed_minutes"] == 120
assert device_info["used_minutes"] == 60
assert device_info["remaining_minutes"] == 60
```

## Exécution des tests

### Installation
```bash
pip install -r requirements-dev.txt
```

### Lancer tous les tests
```bash
pytest tests/test_api_parsing.py -v
```

### Lancer un test spécifique
```bash
pytest tests/test_api_parsing.py::test_get_time_limit_all_enabled -v
```

### Avec couverture
```bash
pytest tests/test_api_parsing.py --cov=custom_components.familylink.client.api --cov-report=html
```

## Structure des mock responses

### Format timeLimit (bedtime/school_time)
```python
[
    # Schedule entries
    ["CAEQBiABKgQIEhABMgQIABAAOAE", day, [start_h, start_m], [end_h, end_m], None],
    
    # Revision entries (état ON/OFF)
    ["uuid", type_flag, state_flag, "timestamp"]
    # type_flag: 1=bedtime, 2=school_time
    # state_flag: 2=ON, 1=OFF
]
```

### Format appliedTimeLimits (daily_limit)
```python
[
    None,
    [  # Devices
        [
            [None, None, action_code, device_id],  # Lock state
            "total_ms",    # Total allowed (ms)
            "used_ms",     # Used (ms)
            ...,
            ["CAEQBg", day, state_flag, minutes, None],  # Daily limit
            ...,
            device_id
        ]
    ]
]
```

## Flags de référence

| Flag | Signification |
|------|---------------|
| stateFlag=2 | Activé (ON) |
| stateFlag=1 | Désactivé (OFF) |
| type_flag=1 | Bedtime |
| type_flag=2 | School time |
| action_code=1 | Locked |
| action_code=4 | Unlocked |

## Documentation

- **README.md** - Documentation complète des tests
- **API_RESPONSE_EXAMPLES.md** - Exemples réels de réponses API
- **TESTING.md** (racine) - Guide général de test du projet
- **SUMMARY.md** - Ce fichier (récapitulatif)

## Prochaines étapes

### Tests à ajouter (optionnel)
1. Tests d'intégration avec API réelle
2. Tests des autres méthodes du client (block_app, unlock_device, etc.)
3. Tests des sensors et switches Home Assistant
4. Tests de gestion d'erreurs (network errors, auth errors)

### Améliorations possibles
1. Fixtures paramétrées pour tester plusieurs scénarios
2. Tests de performance (temps de parsing)
3. Tests de régression avec captures réelles
4. Mock server pour tests d'intégration
