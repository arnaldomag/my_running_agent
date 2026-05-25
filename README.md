# 🏃‍♂️ My Running Agent

Un assistente virtuale per il running basato su Telegram, progettato per automatizzare la sincronizzazione con **Strava**, gestire la pianificazione degli allenamenti e fornire analisi tecniche avanzate tramite l'Intelligenza Artificiale di **Google Gemini**. Il sistema è cloud-native e interamente deployato su **Google Cloud Platform** (Cloud Run & Firestore).

---

## 🌟 Funzionalità Principali

* **📅 Pianificazione Settimanale Integrata (Mini-CRUD):**
    * Crea, visualizza, modifica e completa gli allenamenti direttamente da Telegram tramite messaggi testuali e bottoni inline (`✅ Chiudi`, `↩️ Riapri`, `❌ Elimina`).
* **🤖 Analisi AI Avanzata:**
    * **Singola Corsa:** Confronta l'allenamento reale (passo, bpm, lap) con l'obiettivo prefissato nelle note.
    * **Report Settimanale:** Schedulato in automatico ogni domenica sera (tramite Cloud Scheduler), valuta il volume e la qualità della settimana in corso rispetto alla preparazione di 10km/mezze maratone.
* **👟 Gestione Scarpiera Intelligente:**
    * Sincronizzazione automatica dei modelli attivi da Strava.
    * Valutazione predittiva dell'usura dei materiali (es. schiume PEBA/EVA) incrociata dinamicamente con il peso aggiornato dell'atleta.
* **📸 OCR su Metriche Corporee:**
    * Invia lo screenshot di una bilancia smart: l'agente (tramite Gemini Flash) estrarrà automaticamente data, peso, IMC e percentuali (massa grassa/muscolare) salvandole direttamente nel database.
* **💬 Chat Contestuale AI:**
    * Chiedi consigli al coach in linguaggio naturale. L'agente "ricorda" lo storico delle tue ultime interazioni e il contesto delle tue ultime 100 corse.

---

## 🏗️ Architettura del Software

Il progetto è strutturato seguendo il solido pattern **Controller-Service** per garantire scalabilità, manutenibilità e single-responsibility:

* **`webhook.py`**: L'entry point (il *vigile urbano*). Smista in modo rapido e pulito le richieste HTTP in arrivo da Telegram e da Cloud Scheduler.
* **`app/orchestrator.py`**: Il *cervello* operativo. Coordina i servizi e contiene tutta la logica di business.
* **`app/strava_client.py`**: Modulo ETL per l'integrazione con Strava. Esegue micro-sincronizzazioni intelligenti e importazioni storiche massive.
* **`app/database.py`**: Gestore Firestore. Amministra le collezioni per attività, metriche, piani settimanali e storico chat.
* **`app/analyst.py` & `app/prompts.py`**: Moduli AI disaccoppiati. Elaborano prompt complessi usando i modelli Gemini estraendo i testi in un file di configurazione dedicato.
* **`app/telegram_client.py`**: Wrapper pulito per comunicare con l'API di Telegram ed effettuare il parsing di testo e immagini.

---

## 🛠️ Comandi Telegram Supportati

| Comando | Descrizione |
| :--- | :--- |
| `/pianifica` | Inserisci un nuovo piano settimanale separando le sessioni con una riga vuota. |
| `/piano` | Visualizza il piano corrente con bottoni interattivi (Chiudi, Riapri, Elimina). |
| `/modifica [ID]` | Modifica i dettagli (gli step) di una specifica sessione mantenendola attiva (es. `/modifica 0`). |
| `/scarpe` | Mostra la scarpiera attuale e permette di lanciare l'analisi diagnostica sullo stato dei materiali. |
| `/syncstorico [anno]` | Scarica da Strava e salva su DB tutte le corse di un anno specifico (es. `/syncstorico 2026`). |
| *Invia Foto* | Manda un'immagine per attivare la pipeline OCR di estrazione dati (es. metriche bilancia). |
| *Testo Libero* | Scrivi un messaggio testuale normale per conversare con il tuo coach virtuale. |

---

## 📂 Struttura della Repository

```text
├── app/
│   ├── __init__.py
│   ├── analyst.py           # Integrazione SDK Google GenAI
│   ├── config.py            # Gestione variabili d'ambiente e Secrets
│   ├── database.py          # Operazioni CRUD su Firestore
│   ├── orchestrator.py      # Logica di business e orchestrazione servizi
│   ├── prompts.py           # File di configurazione per i System Prompt AI
│   ├── strava_client.py     # Wrapper API Strava
│   └── telegram_client.py   # Wrapper API Telegram
├── scripts/
│   ├── archive/             # Codice storicizzato / vecchi esperimenti
│   ├── bonifiche/           # Script di utilità per pulizia dati storici (ETL batch)
│   └── liste/               # Script di data profiling in sola lettura
├── check_models.py          # Utility di verifica dei modelli LLM disponibili
├── main.py                  # Entry point WSGI/Gunicorn
├── webhook.py               # Entry point Flask (Route API principale)
└── README.md                # Questo file
```

## 🚀 Deployment (Google Cloud Platform)
​Questo progetto è configurato per girare interamente serverless su GCP:
* **Cloud Run**: Esegue ed espone gli endpoint Flask (/telegram-webhook, /tasks/weekly-report).
​
* **Firestore**: Database NoSQL utilizzato come single source of truth per memorizzare stato, sessioni e storico.
​
* **Secret Manager**: Protegge token e chiavi (TELEGRAM_TOKEN, STRAVA_CLIENT_ID, STRAVA_CLIENT_SECRET, STRAVA_REFRESH_TOKEN, GEMINI_API_KEY).
​
* **Cloud Scheduler**: Job Cron automatizzato che triggera il report settimanale ogni domenica alle 20:00 (stringa cron: 0 20 * * 0).
