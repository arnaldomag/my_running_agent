from datetime import datetime
import logging
import time
from typing import Any

import requests

from app.config import config

logger = logging.getLogger(__name__)


class RunalyzeClient:
    CACHE_TTL_SECONDS = 300  # 5 minuti di cache per l'anagrafica scarpe
    DEFAULT_TIMEOUT = 15

    def __init__(self):
        raw_token = config.get_secret("RUNALYZE_TOKEN") or ""
        self.token = raw_token.replace("pt#", "").strip()
        self.base_url = "https://runalyze.com/api/v1"

        # Sessione persistente TCP Keep-Alive
        self.session = requests.Session()
        self.session.headers.update({
            "token": self.token,
            "Accept": "application/json"
        })

        # Cache leggera in-memory per evitare chiamate doppie tra /scarpe e click sul bottone
        self._shoes_cache: list[dict[str, Any]] | None = None
        self._shoes_cache_time: float = 0.0

    def fetch_athlete_shoes(self, force_refresh: bool = False) -> list[dict[str, Any]]:
        """Recupera l'elenco delle scarpe dal profilo Runalyze (con cache TTL di 5 minuti)."""
        now = time.monotonic()
        if not force_refresh and self._shoes_cache is not None and (now - self._shoes_cache_time) < self.CACHE_TTL_SECONDS:
            return self._shoes_cache

        try:
            url = f"{self.base_url}/equipment"
            res = self.session.get(url, timeout=self.DEFAULT_TIMEOUT)
            res.raise_for_status()
            data = res.json()

            if isinstance(data, list):
                self._shoes_cache = data
                self._shoes_cache_time = now
                return data
            return []
        except Exception as e:
            logger.error("❌ [API] Errore recupero scarpe da Runalyze: %s", e)
            return self._shoes_cache or []

    def fetch_gear_details(self, gear_id: str | int) -> dict[str, Any] | None:
        """
        Recupera i dettagli di un singolo modello tramite ID.
        Controlla prima nella cache della scarpiera per rispondere in 0 ms senza rete.
        """
        target_id = str(gear_id)

        # 1. Fast-path: se abbiamo appena scaricato la lista con /scarpe, il dato è già in RAM!
        if self._shoes_cache:
            for item in self._shoes_cache:
                if str(item.get("id")) == target_id:
                    return item

        # 2. Fallback: chiamata API puntuale
        try:
            url = f"{self.base_url}/equipment/{target_id}"
            res = self.session.get(url, timeout=self.DEFAULT_TIMEOUT)
            res.raise_for_status()
            return res.json()
        except Exception as e:
            logger.error("❌ [API] Errore recupero dettaglio equipaggiamento %s: %s", target_id, e)
            return None

    @staticmethod
    def _safe_float(dati: dict[str, Any], key: str) -> float:
        val = dati.get(key)
        if not val:
            return 0.0
        try:
            return float(str(val).replace(",", ".").strip())
        except ValueError:
            return 0.0

    def upload_body_metrics(self, dati_corporei: dict[str, Any]) -> bool:
        """Carica le metriche corporee su Runalyze tramite chiamata POST."""
        logger.info("🏋️ [API] Invio composizione corporea a Runalyze...")
        try:
            url = f"{self.base_url}/metrics/bodyComposition"
            payload = {
                "date_time": datetime.now().isoformat(),
                "weight": self._safe_float(dati_corporei, "peso_kg"),
                "fat_percentage": self._safe_float(dati_corporei, "massa_grassa_percentuale"),
                "water_percentage": self._safe_float(dati_corporei, "massa_idrica_percentuale"),
                "muscle_percentage": self._safe_float(dati_corporei, "massa_muscolare_percentuale"),
                "bone_percentage": self._safe_float(dati_corporei, "massa_ossea_percentuale")
            }

            res = self.session.post(url, json=payload, timeout=self.DEFAULT_TIMEOUT)
            res.raise_for_status()

            logger.info("✅ [API] Dati corporei caricati con successo su Runalyze.")
            return True

        except requests.exceptions.HTTPError as errh:
            dettaglio = errh.response.text if errh.response is not None else "Nessun dettaglio"
            logger.error("❌ [API] Errore HTTP Runalyze (%s): %s", errh, dettaglio)
            return False
        except Exception as e:
            logger.error("❌ [API] Errore di sistema nel caricamento metriche: %s", e)
            return False


runalyze_client = RunalyzeClient()
