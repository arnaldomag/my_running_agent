# 🏃‍♂️ My Running Agent

[cite_start]Un assistente virtuale per il running basato su Telegram, progettato per automatizzare la sincronizzazione con **Strava**, gestire la pianificazione degli allenamenti e fornire analisi tecniche avanzate tramite l'Intelligenza Artificiale di **Google Gemini**[cite: 10, 11]. [cite_start]Il sistema è cloud-native e interamente deployato su **Google Cloud Platform** (Cloud Run & Firestore)[cite: 11].

---

## 🌟 Funzionalità Principali

* **📊 Dashboard Interattiva (Telegram Mini App):**
    * [cite_start]Visualizzazione dei trend di allenamento (passo e chilometraggio) e monitoraggio del peso corporeo tramite un'interfaccia grafica integrata direttamente in Telegram[cite: 161, 374, 386, 392].
    * [cite_start]Validazione crittografica sicura (HMAC-SHA256) per garantire che solo le richieste provenienti dalla tua chat Telegram possano accedere ai dati[cite: 406, 407].
* **📅 Pianificazione Settimanale Integrata (Mini-CRUD):**
    * [cite_start]Crea, visualizza, modifica e completa gli allenamenti direttamente da Telegram tramite messaggi testuali e bottoni inline (`✅ Chiudi`, `↩️ Riapri`, `❌ Elimina`)[cite: 12].
* **🤖 Analisi AI Avanzata:**
    * [cite_start]**Singola Corsa:** Confronta l'allenamento reale (passo, bpm, lap) con l'obiettivo prefissato nelle note[cite: 13, 197].
    * [cite_start]**Report Settimanale:** Schedulato in automatico ogni domenica sera, valuta il volume e la qualità della settimana in corso rispetto alla preparazione di 10km/mezze maratone[cite: 14, 144].
* **👟 Gestione Scarpiera Intelligente:**
    * [cite_start]Sincronizzazione automatica dei modelli attivi da Strava[cite: 15, 128].
    * [cite_start]Valutazione predittiva dell'usura dei materiali incrociata dinamicamente con il peso aggiornato dell'atleta[cite: 16, 133].
* **📸 OCR su Metriche Corporee:**
    * [cite_start]Invia lo screenshot di una bilancia smart: l'agente (tramite Gemini Flash) estrarrà automaticamente data, peso, IMC e percentuali salvandole direttamente nel database[cite: 17, 70, 138].
* **💬 Chat Contestuale AI:**
    * Chiedi consigli al coach in linguaggio naturale. [cite_start]L'agente "ricorda" lo storico delle tue ultime interazioni e il contesto delle tue ultime 100 corse[cite: 18, 19].

---

## 🏗️ Architettura del Software

Il progetto è strutturato seguendo il pattern **Controller-Service** per garantire scalabilità e single-responsibility:

* **`webhook.py`**: L'entry point. [cite_start]Smista le richieste HTTP in arrivo da Telegram e da Cloud Scheduler e serve le API per la Web App[cite: 20, 21].
* **`app/orchestrator.py`**: Il *cervello* operativo. [cite_start]Coordina i servizi e contiene tutta la logica di business e la preparazione dei dati per la dashboard[cite: 22, 162].
* **`app/strava_client.py`**: Modulo ETL per l'integrazione con Strava. [cite_start]Esegue micro-sincronizzazioni intelligenti e importazioni storiche massive[cite: 23].
* **`app/database.py`**: Gestore Firestore. [cite_start]Amministra le collezioni per attività, metriche, piani settimanali e storico chat[cite: 24, 79].
* **`app/analyst.py` & `app/prompts.py`**: Moduli AI disaccoppiati. Elaborano prompt complessi usando i modelli Gemini[cite: 25, 41].
* [cite_start]**`app/telegram_client.py`**: Wrapper per comunicare con l'API di Telegram ed effettuare il parsing di testo e immagini[cite: 26, 253].

---

## 🛠️ Comandi Telegram Supportati

| Comando | Descrizione |
| :--- | :--- |
| `/dashboard` | **[NUOVO]** Apre la Web App integrata per visualizzare i grafici dei tuoi allenamenti e le metriche di peso. |
| `/pianifica` | [cite_start]Inserisci un nuovo piano settimanale separando le sessioni con una riga vuota[cite: 27, 28]. |
| `/piano` | [cite_start]Visualizza il piano corrente con bottoni interattivi (Chiudi, Riapri, Elimina)[cite: 28, 29]. |
| `/modifica [ID]` | [cite_start]Modifica i dettagli (gli step) di una specifica sessione mantenendola attiva (es. `/modifica 0`)[cite: 29, 30]. |
| `/scarpe` | [cite_start]Mostra la scarpiera attuale e permette di lanciare l'analisi diagnostica sullo stato dei materiali[cite: 30, 31]. |
| `/syncstorico [anno]` | [cite_start]Scarica da Strava e salva su DB tutte le corse di un anno specifico (es. `/syncstorico 2026`)[cite: 31, 32]. |
| *Invia Foto* | [cite_start]Manda un'immagine per attivare la pipeline OCR di estrazione dati (es. metriche bilancia)[cite: 32, 33]. |
| *Testo Libero* | [cite_start]Scrivi un messaggio testuale normale per conversare con il tuo coach virtuale[cite: 33, 34]. |

---

## 🚀 Deployment (Google Cloud Platform)

Il progetto gira in modalità serverless:
* [cite_start]**Cloud Run**: Esegue l'applicazione Flask e gestisce certificati HTTPS nativi necessari per la Telegram Mini App[cite: 37, 75].
* **Firestore**: Database NoSQL per memorizzare stato, sessioni e storico[cite: 38].
* [cite_start]**Secret Manager**: Protegge token e chiavi (`TELEGRAM_TOKEN`, `STRAVA_CLIENT_ID`, `STRAVA_CLIENT_SECRET`, `STRAVA_REFRESH_TOKEN`, `GEMINI_API_KEY`, `WEBAPP_URL`)[cite: 39, 76, 77].
* [cite_start]**Cloud Scheduler**: Job Cron automatizzato che triggera il report settimanale ogni domenica alle 20:00[cite: 40].
