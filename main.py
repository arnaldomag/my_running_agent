from app.config import config
from app.database import db
from app.runalyze_client import runalyze_client
from app.analyst import analyst
import sys
from datetime import date, timedelta
from app.telegram_client import notifier

def sync_activities():
    print("🔄 Sincronizzazione attività da Runalyze...")
    try:
        # Il nuovo metodo sync_latest_activities fa già tutto: scarica, mappa e salva su Firestore
        if runalyze_client.sync_latest_activities(db, limit=5):
            print("✅ Sincronizzazione rapida completata con successo.")
        else:
            print("⚠️ Sincronizzazione completata con qualche anomalia.")
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
            # Estrazione usando le nuove chiavi italiane. Distanza è già in KM!
            distanza_km = r.get('distanza', 0)
            nome = r.get('nome', 'Corsa')
            data_start = r.get('start_date', 'N/D')
            print(f"- {data_start}: {nome} ({distanza_km:.2f} km)")

        print("\n📊 Recupero dati della settimana in corso dal database...")
        # Estraiamo i dati della settimana direttamente da Firestore come fa l'Orchestrator
        oggi = date.today()
        lunedi = oggi - timedelta(days=oggi.weekday())
        domenica = lunedi + timedelta(days=6)
        
        str_lunedi = lunedi.strftime("%Y-%m-%d")
        str_domenica = domenica.strftime("%Y-%m-%d")
        
        query_corse = db.db.collection(db.collection_name) \
            .where("start_date", ">=", str_lunedi) \
            .where("start_date", "<=", str_domenica) \
            .order_by("start_date", direction="DESCENDING") \
            .get()

        lista_corse = []
        for doc in query_corse:
            corsa = doc.to_dict()
            corsa['data'] = corsa.get('start_date', 'N/D')
            corsa['nome'] = corsa.get('nome', 'Corsa')
            corsa['distanza'] = corsa.get('distanza', 0)
            corsa['tempo'] = corsa.get('tempo_movimento', 0)
            lista_corse.append(corsa)

        # Sommiamo le distanze già in chilometri
        km_totali = sum([c['distanza'] for c in lista_corse])

        # --- SE LA SETTIMANA È VUOTA: PROPONI IL BIVIO INTERATTIVO ---
        if not lista_corse:
            print("⚠️ Nessun allenamento trovato questa settimana. Invio proposta di fallback su Telegram...")
            
            messaggio_domanda = (
                "📅 <b>Report Settimanale MyRunningAgent</b>\n\n"
                "💤 Non ho trovato allenamenti registrati per questa settimana.\n\n"
                "Vuoi analizzare i dati dell'<b>ultima settimana attiva</b> disponibile?"
            )
            
            # Creiamo i due bottoni di scelta
            bottoni_scelta = [[
                {"text": "✅ Sì, grazie", "callback_data": "fallback_last_week_show"},
                {"text": "❌ No, va bene così", "callback_data": "fallback_last_week_ignore"}
            ]]
            
            tastiera_inline = {"inline_keyboard": bottoni_scelta}
            
            if notifier.send_message(messaggio_domanda, reply_markup=tastiera_inline):
                print("✅ Domanda di fallback inviata su Telegram.")
            return # Interrompiamo l'esecuzione del main qui
        # --- FINE BLOCCO BIVIO ---

        # Questo codice viene eseguito SOLO se ci sono corse nella settimana corrente
        print("🤖 L'Agente IA sta generando il report settimanale...")
        feedback_raw = analyst.analyze_weekly_summary(lista_corse, km_totali)
        feedback_settimanale = feedback_raw.replace("```html", "").replace("```", "").strip()

        print("\n📱 Inviando notifica standard con bottoni...")
        messaggio_telegram = f"📅 <b>Report Settimanale MyRunningAgent</b>\n\n{feedback_settimanale}"
        
        bottoni = []
        for corsa in lista_corse:
            bottone = {"text": f"📊 Analizza {corsa['nome']}", "callback_data": f"analyze_{corsa['id']}"}
            bottoni.append([bottone])
        
        tastiera_inline = {"inline_keyboard": bottoni} if bottoni else None
        notifier.send_message(messaggio_telegram, reply_markup=tastiera_inline)

        print(f"🚀 Avvio in modalità {'CLOUD' if getattr(config, 'is_cloud', False) else 'LOCALE'}")

    except Exception as e:
        print(f"❌ Errore critico: {e}")

if __name__ == "__main__":
    main()