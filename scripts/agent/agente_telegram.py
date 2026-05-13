import requests
import pandas as pd
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler
import os
from dotenv import load_dotenv

# 1. Carica le chiavi in modo sicuro dal file .env
load_dotenv()

# --- CONFIGURAZIONI ---
#STRAVA_TOKEN = os.getenv('STRAVA_ACCESS_TOKEN')
#TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
# --- CONFIGURAZIONI ---
CLIENT_ID = os.getenv('STRAVA_CLIENT_ID')
CLIENT_SECRET = os.getenv('STRAVA_CLIENT_SECRET')
REFRESH_TOKEN = os.getenv('STRAVA_REFRESH_TOKEN') # Quello che hai ottenuto la prima volta
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')

def get_fresh_strava_token():
    """Rigenera un access_token valido usando il refresh_token"""
    url = "https://www.strava.com/oauth/token"
    payload = {
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'refresh_token': REFRESH_TOKEN,
        'grant_type': 'refresh_token'
    }
    response = requests.post(url, data=payload)
    if response.status_code == 200:
        return response.json()['access_token']
    else:
        print("❌ Errore nel refresh del token:", response.json())
        return None

# --- FUNZIONI DI CALCOLO ---

def analizza_telemetria(id_attivita):
    token_attivo = get_fresh_strava_token()
    headers = {"Authorization": f"Bearer {token_attivo}"}
    
    # 1. Recupero dati base attività
    url_base = f"https://www.strava.com/api/v3/activities/{id_attivita}"
    res_act = requests.get(url_base, headers=headers).json()
    
    if "distance" not in res_act:
        return "❌ Errore: Non riesco a recuperare i dati dell'attività."

    # 2. Recupero Streams (Dati secondo per secondo)
    url_s = f"{url_base}/streams?keys=time,distance,heartrate,cadence,velocity_smooth&key_by_type=true"
    res_s = requests.get(url_s, headers=headers).json()
    
    # Trasformiamo in DataFrame per calcoli statistici
    df = pd.DataFrame({k: v['data'] for k, v in res_s.items()})
    
    # Dati generali
    nome = res_act.get('name')
    distanza = res_act.get('distance') / 1000
    tempo_moto = res_act.get('moving_time')
    scarpa = res_act.get('gear', {}).get('name', 'Nessuna')
    
    # Passo medio (min/km)
    passo_medio_sec = tempo_moto / distanza
    p_min, p_sec = divmod(int(passo_medio_sec), 60)
    
    # Analisi Cadenza e Battito
    cadenza_media = df['cadence'].mean() * 2 if 'cadence' in df else 0
    hr_media = res_act.get('average_heartrate', 0)
    hr_max = res_act.get('max_heartrate', 0)
    
    # Calcolo Drift Cardiaco approssimativo (Confronto prima metà vs seconda metà)
    meta = len(df) // 2
    hr_inizio = df['heartrate'].iloc[:meta].mean() if 'heartrate' in df else 0
    hr_fine = df['heartrate'].iloc[meta:].mean() if 'heartrate' in df else 0
    drift = ((hr_fine - hr_inizio) / hr_inizio * 100) if hr_inizio > 0 else 0

    report = (
        f"🏃 *{nome}*\n"
        f"📅 {res_act['start_date_local'][:10]}\n"
        f"👟 Scarpa: {scarpa}\n"
        f"---"
        f"📏 *Distanza:* {distanza:.2f} km\n"
        f"⏱ *Passo Medio:* {p_min}:{p_sec:02d} min/km\n"
        f"💓 *FC Media:* {hr_media:.0f} bpm (Max: {hr_max})\n"
        f"👟 *Cadenza:* {cadenza_media:.0f} spm\n"
        f"📉 *Drift Cardiaco:* {drift:+.2f}%\n"
        f"🏔 *Dislivello:* {res_act.get('total_elevation_gain')} m"
    )
    return report

# --- COMANDI BOT ---

async def ultime(update: Update, context: ContextTypes.DEFAULT_TYPE):
    token_attivo = get_fresh_strava_token()
    headers = {"Authorization": f"Bearer {token_attivo}"}
    url = "https://www.strava.com/api/v3/athlete/activities?per_page=5"
    
    response = requests.get(url, headers=headers)
    res = response.json()
    
    # CONTROLLO SICUREZZA: Se Strava restituisce un errore (es. Token scaduto)
    if isinstance(res, dict) and res.get('errors'):
        await update.message.reply_text(f"❌ Errore da Strava: {res.get('message', 'Token non valido')}")
        return

    # Se non ci sono attività
    if not res:
        await update.message.reply_text("📭 Non ho trovato attività recenti.")
        return

    msg = "👟 *Ultime 5 attività:*\n\n"
    
    try:
        for a in res:
            # Qui ora siamo sicuri che 'a' sia un dizionario
            data = a.get('start_date_local', '0000-00-00')[:10]
            nome = a.get('name', 'Senza titolo')
            act_id = a.get('id')
            
            msg += f"📅 {data} - {nome}\n"
            msg += f"🆔 `/analizza {act_id}`\n\n"
        
        await update.message.reply_text(msg, parse_mode='Markdown')
        
    except TypeError as e:
        print(f"Errore di parsing: {e} - Dati ricevuti: {res}")
        await update.message.reply_text("❌ Errore tecnico nel leggere i dati da Strava.")

async def analizza(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Uso: /analizza [ID_STRAVA]")
        return
        
    id_id = context.args[0]
    await update.message.reply_text("🔍 Estrazione telemetria in corso...")
    
    report = analizza_telemetria(id_id)
    await update.message.reply_text(report, parse_mode='Markdown')

# --- AVVIO ---

if __name__ == '__main__':
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler('ultime', ultime))
    app.add_handler(CommandHandler('analizza', analizza))
    
    print("🚀 Running Agent Tecnico ONLINE!")
    app.run_polling()
