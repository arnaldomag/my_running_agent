import sys
from app.config import config
from app.database import db

def run_health_check():
    print("\n--- 🔍 AVVIO HEALTH CHECK AGENTE ---")
    
    # 1. Verifica Segreti
    print("1. Controllo Segreti...")
    tg_token = config.get_secret("TELEGRAM_TOKEN")
    if tg_token:
        print(f"   ✅ Segreto TELEGRAM_TOKEN recuperato: {tg_token[:5]}***")
    else:
        print("   ❌ Errore: Impossibile recuperare TELEGRAM_TOKEN.")
        return False

    # 2. Verifica Database tramite la nuova funzione di test
    print("2. Controllo Connessione Firestore...")
    try:
        if db.run_test_write():
            print("   ✅ Scrittura Firestore riuscita.")
    except Exception as e:
        print(f"   ❌ Errore Firestore: {e}")
        return False

    print("--- ✨ TUTTI I SISTEMI SONO OPERATIVI ---\n")
    return True

def main():
    if not run_health_check():
        sys.exit(1)

    print(f"🚀 Avvio in modalità {'CLOUD' if config.is_cloud else 'LOCALE'}")

if __name__ == "__main__":
    main()