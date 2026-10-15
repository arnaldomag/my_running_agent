import logging
import sys
import time
from app.config import config
from app.database import db

# Configurazione logging standard (ottimale per Cloud Run / stdout)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stdout
)
logger = logging.getLogger(__name__)


def run_health_check() -> bool:
    start_time = time.perf_counter()
    logger.info("🔍 Avvio Health Check Agente...")

    # 1. Controllo Segreti
    tg_token = config.get_secret("TELEGRAM_TOKEN")
    if not tg_token:
        logger.error("❌ Impossibile recuperare TELEGRAM_TOKEN.")
        return False
    logger.info("✅ Segreto TELEGRAM_TOKEN recuperato (%s***)", tg_token[:5])

    # 2. Controllo Connessione Firestore
    try:
        if not db.run_test_write():
            logger.error("❌ Scrittura di test su Firestore fallita.")
            return False
        logger.info("✅ Connessione e scrittura Firestore riuscita.")
    except Exception as e:
        logger.exception("❌ Errore durante il test Firestore: %s", e)
        return False

    elapsed = (time.perf_counter() - start_time) * 1000
    logger.info("✨ Tutti i sistemi sono operativi (Health Check completato in %.1f ms)", elapsed)
    return True


def main() -> None:
    if not run_health_check():
        sys.exit(1)

    env_mode = "CLOUD" if getattr(config, "is_cloud", False) else "LOCALE"
    logger.info("🚀 Avvio in modalità %s", env_mode)
    logger.info("💡 Dati atletici gestiti in tempo reale via Runalyze MCP.")
    logger.info("💡 Esegui Gunicorn o 'python webhook.py' per avviare il server in ascolto.")


if __name__ == "__main__":
    main()
