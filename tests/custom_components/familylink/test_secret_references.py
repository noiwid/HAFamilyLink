"""Guard user-facing integration files against URL credential regressions."""

from __future__ import annotations

import re
from pathlib import Path


QUERY_KEY_RECOMMENDATIONS = (
    re.compile(r"\?api_key=<(?:your-)?key>", re.IGNORECASE),
    re.compile(r"\b(?:append|add)\b[^\n]{0,80}\?api_key=", re.IGNORECASE),
)


def test_user_facing_integration_files_do_not_recommend_query_keys() -> None:
    """New users must be directed to the separate masked key field."""
    integration_root = (
        Path(__file__).resolve().parents[3] / "custom_components" / "familylink"
    )
    repository_root = integration_root.parents[1]
    paths = [
        repository_root / "INSTALL.md",
        repository_root / "DOCKER_STANDALONE.md",
        repository_root / "familylink-playwright" / "DOCS.md",
        repository_root / "familylink-playwright" / "app" / "main.py",
        repository_root / "familylink-playwright" / "docker-compose.standalone.yml",
        repository_root / "familylink-playwright" / "run-standalone.sh",
        integration_root / "strings.json",
        *sorted((integration_root / "translations").glob("*.json")),
    ]

    for path in paths:
        content = path.read_text()
        for pattern in QUERY_KEY_RECOMMENDATIONS:
            assert pattern.search(content) is None, (path, pattern.pattern)
