"""Tests unitaires pour le parsing des endpoints Family Link.

Ce fichier teste le parsing des réponses API pour les endpoints de gestion du temps :
- async_get_time_limit : bedtime_enabled, school_time_enabled
- async_get_applied_time_limits : daily_limit_enabled

Scénarios testés :
1. Tout activé (bedtime, school_time, daily_limit)
2. Bedtime désactivé (stateFlag=1)
3. School time désactivé (stateFlag=1)
4. Daily limit désactivé (stateFlag=1)
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from aiohttp import ClientSession

from custom_components.familylink.client.api import FamilyLinkClient


# ============================================================================
# FIXTURES - Mock Responses
# ============================================================================


@pytest.fixture
def mock_time_limit_all_enabled():
    """Réponse mock pour timeLimit avec bedtime ET school_time activés.

    Format réel de l'API :
    - type_flag=1 : bedtime/downtime
    - type_flag=2 : school_time
    - state_flag=2 : activé (ON)
    - state_flag=1 : désactivé (OFF)
    """
    return [
        # Bedtime schedule
        ["CAEQBiABKgQIEhABMgQIABAAOAE", 1, [20, 0], [7, 0], None],
        # School time schedule
        ["CAMQBiACKgQIEhABMgQIABAAOAE", 1, [17, 0], [20, 0], None],
        # Bedtime revision (type=1, state=2 = ON)
        ["487088e7-38b4-4f18-a5fb-4aab64ba9d2f", 1, 2, "1699999999999"],
        # School time revision (type=2, state=2 = ON)
        ["579e5e01-8dfd-42f3-be6b-d77984842202", 2, 2, "1699999999999"]
    ]


@pytest.fixture
def mock_time_limit_bedtime_disabled():
    """Réponse mock pour timeLimit avec bedtime DÉSACTIVÉ (stateFlag=1).

    Le bedtime_schedule peut être présent ou vide, mais bedtime_enabled=False
    car state_flag=1.
    """
    return [
        # Bedtime schedule (présent mais désactivé)
        ["CAEQBiABKgQIEhABMgQIABAAOAE", 1, [20, 0], [7, 0], None],
        # School time schedule
        ["CAMQBiACKgQIEhABMgQIABAAOAE", 1, [17, 0], [20, 0], None],
        # Bedtime revision (type=1, state=1 = OFF)
        ["487088e7-38b4-4f18-a5fb-4aab64ba9d2f", 1, 1, "1699999999999"],
        # School time revision (type=2, state=2 = ON)
        ["579e5e01-8dfd-42f3-be6b-d77984842202", 2, 2, "1699999999999"]
    ]


@pytest.fixture
def mock_time_limit_school_time_disabled():
    """Réponse mock pour timeLimit avec school_time DÉSACTIVÉ (stateFlag=1)."""
    return [
        # Bedtime schedule
        ["CAEQBiABKgQIEhABMgQIABAAOAE", 1, [20, 0], [7, 0], None],
        # School time schedule
        ["CAMQBiACKgQIEhABMgQIABAAOAE", 1, [17, 0], [20, 0], None],
        # Bedtime revision (type=1, state=2 = ON)
        ["487088e7-38b4-4f18-a5fb-4aab64ba9d2f", 1, 2, "1699999999999"],
        # School time revision (type=2, state=1 = OFF)
        ["579e5e01-8dfd-42f3-be6b-d77984842202", 2, 1, "1699999999999"]
    ]


@pytest.fixture
def mock_applied_time_limits_all_enabled():
    """Réponse mock pour appliedTimeLimits avec daily_limit activé.

    Format réel de l'API :
    - Index 1 : liste des devices
    - Chaque device contient des tuples CAEQBg pour le daily limit
    - state_flag=2 : daily_limit activé
    - state_flag=1 : daily_limit désactivé
    """
    return [
        None,  # Index 0
        [  # Index 1 : devices
            [
                # Device lock state
                [None, None, 4, "device123"],
                # Total allowed time (ms)
                "7200000",  # 120 minutes = 2 hours
                # Used time (ms)
                "3600000",  # 60 minutes = 1 hour
                None, None, None, None, None, None, None,
                # Daily limit tuple: ["CAEQBg", day, state_flag, minutes]
                # state_flag=2 signifie activé
                ["CAEQBg", 1, 2, 120, None],
                None, None, None, None, None, None, None, None, None, None, None, None,
                "device123"  # Index 25 : device ID
            ]
        ]
    ]


@pytest.fixture
def mock_applied_time_limits_daily_disabled():
    """Réponse mock pour appliedTimeLimits avec daily_limit DÉSACTIVÉ (stateFlag=1)."""
    return [
        None,  # Index 0
        [  # Index 1 : devices
            [
                # Device lock state
                [None, None, 4, "device123"],
                # Total allowed time (ms)
                "7200000",
                # Used time (ms)
                "3600000",
                None, None, None, None, None, None, None,
                # Daily limit tuple avec state_flag=1 (désactivé)
                ["CAEQBg", 1, 1, 120, None],
                None, None, None, None, None, None, None, None, None, None, None, None,
                "device123"
            ]
        ]
    ]


# ============================================================================
# FIXTURES - Client Setup
# ============================================================================


@pytest.fixture
def mock_hass():
    """Mock Home Assistant instance."""
    hass = MagicMock()
    return hass


@pytest.fixture
def mock_config():
    """Mock configuration."""
    return {
        "cookie_file": "/tmp/test_cookies.json"
    }


@pytest.fixture
async def client(mock_hass, mock_config):
    """Fixture pour créer un FamilyLinkClient mocké."""
    client = FamilyLinkClient(mock_hass, mock_config)

    # Mock authentication
    client._cookies = [
        {"name": "SAPISID", "value": "test_sapisid", "domain": ".google.com"}
    ]
    client._account_id = "test_child_123"

    yield client

    # Cleanup
    await client.async_cleanup()


# ============================================================================
# TESTS - async_get_time_limit (bedtime_enabled, school_time_enabled)
# ============================================================================


@pytest.mark.asyncio
async def test_get_time_limit_all_enabled(client, mock_time_limit_all_enabled):
    """Scénario 1 : Bedtime ET School time activés.

    Vérifie que :
    - bedtime_enabled = True (type_flag=1, state_flag=2)
    - school_time_enabled = True (type_flag=2, state_flag=2)
    """
    with patch.object(client, '_get_session') as mock_session:
        # Mock la réponse HTTP
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value=mock_time_limit_all_enabled)
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock()

        mock_session_instance = AsyncMock()
        mock_session_instance.get = MagicMock(return_value=mock_response)
        mock_session.return_value = mock_session_instance

        # Exécute la méthode
        result = await client.async_get_time_limit()

        # Assertions
        assert result["bedtime_enabled"] is True, "Bedtime devrait être activé (state_flag=2)"
        assert result["school_time_enabled"] is True, "School time devrait être activé (state_flag=2)"
        assert isinstance(result["bedtime_schedule"], list)
        assert isinstance(result["school_time_schedule"], list)


@pytest.mark.asyncio
async def test_get_time_limit_bedtime_disabled(client, mock_time_limit_bedtime_disabled):
    """Scénario 2 : Bedtime DÉSACTIVÉ (stateFlag=1).

    Vérifie que :
    - bedtime_enabled = False (type_flag=1, state_flag=1)
    - school_time_enabled = True (type_flag=2, state_flag=2)
    - bedtime_schedule peut exister même si désactivé
    """
    with patch.object(client, '_get_session') as mock_session:
        # Mock la réponse HTTP
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value=mock_time_limit_bedtime_disabled)
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock()

        mock_session_instance = AsyncMock()
        mock_session_instance.get = MagicMock(return_value=mock_response)
        mock_session.return_value = mock_session_instance

        # Exécute la méthode
        result = await client.async_get_time_limit()

        # Assertions
        assert result["bedtime_enabled"] is False, "Bedtime devrait être désactivé (state_flag=1)"
        assert result["school_time_enabled"] is True, "School time devrait être activé"
        # Le schedule peut être présent ou vide
        assert isinstance(result["bedtime_schedule"], list)


@pytest.mark.asyncio
async def test_get_time_limit_school_time_disabled(client, mock_time_limit_school_time_disabled):
    """Scénario 3 : School time DÉSACTIVÉ (stateFlag=1).

    Vérifie que :
    - bedtime_enabled = True (type_flag=1, state_flag=2)
    - school_time_enabled = False (type_flag=2, state_flag=1)
    """
    with patch.object(client, '_get_session') as mock_session:
        # Mock la réponse HTTP
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value=mock_time_limit_school_time_disabled)
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock()

        mock_session_instance = AsyncMock()
        mock_session_instance.get = MagicMock(return_value=mock_response)
        mock_session.return_value = mock_session_instance

        # Exécute la méthode
        result = await client.async_get_time_limit()

        # Assertions
        assert result["bedtime_enabled"] is True, "Bedtime devrait être activé"
        assert result["school_time_enabled"] is False, "School time devrait être désactivé (state_flag=1)"
        assert isinstance(result["school_time_schedule"], list)


# ============================================================================
# TESTS - async_get_applied_time_limits (daily_limit_enabled)
# ============================================================================


@pytest.mark.asyncio
async def test_get_applied_time_limits_daily_enabled(client, mock_applied_time_limits_all_enabled):
    """Scénario 1 : Daily limit activé avec minutes configurées.

    Vérifie que :
    - daily_limit_enabled = True (state_flag=2 dans tuple CAEQBg)
    - daily_limit_minutes contient la valeur configurée (120 minutes)
    - remaining_minutes est calculé correctement
    """
    with patch.object(client, '_get_session') as mock_session:
        # Mock la réponse HTTP
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value=mock_applied_time_limits_all_enabled)
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock()

        mock_session_instance = AsyncMock()
        mock_session_instance.get = MagicMock(return_value=mock_response)
        mock_session.return_value = mock_session_instance

        # Exécute la méthode
        result = await client.async_get_applied_time_limits()

        # Assertions
        assert "devices" in result
        assert "device123" in result["devices"]

        device_info = result["devices"]["device123"]
        assert device_info["daily_limit_enabled"] is True, "Daily limit devrait être activé (state_flag=2)"
        assert device_info["daily_limit_minutes"] == 120, "Daily limit devrait être 120 minutes"
        assert device_info["total_allowed_minutes"] == 120, "Total allowed devrait être 120 minutes (7200000ms)"
        assert device_info["used_minutes"] == 60, "Used minutes devrait être 60 (3600000ms)"
        assert device_info["remaining_minutes"] == 60, "Remaining devrait être 60 minutes (120 - 60)"


@pytest.mark.asyncio
async def test_get_applied_time_limits_daily_disabled(client, mock_applied_time_limits_daily_disabled):
    """Scénario 4 : Daily limit DÉSACTIVÉ (stateFlag=1).

    Vérifie que :
    - daily_limit_enabled = False (state_flag=1 dans tuple CAEQBg)
    - daily_limit_minutes peut toujours avoir une valeur (config sauvegardée)
    """
    with patch.object(client, '_get_session') as mock_session:
        # Mock la réponse HTTP
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value=mock_applied_time_limits_daily_disabled)
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock()

        mock_session_instance = AsyncMock()
        mock_session_instance.get = MagicMock(return_value=mock_response)
        mock_session.return_value = mock_session_instance

        # Exécute la méthode
        result = await client.async_get_applied_time_limits()

        # Assertions
        assert "devices" in result
        assert "device123" in result["devices"]

        device_info = result["devices"]["device123"]
        assert device_info["daily_limit_enabled"] is False, "Daily limit devrait être désactivé (state_flag=1)"
        # Les minutes peuvent être présentes même si désactivé (configuration sauvegardée)
        assert device_info["daily_limit_minutes"] == 120


# ============================================================================
# TESTS - Scénarios combinés
# ============================================================================


@pytest.mark.asyncio
async def test_combined_all_enabled(client, mock_time_limit_all_enabled, mock_applied_time_limits_all_enabled):
    """Test combiné : Tous les contrôles activés (bedtime, school_time, daily_limit).

    Ce test simule la situation réelle où un utilisateur a activé tous les contrôles
    de temps disponibles dans Google Family Link.
    """
    with patch.object(client, '_get_session') as mock_session:
        # Mock les deux endpoints
        mock_response_time_limit = AsyncMock()
        mock_response_time_limit.status = 200
        mock_response_time_limit.json = AsyncMock(return_value=mock_time_limit_all_enabled)
        mock_response_time_limit.__aenter__ = AsyncMock(return_value=mock_response_time_limit)
        mock_response_time_limit.__aexit__ = AsyncMock()

        mock_response_applied = AsyncMock()
        mock_response_applied.status = 200
        mock_response_applied.json = AsyncMock(return_value=mock_applied_time_limits_all_enabled)
        mock_response_applied.__aenter__ = AsyncMock(return_value=mock_response_applied)
        mock_response_applied.__aexit__ = AsyncMock()

        mock_session_instance = AsyncMock()
        # Le premier appel retourne timeLimit, le second appliedTimeLimits
        mock_session_instance.get = MagicMock(side_effect=[
            mock_response_time_limit,
            mock_response_applied
        ])
        mock_session.return_value = mock_session_instance

        # Exécute les deux méthodes
        time_limit_result = await client.async_get_time_limit()
        applied_result = await client.async_get_applied_time_limits()

        # Assertions combinées
        assert time_limit_result["bedtime_enabled"] is True
        assert time_limit_result["school_time_enabled"] is True
        assert applied_result["devices"]["device123"]["daily_limit_enabled"] is True

        # Vérification complète : tous les switches devraient être ON
        assert all([
            time_limit_result["bedtime_enabled"],
            time_limit_result["school_time_enabled"],
            applied_result["devices"]["device123"]["daily_limit_enabled"]
        ]), "Tous les contrôles de temps devraient être activés"


@pytest.mark.asyncio
async def test_empty_response_handling(client):
    """Test de gestion des réponses vides ou malformées.

    Vérifie que le parsing ne crash pas avec des données invalides.
    """
    with patch.object(client, '_get_session') as mock_session:
        # Mock réponse vide
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value=[])
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock()

        mock_session_instance = AsyncMock()
        mock_session_instance.get = MagicMock(return_value=mock_response)
        mock_session.return_value = mock_session_instance

        # Exécute la méthode
        result = await client.async_get_time_limit()

        # Assertions : devrait retourner des valeurs par défaut
        assert result["bedtime_enabled"] is False
        assert result["school_time_enabled"] is False
        assert result["bedtime_schedule"] == []
        assert result["school_time_schedule"] == []


# ============================================================================
# TESTS - Edge Cases
# ============================================================================


@pytest.mark.asyncio
async def test_missing_state_flags(client):
    """Test avec des state_flags manquants dans la réponse.

    Vérifie que le code gère correctement les données incomplètes.
    """
    # Mock réponse avec données incomplètes (pas de state_flag)
    incomplete_response = [
        ["487088e7-38b4-4f18-a5fb-4aab64ba9d2f", 1, None, "1699999999999"],  # state_flag=None
    ]

    with patch.object(client, '_get_session') as mock_session:
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value=incomplete_response)
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock()

        mock_session_instance = AsyncMock()
        mock_session_instance.get = MagicMock(return_value=mock_response)
        mock_session.return_value = mock_session_instance

        # Exécute la méthode
        result = await client.async_get_time_limit()

        # Assertions : devrait retourner False par défaut
        assert result["bedtime_enabled"] is False
        assert result["school_time_enabled"] is False


@pytest.mark.asyncio
async def test_device_lock_states_parsing(client, mock_applied_time_limits_all_enabled):
    """Test du parsing des états de verrouillage des devices.

    Vérifie que le parsing extrait correctement l'état locked/unlocked.
    action_code=1 : locked
    action_code=4 : unlocked
    """
    with patch.object(client, '_get_session') as mock_session:
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value=mock_applied_time_limits_all_enabled)
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock()

        mock_session_instance = AsyncMock()
        mock_session_instance.get = MagicMock(return_value=mock_response)
        mock_session.return_value = mock_session_instance

        # Exécute la méthode
        result = await client.async_get_applied_time_limits()

        # Assertions
        assert "device_lock_states" in result
        assert "device123" in result["device_lock_states"]
        # action_code=4 signifie unlocked (False)
        assert result["device_lock_states"]["device123"] is False
