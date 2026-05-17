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
            data = {
                "id": activity['id'],
                "name": activity['name'],
                "distance": activity['distance'],
                "moving_time": activity['moving_time'],
                "type": activity['type'],
                "start_date": activity['start_date'],
                "average_speed": activity['average_speed']
            }
            db.update_activity(data)
        print(f"✅ Sincronizzazione completata: {len(activities)} attività elaborate.")
    except Exception as e:
        print(f"❌ Errore durante la sincronizzazione: {e}")

def run_health_check():
    print("\n--- 🔍 AVVIO HEALTH CHECK AGENTE ---")
    
    print("1. Controllo Segreti...")
    tg_token = config.get_secret("TELEGRAM_TOKEN")
    if tg_token:
        print(f"   ✅ Segreto TELEGRAM_TOKEN recuperato: {tg_token[:5]}***")
    else:
        print("   ❌ Errore: Impossibile recuperare TELEGRAM_TOKEN.")
        return False

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
        
        # 2. Sincronizzazione Database (mantiene lo storico aggiornato)
        sync_activities()
        
        # 3. Visualizzazione Rapida locale
        print("\nUltime 3 corse salvate nel Cloud:")
        runs = db.get_recent_runs(limit=3)
        for r in runs:
            distanza_km = r['distance'] / 1000
            print(f"- {r['start_date']}: {r['name']} ({distanza_km:.2f} km)")

        print("\n📊 Recupero dati della settimana in corso da Strava...")
        lista_corse, km_totali = strava_client.fetch_weekly_runs()

        print("🤖 L'Agente IA sta generando il report settimanale...")
        feedback_raw = analyst.analyze_weekly_summary(lista_corse, km_totali)

        # PULIZIA DI SICUREZZA: Rimuove eventuali blocchi di codice che Gemini potrebbe aggiungere
        feedback_settimanale = feedback_raw.replace("```html", "").replace("```", "").strip()

        print("\n--- REPORT SETTIMANALE DEL COACH ---")
        print(feedback_settimanale)
        print("------------------------------------")

        # --- INIZIO BLOCCO INVIO TELEGRAM CON BOTTONI ---
        print("📱 Inviando notifica su Telegram con bottoni interattivi...")
        
        messaggio_telegram = f"📅 <b>Report Settimanale MyRunningAgent</b>\n\n{feedback_settimanale}"
        
        # 1. Creiamo la tastiera dinamica basata sulle corse della settimana
        bottoni = []
        if lista_corse:
            for corsa in lista_corse:
                # Creiamo una riga con un singolo bottone per ogni corsa
                # Usiamo l'ID reale della corsa per il callback_data
                bottone = {
                    "text": f"📊 Analizza {corsa['nome']}", 
                    "callback_data": f"analyze_{corsa['id']}"
                }
                bottoni.append([bottone]) # Le parentesi quadre extra mettono un bottone per riga
        
        # 2. Strutturiamo il dizionario come lo vuole Telegram
        tastiera_inline = {"inline_keyboard": bottoni} if bottoni else None
        
        # 3. Spediamo messaggio + tastiera
        if notifier.send_message(messaggio_telegram, reply_markup=tastiera_inline):
            print("✅ Notifica con bottoni inviata con successo sul tuo smartphone!")
        # --- FINE BLOCCO INVIO TELEGRAM ---

        print(f"🚀 Avvio in modalità {'CLOUD' if getattr(config, 'is_cloud', False) else 'LOCALE'}")

    except Exception as e:
        print(f"❌ Errore critico: {e}")

if __name__ == "__main__":
    main()