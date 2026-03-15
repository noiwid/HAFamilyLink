"""UI translations for the auth add-on web interface."""

TRANSLATIONS = {
    "fr": {
        "html_lang": "fr",
        "title": "Google Family Link Authentication",
        "subtitle": "Service d'authentification pour l'int\u00e9gration Home Assistant",
        "start_auth": "D\u00e9marrer l'authentification",
        "instructions_title": "Instructions",
        "instruction_1": "Cliquez sur \"D\u00e9marrer l'authentification\"",
        "instruction_2": "Une fen\u00eatre de navigateur va s'ouvrir avec la page de connexion Google",
        "instruction_3": "Ouvrez le lien noVNC ci-dessous pour voir et interagir avec le navigateur",
        "instruction_4": "Connectez-vous avec votre compte Google",
        "instruction_5": "Compl\u00e9tez la validation en deux \u00e9tapes si demand\u00e9",
        "instruction_6": "Attendez le message de succ\u00e8s",
        "instruction_7": "Retournez dans Home Assistant pour terminer la configuration",
        "info_note": "Apr\u00e8s avoir cliqu\u00e9 sur le bouton, ouvrez le lien noVNC pour voir le navigateur et vous connecter \u00e0 Google.",
        "novnc_link_text": "Ouvrir noVNC (voir le navigateur)",
        "novnc_password_hint": "Mot de passe VNC : <code>familylink</code>",
        "starting": "D\u00e9marrage...",
        "waiting": "En attente de connexion...",
        "auth_starting": "D\u00e9marrage de l'authentification...",
        "browser_open": "Fen\u00eatre du navigateur ouverte. Veuillez vous connecter \u00e0 Google...",
        "start_failed": "\u00c9chec du d\u00e9marrage: ",
        "retry": "R\u00e9essayer",
        "auth_success": "Authentification r\u00e9ussie! {count} cookies sauvegard\u00e9s.\\n\\nVous pouvez maintenant terminer la configuration dans Home Assistant.",
        "auth_completed": "Authentification termin\u00e9e",
        "auth_timeout": "D\u00e9lai d'attente d\u00e9pass\u00e9. Veuillez r\u00e9essayer.",
        "retry_auth": "R\u00e9essayer l'authentification",
        "auth_error": "Erreur: ",
        "unknown_error": "Erreur inconnue",
        "cookies_exist": "Des cookies sont d\u00e9j\u00e0 enregistr\u00e9s. Vous pouvez configurer l'int\u00e9gration dans Home Assistant.",
        "start_error": "\u00c9chec du d\u00e9marrage de l'authentification",
    },
    "en": {
        "html_lang": "en",
        "title": "Google Family Link Authentication",
        "subtitle": "Authentication service for Home Assistant integration",
        "start_auth": "Start Authentication",
        "instructions_title": "Instructions",
        "instruction_1": "Click \"Start Authentication\"",
        "instruction_2": "A browser window will open with the Google login page",
        "instruction_3": "Open the noVNC link below to see and interact with the browser",
        "instruction_4": "Sign in with your Google account",
        "instruction_5": "Complete two-factor authentication if prompted",
        "instruction_6": "Wait for the success message",
        "instruction_7": "Return to Home Assistant to complete the configuration",
        "info_note": "After clicking the button, open the noVNC link to see the browser and sign in to Google.",
        "novnc_link_text": "Open noVNC (view browser)",
        "novnc_password_hint": "VNC password: <code>familylink</code>",
        "starting": "Starting...",
        "waiting": "Waiting for login...",
        "auth_starting": "Starting authentication...",
        "browser_open": "Browser window opened. Please sign in to Google...",
        "start_failed": "Failed to start: ",
        "retry": "Retry",
        "auth_success": "Authentication successful! {count} cookies saved.\\n\\nYou can now complete the configuration in Home Assistant.",
        "auth_completed": "Authentication completed",
        "auth_timeout": "Authentication timed out. Please try again.",
        "retry_auth": "Retry authentication",
        "auth_error": "Error: ",
        "unknown_error": "Unknown error",
        "cookies_exist": "Cookies are already saved. You can configure the integration in Home Assistant.",
        "start_error": "Failed to start authentication",
    },
}


def get_translations(language: str) -> dict:
    """Get translations for the given language code.

    Accepts full locale (fr-FR, en-US) or short code (fr, en).
    Falls back to English if language is not supported.
    """
    short = language.split("-")[0].lower() if language else "en"
    return TRANSLATIONS.get(short, TRANSLATIONS["en"])
