"""File-based storage for cookies with encryption."""
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from cryptography.fernet import Fernet
import logging

_LOGGER = logging.getLogger(__name__)


class SharedStorage:
    """Manages cookie storage in Home Assistant shared directory."""

    def __init__(self, share_dir: str = "/share/familylink"):
        """Initialize storage manager."""
        self.share_dir = Path(share_dir)
        self.storage_path = self.share_dir / "cookies.enc"
        self.key_file = self.share_dir / ".key"
        self._encryption_key = self._get_encryption_key()

        # Ensure directory exists
        self.share_dir.mkdir(parents=True, exist_ok=True)
        os.chmod(self.share_dir, 0o700)

    def _get_encryption_key(self) -> bytes:
        """Get or create encryption key."""
        if self.key_file.exists():
            with open(self.key_file, "rb") as f:
                return f.read()

        # Generate new key
        key = Fernet.generate_key()
        self.key_file.write_bytes(key)
        os.chmod(self.key_file, 0o600)

        _LOGGER.info("Generated new encryption key")
        return key

    async def save_cookies(self, cookies: List[Dict[str, Any]]) -> None:
        """Save cookies to encrypted file."""
        try:
            # Prepare data
            data = {
                "cookies": cookies,
                "timestamp": datetime.utcnow().isoformat(),
                "version": "1.0"
            }

            # Encrypt
            fernet = Fernet(self._encryption_key)
            json_data = json.dumps(data, indent=2)
            encrypted = fernet.encrypt(json_data.encode())

            # Write atomically
            temp_file = self.storage_path.with_suffix('.tmp')
            temp_file.write_bytes(encrypted)
            temp_file.rename(self.storage_path)

            # Set restrictive permissions
            os.chmod(self.storage_path, 0o600)

            _LOGGER.info(f"Saved {len(cookies)} cookies to shared storage")

        except Exception as e:
            _LOGGER.error(f"Failed to save cookies: {e}")
            raise

    async def load_cookies(self) -> List[Dict[str, Any]]:
        """Load cookies from encrypted file."""
        if not self.storage_path.exists():
            raise FileNotFoundError("No cookies found")

        try:
            # Read and decrypt
            encrypted = self.storage_path.read_bytes()
            fernet = Fernet(self._encryption_key)
            decrypted = fernet.decrypt(encrypted)

            # Parse
            data = json.loads(decrypted.decode())
            cookies = data.get("cookies", [])

            _LOGGER.info(f"Loaded {len(cookies)} cookies from shared storage")
            return cookies

        except Exception as e:
            _LOGGER.error(f"Failed to load cookies: {e}")
            raise

    async def clear_cookies(self) -> None:
        """Remove stored cookies."""
        if self.storage_path.exists():
            self.storage_path.unlink()
            _LOGGER.info("Cleared stored cookies")

    async def check_exists(self) -> bool:
        """Check if cookies exist."""
        return self.storage_path.exists()
