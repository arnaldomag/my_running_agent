from app.config import config
from app.database import db
from app.strava_client import strava_client
from app.analyst import analyst
import sys
from app.telegram_client import notifier

def sync_activities():
    print("🔄 Sincronizzazione attività da Strava...")
    try:
        activities = strava_client.fetch_recent_activities(limit=5)
        for activity in activities:
            # Prepariamo i dati per Firestore
            # Puoi mappare solo i campi che ti interessano
            data = {
                "id": activity['id'],
                "name": activity['name'],
                "distance": activity['distance'], # in metri
                "moving_time": activity['moving_time'],
                "type": activity['type'],
                "start_date": activity['start_date'],
                "average_speed": activity['average_speed']
            }
            # Salvataggio su Firestore
            db.update_activity(data)
        print(f"✅ Sincronizzazione completata: {len(activities)} attività elaborate.")
    except Exception as e:
        print(f"❌ Errore durante la sincronizzazione: {e}")

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
    try:
        # 1. Health Check
        if not run_health_check():
            sys.exit(1)
        
        # 2. Esecuzione Logica
        sync_activities()
        
        # 3. Visualizzazione Rapida
        print("\nUltime 3 corse salvate nel Cloud:")
        runs = db.get_recent_runs(limit=3)
        for r in runs:
            distanza_km = r['distance'] / 1000
            print(f"- {r['start_date']}: {r['name']} ({distanza_km:.2f} km)")

        print("\n🤖 L'Agente IA sta analizzando le tue prestazioni...")

        # ... (codice precedente) ...
        feedback = analyst.analyze_recent_performance()
        print("\n--- REPORT DEL COACH ---")
        print(feedback)
        print("------------------------")

        # NUOVO BLOCCO: Invio a Telegram
        print("📱 Inviando notifica su Telegram...")
        
        # Formattiamo il messaggio per renderlo carino sul telefono
        messaggio_telegram = f"🏃‍♂️ *Report Coach Gemini 2.5*\n\n{feedback}"
        
        if notifier.send_message(messaggio_telegram):
            print("✅ Notifica inviata con successo sul tuo smartphone!")
        print(f"🚀 Avvio in modalità {'CLOUD' if config.is_cloud else 'LOCALE'}")

    except Exception as e:
        print(f"❌ Errore critico: {e}")

if __name__ == "__main__":
    main()
   


