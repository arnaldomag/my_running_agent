#!/bin/bash

# 1. Carica le variabili dal file .env (ignora i commenti)
set -a
source ../.env 2>/dev/null || source .env
set +a

# 2. Controlla che le variabili esistano
if [ -z "$GITHUB_TOKEN" ] || [ -z "$GITHUB_USER" ] || [ -z "$GITHUB_REPO" ]; then
    echo "❌ Errore: Assicurati di aver impostato GITHUB_TOKEN, GITHUB_USER e GITHUB_REPO nel file .env"
    exit 1
fi

API_URL="https://api.github.com/repos/$GITHUB_USER/$GITHUB_REPO/issues"

echo "🚀 Connessione alla repository $GITHUB_USER/$GITHUB_REPO in corso..."

# 3. Funzione per creare un'issue tramite cURL
create_issue() {
    local title="$1"
    local body="$2"
    
    # Costruiamo il JSON in linea. Usiamo \n per i ritorni a capo nel Markdown
    curl -s -X POST "$API_URL" \
        -H "Authorization: token $GITHUB_TOKEN" \
        -H "Accept: application/vnd.github.v3+json" \
        -d "{\"title\": \"$title\", \"body\": \"$body\", \"labels\": [\"refactoring\", \"enhancement\"]}" \
        > /dev/null
        
    echo "✅ Creata: $title"
}

# ==========================================
# 4. ESECUZIONE DEI TASK
# ==========================================

create_issue "Refactoring: Rinominare strava_client.py in runalyze_client.py" "Occorre allineare il nome del file e l'istanza esportata al nuovo servizio sorgente dei dati.\n\n- [ ] Rinominare fisicamente il file \`app/strava_client.py\` in \`app/runalyze_client.py\`.\n- [ ] Aprire \`app/runalyze_client.py\` e scorrere fino all'ultima riga.\n- [ ] Modificare l'istanza finale da \`strava_client = RunalyzeClient()\` a \`runalyze_client = RunalyzeClient()\`."

create_issue "Refactoring: Aggiornare le importazioni in webhook.py e main.py" "I file di avvio dell'applicazione devono importare il nuovo client e passarlo all'orchestratore.\n\n- [ ] In \`webhook.py\`, modificare l'importazione: \`from app.strava_client import strava_client\` in \`from app.runalyze_client import runalyze_client\`.\n- [ ] In \`webhook.py\`, aggiornare l'inizializzazione: \`orchestrator = BotOrchestrator(db, runalyze_client, analyst, notifier)\`.\n- [ ] In \`main.py\`, modificare l'importazione: \`from app.strava_client import strava_client\` in \`from app.runalyze_client import runalyze_client\`.\n- [ ] In \`main.py\`, sostituire le chiamate \`strava_client.fetch_...\` con \`runalyze_client.fetch_...\`."

create_issue "Refactoring: Sostituire le nomenclature Strava in orchestrator.py" "L'orchestratore gestisce le comunicazioni testuali con l'utente e richiama i metodi. Deve essere ripulito da ogni riferimento al vecchio sistema.\n\n- [ ] In \`app/orchestrator.py\`, aggiornare la firma dell'\`__init__\`: \`def __init__(self, db, runalyze_client, analyst, notifier):\`.\n- [ ] All'interno dell'\`__init__\`, aggiornare l'assegnazione: \`self.runalyze_client = runalyze_client\`.\n- [ ] Usare il 'Trova e Sostituisci' globale solo all'interno di questo file per cambiare \`self.strava_client\` in \`self.runalyze_client\`.\n- [ ] Cambiare i testi dei log e dei messaggi Telegram (es. 'garage Strava' -> 'Runalyze', '[STRAVA]' -> '[RUNALYZE]').\n- [ ] Rinominare la chiamata al metodo AI da \`chat_with_strava_context\` a \`chat_with_runalyze_context\`."

create_issue "Refactoring: Allineare i System Prompts e i metodi dell'Analyst a Runalyze" "L'Intelligenza Artificiale non deve più fare riferimento a metriche 'Strava', ma 'Runalyze'.\n\n- [ ] In \`app/analyst.py\`, rinominare il metodo \`def chat_with_strava_context\` in \`def chat_with_runalyze_context\`.\n- [ ] In \`app/prompts.py\`, cercare \`PROMPT_ANALISI_CORSA\` e sostituire la stringa \`DATI A PREVENTIVO (NOTE SU STRAVA):\` con \`DATI A PREVENTIVO (NOTE SU RUNALYZE):\`.\n- [ ] In \`app/prompts.py\`, cercare \`PROMPT_ANALISI_SCARPA\` e sostituire \`Nome in Strava:\` con \`Nome in Runalyze:\`."

create_issue "Docs: Sostituire Strava con Runalyze nel README.md" "La documentazione del progetto deve riflettere la nuova architettura.\n\n- [ ] Aprire \`README.md\`.\n- [ ] Eseguire un Trova e Sostituisci globale di 'Strava' con 'Runalyze'.\n- [ ] Aggiornare la descrizione del file nell'albero delle directory (da \`app/strava_client.py\` a \`app/runalyze_client.py\`)."

echo "🎉 Tutti i task sono stati creati su GitHub!"