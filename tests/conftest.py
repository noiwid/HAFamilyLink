"""Configuration pytest pour les tests Google Family Link.

Ce fichier contient les fixtures partagées et la configuration pytest
utilisées dans tous les tests.
"""

import pytest
import sys
from pathlib import Path

# Ajouter le répertoire parent au PYTHONPATH pour importer custom_components
sys.path.insert(0, str(Path(__file__).parent.parent))


# Configuration pytest
def pytest_configure(config):
    """Configuration pytest."""
    config.addinivalue_line(
        "markers", "asyncio: mark test as async"
    )
