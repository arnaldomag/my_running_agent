from functools import lru_cache
import logging
import os

from dotenv import load_dotenv
import google.auth
from google.cloud import secretmanager

load_dotenv()
logger = logging.getLogger(__name__)


class Config:
    def __init__(self):
        # 1. Riconoscimento Ambiente (K_SERVICE indica Google Cloud Run)
        self.is_cloud: bool = os.getenv("K_SERVICE") is not None

        # 2. Identificazione Progetto
        self.project_id: str | None = os.getenv("GOOGLE_CLOUD_PROJECT")
        if not self.project_id:
            try:
                _, self.project_id = google.auth.default()
            except Exception:
                self.project_id = "my-running-agent"

        # Client Secret Manager inizializzato in modo lazy solo se necessario
        self._sm_client: secretmanager.SecretManagerServiceClient | None = None

    @property
    def sm_client(self) -> secretmanager.SecretManagerServiceClient:
        if self._sm_client is None:
            self._sm_client = secretmanager.SecretManagerServiceClient()
        return self._sm_client

    @lru_cache(maxsize=32)
    def get_secret(self, name: str, default: str | None = None) -> str | None:
        """
        Recupera un segreto con caching in-memory.
        1. Controlla prima le variabili d'ambiente (istantaneo, funziona sia in locale
           sia su Cloud Run se i segreti sono montati come env vars).
        2. Se siamo in Cloud e non è nell'env, interroga Secret Manager UNA SOLA VOLTA
           grazie a @lru_cache e riutilizza lo stesso canale gRPC.
        """
        env_val = os.getenv(name)
        if env_val:
            return env_val.strip()

        if self.is_cloud:
            try:
                resource_name = f"projects/{self.project_id}/secrets/{name}/versions/latest"
                response = self.sm_client.access_secret_version(request={"name": resource_name})
                return response.payload.data.decode("UTF-8").strip()
            except Exception as e:
                logger.warning("⚠️ [CONFIG] Errore Secret Manager per '%s': %s", name, e)
                return default

        return default


config = Config()
