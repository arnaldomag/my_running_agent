from app.config import config
from app.database import db
import sys

def run_health_check():
    print("\n--- 🔍 AVVIO HEALTH CHECK AGENTE ---")
    
    print("1. Controllo Segreti...")
    tg_token = config.get_secret("TELEGRAM_TOKEN")
    if tg_token:
        print(f"   ✅ Segreto TELEGRAM_TOKEN recuperato: {tg_token[:5]}***")
    else:
        print("   ❌ Errore: Impossibile recuperare TELEGRAM_TOKEN.")
        return False

    print("2. Controllo Connessione Firestore (Dati Biometrici/Piani)...")
    try:
        if db.run_test_write():
            print("   ✅ Scrittura Firestore riuscita.")
    except Exception as e:
        print(f"   ❌ Errore Firestore: {e}")
        return False

    print("--- ✨ TUTTI I SISTEMI SONO OPERATIVI ---\n")
    return True

def main():
    try:
        # 1. Health Check
        if not run_health_check():
            sys.exit(1)
            
        print(f"🚀 Avvio in modalità {'CLOUD' if getattr(config, 'is_cloud', False) else 'LOCALE'}")
        print("💡 Nota: I dati atletici sono ora gestiti in tempo reale via Runalyze MCP.")
        print("💡 Esegui 'python webhook.py' per avviare il server in ascolto per Telegram.")

    except Exception as e:
        print(f"❌ Errore critico: {e}")

if __name__ == "__main__":
    main()