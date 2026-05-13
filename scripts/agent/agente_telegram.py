import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler
import requests
import pandas as pd
#import os
#from dotenv import load_dotenv

# 1. Carica le chiavi in modo sicuro dal file .env
#load_dotenv()

# --- CONFIGURAZIONI ---
TELEGRAM_TOKEN = "8658723002:AAFwOXYe9X_a3Ihkf5ThAl0j6IQ9sSni0-0"
STRAVA_TOKEN = "58f87d83e61572f533318eaa7b5f538d6bf03f3b"

# Setup logging per vedere errori nel terminale
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# Funzione core di analisi (adattata per Telegram)
def calcola_analisi_corsa(id_attivita):
    headers = {"Authorization": f"Bearer {STRAVA_TOKEN}"}
    url = f"https://www.strava.com/api/v3/activities/{id_attivita}"
    res = requests.get(url, headers=headers)
    
    if res.status_code != 200:
        return "❌ Non ho trovato questa attività su Strava."
    
    dati = res.json()
    nome = dati.get('name')
    distanza = dati.get('distance', 0) / 1000
    tempo_sec = dati.get('moving_time', 1)
    
    # Calcolo passo medio
    passo_medio_sec = tempo_sec / distanza
    minuti = int(passo_medio_sec // 60)
    secondi = int(passo_medio_sec % 60)
    
    report = (
        f"🏃 *Analisi Attività: {nome}*\n"
        f"📅 Data: {dati.get('start_date_local')[:10]}\n"
        f"📏 Distanza: {distanza:.2f} km\n"
        f"⏱️ Passo Medio: {minuti}:{secondi:02d} min/km\n"
        f"💓 Battito Medio: {dati.get('average_heartrate', 'N/D')} bpm\n"
        f"👟 Scarpa: {dati.get('gear', {}).get('name', 'Nessuna')}\n"
    )
    return report

# Comando /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Ciao! Sono il tuo Running Agent. Inviami /analizza [ID_STRAVA] per i dettagli.")

# Comando /analizza [ID]
async def analizza(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Per favore, inserisci l'ID dopo il comando. Es: /analizza 123456789")
        return
    
    id_strava = context.args[0]
    await update.message.reply_text("🧠 Sto analizzando i dati...")
    
    risultato = calcola_analisi_corsa(id_strava)
    await update.message.reply_text(risultato, parse_mode='Markdown')

if __name__ == '__main__':
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    
    # Registriamo i comandi
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('analizza', analizza))
    
    print("🚀 Agente Telegram in ascolto...")
    application.run_polling()