Strava AI Agent

Python Strava API OAuth2 Data Analysis
Questo progetto nasce nell'ambito della discussione "Agenti IA: Funzionamento e
Applicazioni Pratiche" con l'obiettivo di creare un assistente intelligente per il
monitoraggio avanzato delle attività atletiche.

Descrizione del Progetto
L'agente IA è stato progettato per superare le limitazioni delle API chiuse (come
quelle di Suunto) interfacciandosi direttamente con le API di Strava. La sua funzione
principale è automatizzare l'analisi delle performance e la gestione dell'attrezzatura
tecnica.

Funzionalità Principali
Monitoraggio Usura Scarpe: Calcolo automatico dei chilometri percorsi per ogni
paio di scarpe, con alert per la sostituzione basati sulla densità del foam e sullo
stato dello storico.
Integrazione OAuth2: Gestione sicura del flusso di autenticazione per l'accesso ai
dati personali di Strava.
Bonifica Dati: Script Python dedicati alla pulizia dello storico corse e
all'associazione massiva delle calzature corrette tramite file JSON.
Reporting Avanzato: Generazione di report dettagliati su metriche chiave come
SPM (passi al minuto), passo medio e progressioni.

Tecnologie Utilizzate

Linguaggio: Python
Librerie: Requests (per API), Pandas (per analisi dati), JSON (per configurazioni).
Autenticazione: Flusso OAuth2 (Client ID, Client Secret, Refresh Tokens).
•

•

•

•

•
•
•

Struttura del Codice

/
├── auth_manager.py # Gestione token e autenticazione Strava
├── data_fetcher.py # Recupero attività tramite API
├── shoes_tracker.py # Logica monitoraggio usura e chilometraggio
├── reports/ # Cartella output per le analisi generate
└── config/
└── mapping.json # Mappatura massiva attività-scarpe

Sviluppi Futuri

Il progetto prevede la migrazione verso un ambiente cloud per consentire analisi in
tempo reale e l'integrazione di modelli predittivi per suggerire carichi di allenamento
ottimali.

Sviluppato come caso studio pratico per l'implementazione di agenti autonomi nel settore
sport-tech.
