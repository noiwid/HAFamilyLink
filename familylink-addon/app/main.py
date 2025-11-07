"""Main FastAPI application for Family Link Auth."""
import logging
import sys
from pathlib import Path

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from app.auth.browser import BrowserAuthManager
from app.storage.file_storage import SharedStorage
from app.config import get_config

# Configure logging
config = get_config()
logging.basicConfig(
    level=config.log_level.upper(),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)

_LOGGER = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="Google Family Link Auth Service",
    description="Authentication service for Google Family Link integration",
    version="1.0.0"
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global instances
storage = SharedStorage(config.share_dir)
browser_manager = None


@app.on_event("startup")
async def startup_event():
    """Initialize services on startup."""
    global browser_manager
    _LOGGER.info("Starting Family Link Auth Service v1.0.0")
    _LOGGER.info(f"Configuration: log_level={config.log_level}, auth_timeout={config.auth_timeout}s")

    try:
        browser_manager = BrowserAuthManager(auth_timeout=config.auth_timeout)
        await browser_manager.initialize()
        _LOGGER.info("Service started successfully")
    except Exception as e:
        _LOGGER.error(f"Failed to start service: {e}")
        raise


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown."""
    _LOGGER.info("Shutting down Family Link Auth Service")
    if browser_manager:
        await browser_manager.cleanup()


@app.get("/", response_class=HTMLResponse)
async def index():
    """Serve the main authentication interface."""
    html_content = """
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Google Family Link Authentication</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }

        .container {
            background: white;
            border-radius: 16px;
            padding: 40px;
            max-width: 500px;
            width: 100%;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
        }

        h1 {
            color: #333;
            margin-bottom: 10px;
            font-size: 28px;
            display: flex;
            align-items: center;
            gap: 10px;
        }

        .subtitle {
            color: #666;
            margin-bottom: 30px;
            font-size: 14px;
            line-height: 1.5;
        }

        .status {
            padding: 15px;
            border-radius: 8px;
            margin-bottom: 20px;
            display: none;
        }

        .status.success {
            background: #d4edda;
            color: #155724;
            border: 1px solid #c3e6cb;
        }

        .status.error {
            background: #f8d7da;
            color: #721c24;
            border: 1px solid #f5c6cb;
        }

        .status.info {
            background: #d1ecf1;
            color: #0c5460;
            border: 1px solid #bee5eb;
        }

        button {
            width: 100%;
            padding: 16px;
            background: #667eea;
            color: white;
            border: none;
            border-radius: 8px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 10px;
        }

        button:hover:not(:disabled) {
            background: #5568d3;
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
        }

        button:disabled {
            background: #ccc;
            cursor: not-allowed;
            transform: none;
        }

        .instructions {
            background: #f8f9fa;
            border-radius: 8px;
            padding: 20px;
            margin-top: 20px;
        }

        .instructions h3 {
            color: #333;
            margin-bottom: 10px;
            font-size: 16px;
        }

        .instructions ol {
            margin-left: 20px;
            color: #666;
            font-size: 14px;
            line-height: 1.8;
        }

        .instructions li {
            margin-bottom: 8px;
        }

        .loader {
            border: 3px solid #f3f3f3;
            border-top: 3px solid #667eea;
            border-radius: 50%;
            width: 20px;
            height: 20px;
            animation: spin 1s linear infinite;
        }

        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }

        .info-box {
            background: #e7f3ff;
            border-left: 4px solid #2196F3;
            padding: 15px;
            margin-top: 20px;
            border-radius: 4px;
            font-size: 14px;
            color: #1976D2;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🔐 Google Family Link</h1>
        <p class="subtitle">Service d'authentification pour l'intégration Home Assistant</p>

        <div id="status" class="status"></div>

        <button id="authButton" onclick="startAuth()">
            Démarrer l'authentification
        </button>

        <div class="instructions">
            <h3>📋 Instructions</h3>
            <ol>
                <li>Cliquez sur "Démarrer l'authentification"</li>
                <li>Une fenêtre de navigateur va s'ouvrir avec la page de connexion Google</li>
                <li>Connectez-vous avec votre compte Google</li>
                <li>Complétez la validation en deux étapes si demandé</li>
                <li>Attendez le message de succès</li>
                <li>Retournez dans Home Assistant pour terminer la configuration</li>
            </ol>
        </div>

        <div class="info-box">
            💡 <strong>Note:</strong> La fenêtre du navigateur peut mettre quelques secondes à apparaître. Ne fermez pas cette page pendant l'authentification.
        </div>
    </div>

    <script>
        let sessionId = null;
        let statusCheckInterval = null;

        async function startAuth() {
            const button = document.getElementById('authButton');
            const status = document.getElementById('status');

            button.disabled = true;
            button.innerHTML = '<div class="loader"></div><span>Démarrage...</span>';

            try {
                showStatus('🔄 Démarrage de l\'authentification...', 'info');

                const response = await fetch('/api/auth/start', {
                    method: 'POST'
                });

                if (!response.ok) {
                    throw new Error('Échec du démarrage de l\'authentification');
                }

                const data = await response.json();
                sessionId = data.session_id;

                showStatus('🌐 Fenêtre du navigateur ouverte. Veuillez vous connecter à Google...', 'info');
                button.innerHTML = '<div class="loader"></div><span>En attente de connexion...</span>';

                // Start checking status
                statusCheckInterval = setInterval(checkAuthStatus, 2000);

            } catch (error) {
                showStatus('❌ Échec du démarrage: ' + error.message, 'error');
                button.disabled = false;
                button.innerHTML = 'Réessayer';
            }
        }

        async function checkAuthStatus() {
            if (!sessionId) return;

            try {
                const response = await fetch(`/api/auth/status/${sessionId}`);
                const data = await response.json();

                if (data.status === 'completed') {
                    clearInterval(statusCheckInterval);
                    showStatus(`✅ Authentification réussie! ${data.cookie_count} cookies sauvegardés.\\n\\nVous pouvez maintenant terminer la configuration dans Home Assistant.`, 'success');

                    const button = document.getElementById('authButton');
                    button.innerHTML = '✓ Authentification terminée';
                    button.style.background = '#28a745';

                } else if (data.status === 'timeout') {
                    clearInterval(statusCheckInterval);
                    showStatus('⏱️ Délai d\'attente dépassé. Veuillez réessayer.', 'error');

                    const button = document.getElementById('authButton');
                    button.disabled = false;
                    button.innerHTML = 'Réessayer l\'authentification';

                } else if (data.status === 'error') {
                    clearInterval(statusCheckInterval);
                    showStatus('❌ Erreur: ' + (data.error || 'Erreur inconnue'), 'error');

                    const button = document.getElementById('authButton');
                    button.disabled = false;
                    button.innerHTML = 'Réessayer l\'authentification';
                }

            } catch (error) {
                console.error('Status check failed:', error);
            }
        }

        function showStatus(message, type) {
            const status = document.getElementById('status');
            status.textContent = message;
            status.className = `status ${type}`;
            status.style.display = 'block';
        }

        // Check if cookies already exist
        window.addEventListener('load', async () => {
            try {
                const response = await fetch('/api/cookies/check');
                const data = await response.json();

                if (data.exists) {
                    showStatus('✓ Des cookies sont déjà enregistrés. Vous pouvez configurer l\'intégration dans Home Assistant.', 'success');
                }
            } catch (error) {
                // Ignore errors on initial check
            }
        });
    </script>
</body>
</html>
    """
    return HTMLResponse(content=html_content)


@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "familylink-auth",
        "version": "1.0.0"
    }


@app.post("/api/auth/start")
async def start_authentication():
    """Start browser authentication flow."""
    try:
        session_id = await browser_manager.start_auth_session()
        _LOGGER.info(f"Started auth session: {session_id}")
        return {
            "session_id": session_id,
            "status": "started",
            "message": "Authentication session started"
        }
    except Exception as e:
        _LOGGER.error(f"Failed to start auth: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/auth/status/{session_id}")
async def check_auth_status(session_id: str):
    """Check authentication status."""
    status = await browser_manager.get_session_status(session_id)
    return status


@app.get("/api/cookies/check")
async def check_cookies():
    """Check if cookies exist."""
    exists = await storage.check_exists()
    return {"exists": exists}


@app.get("/api/cookies")
async def get_cookies():
    """Retrieve stored cookies (for integration)."""
    try:
        cookies = await storage.load_cookies()
        return {
            "cookies": cookies,
            "status": "success",
            "count": len(cookies)
        }
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="No cookies found")
    except Exception as e:
        _LOGGER.error(f"Failed to load cookies: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/cookies")
async def delete_cookies():
    """Delete stored cookies."""
    try:
        await storage.clear_cookies()
        return {"status": "success", "message": "Cookies deleted"}
    except Exception as e:
        _LOGGER.error(f"Failed to delete cookies: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    uvicorn.run(
        app,
        host=config.host,
        port=config.port,
        log_level=config.log_level.lower()
    )
