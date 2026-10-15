import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from app.config import config

logger = logging.getLogger(__name__)

# Pre-compilazione espressioni regolari
RE_RUNALYZE_LINKS = re.compile(r"\[RUNALYZE_LINKS:\s*(.*?)\]")
RE_PLAN_BLOCKS = re.compile(r"\n\s*\n")

# Pool leggero per parallelizzare le 2 letture Firestore del contesto (peso + piano)
_io_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="orch_io")


class BotOrchestrator:
    def __init__(self, db, analyst, notifier, runalyze_client=None):
        self.db = db
        self.analyst = analyst
        self.notifier = notifier
        self.runalyze_client = runalyze_client
        self.default_chat_id = os.environ.get("TELEGRAM_CHAT_ID") or config.get_secret("TELEGRAM_CHAT_ID")

    # ==========================================
    # 0. UTILITY: IL CONTESTO FIRESTORE (PARALLELO)
    # ==========================================
    def _build_omni_context(self) -> str:
        """
        Recupera dati biometrici e piano settimanale da Firestore in parallelo.
        """
        future_weight = _io_pool.submit(self.db.get_latest_weight, True)
        future_plan = _io_pool.submit(self.db.get_weekly_plan)

        dati_corporei = future_weight.result()
        piano = future_plan.result()

        testo_metriche = "Dati biometrici non disponibili."
        if isinstance(dati_corporei, dict) and dati_corporei:
            testo_metriche = (
                f"Data misurazione: {dati_corporei.get('data', 'N/D')}\n"
                f"- Peso: {dati_corporei.get('peso_kg', 'N/D')} kg\n"
                f"- Massa Grassa: {dati_corporei.get('massa_grassa_percentuale', 'N/D')}%\n"
                f"- Massa Muscolare: {dati_corporei.get('massa_muscolare_percentuale', 'N/D')}%\n"
                f"- Massa Ossea: {dati_corporei.get('massa_ossea_percentuale', 'N/D')}%\n"
                f"- Massa Idrica: {dati_corporei.get('massa_idrica_percentuale', 'N/D')}%"
            )

        testo_piano = "Nessun piano programmato per questa settimana."
        if piano and piano.get("sessions"):
            linee_piano = [
                f"- {s['name']} [{'✅ COMPLETATA' if s.get('status') == 'done' else '🟡 DA FARE'}]: "
                f"{' | '.join(s.get('steps', []))}"
                for s in piano["sessions"]
            ]
            testo_piano = "\n".join(linee_piano)

        return (
            f"[PARAMETRI BIOMETRICI ATLETA - DA FIRESTORE]\n{testo_metriche}\n\n"
            f"[PIANIFICAZIONE SETTIMANALE ATTUALE - DA FIRESTORE]\n{testo_piano}"
        )

    def answer_callback(self, callback_query_id: str) -> None:
        """Spegne l'icona di caricamento del bottone su Telegram."""
        if hasattr(self.notifier, "answer_callback_query"):
            self.notifier.answer_callback_query(callback_query_id)
            return

        try:
            import requests
            token = config.get_secret("TELEGRAM_TOKEN")
            url = f"https://api.telegram.org/bot{token}/answerCallbackQuery"
            requests.post(url, json={"callback_query_id": callback_query_id}, timeout=5)
        except Exception as e:
            logger.warning("⚠️ Errore answerCallbackQuery: %s", e)

    # ==========================================
    # 1. GESTIONE CHAT E COMANDI DIRETTI
    # ==========================================
    def handle_chat_ai(self, chat_id: int | str | None, testo: str) -> None:
        """Dirotta i messaggi liberi alla chat arricchendola con il contesto di Firestore."""
        target_chat_id = chat_id or self.default_chat_id
        logger.info("💬 [ORCHESTRATOR] Raccolta contesto Omni-Agent per chat_id %s...", target_chat_id)
        self.notifier.send_message("✍️ L'agente sta elaborando la risposta...", chat_id=target_chat_id)

        try:
            context_string = self._build_omni_context()
            risposta_agente = self.analyst.chat_omni_agent(target_chat_id, testo, context_string)

            if not risposta_agente:
                self.notifier.send_message(
                    "⚠️ Si è verificato un timeout nella generazione della risposta.",
                    chat_id=target_chat_id
                )
                return

            risposta_pulita = risposta_agente.strip()

            # Pulizia eventuali blocchi markdown esterni
            if risposta_pulita.startswith("```"):
                lines = risposta_pulita.splitlines()
                if len(lines) > 2 and lines[0].startswith("```") and lines[-1].startswith("```"):
                    risposta_pulita = "\n".join(lines[1:-1]).strip()

            # Estrazione ID e Nomi per creazione bottoni link Runalyze
            tastiera_inline = None
            match = RE_RUNALYZE_LINKS.search(risposta_pulita)
            if match:
                links_str = match.group(1)
                bottoni = []
                for item in links_str.split(","):
                    parts = item.strip().split("|", 1)
                    if len(parts) == 2:
                        aid, aname = parts[0].strip(), parts[1].strip()
                        if aid.isdigit():
                            nome_bottone = f"{aname[:35]}..." if len(aname) > 35 else aname
                            bottoni.append([{
                                "text": f"🔗 {nome_bottone}",
                                "url": f"[https://runalyze.com/activity/](https://runalyze.com/activity/){aid}"
                            }])

                if bottoni:
                    tastiera_inline = {"inline_keyboard": bottoni}

                risposta_pulita = RE_RUNALYZE_LINKS.sub("", risposta_pulita).strip()

            inviato = self.notifier.send_message(
                risposta_pulita,
                reply_markup=tastiera_inline,
                chat_id=target_chat_id
            )
            if inviato:
                logger.info("🤖 [ORCHESTRATOR] Risposta inviata a Telegram con successo (chat_id=%s).", target_chat_id)
            else:
                logger.error("❌ [ORCHESTRATOR] Fallito invio risposta a Telegram (chat_id=%s).", target_chat_id)

        except Exception as e:
            logger.exception("💥 [ORCHESTRATOR] Errore nella gestione della chat AI: %s", e)
            self.notifier.send_message(
                "❌ Si è verificato un errore durante l'interazione con l'Agente.",
                chat_id=target_chat_id
            )

    def handle_sync_incrementale(self) -> None:
        """Deprecato: le corse sono lette in tempo reale via MCP."""
        self.notifier.send_message(
            "⚡ <b>Sincronizzazione non più necessaria!</b>\n"
            "Ora leggo tutte le tue corse e i km delle scarpe in tempo reale direttamente dal server MCP di Runalyze."
        )

    def handle_sync_storico(self, testo: str) -> None:
        self.handle_sync_incrementale()

    def handle_unrecognized_command(self) -> None:
        self.notifier.send_message(
            "Comando non riconosciuto. Scrivimi liberamente cosa vuoi analizzare, "
            "oppure usa i comandi /scarpe, /pianifica o /piano."
        )

    # ==========================================
    # 2. PIANIFICAZIONE SETTIMANALE (Firestore Nativo)
    # ==========================================
    def handle_plan_creation(self, testo: str) -> None:
        testo_piano = testo.removeprefix("/pianifica").strip()
        if not testo_piano:
            self.notifier.send_message(
                "⚠️ Usa il comando separando le sessioni con una riga vuota, ad esempio:\n\n"
                "/pianifica\nRiscaldamento 20'\nRipetute 10x100\n\nLungo 15km"
            )
            return

        blocchi_sessioni = RE_PLAN_BLOCKS.split(testo_piano)
        sessioni = []

        for blocco in blocchi_sessioni:
            blocco_clean = blocco.strip()
            if not blocco_clean:
                continue
            righe_step = [r.strip() for r in blocco_clean.splitlines() if r.strip()]
            idx = len(sessioni)
            sessioni.append({
                "id": idx,
                "name": f"Sessione {idx + 1}",
                "steps": righe_step,
                "status": "todo"
            })

        if self.db.save_weekly_plan_structured(sessioni):
            self.notifier.send_message(
                f"📝 <b>Piano Settimanale Creato!</b>\n\n"
                f"Ho elaborato <b>{len(sessioni)} sessioni</b>. Usa /piano per gestirle."
            )

    def handle_plan_view(self) -> None:
        piano = self.db.get_weekly_plan()
        if not piano or not piano.get("sessions"):
            self.notifier.send_message(
                "📝 Non hai ancora pianificato nulla per questa settimana. "
                "Inserisci il tuo piano con il comando /pianifica."
            )
            return

        linee_msg = [f"🗓️ <b>Il tuo Piano Settimanale ({piano['week_id']})</b>\n"]
        bottoni = []

        for s in piano["sessions"]:
            is_done = s.get("status") == "done"
            stato_icona = "✅" if is_done else "🟡"
            linee_msg.append(f"{stato_icona} <b>{s['name']}</b> (ID: {s['id']})")
            for step in s.get("steps", []):
                linee_msg.append(f"   • <i>{step}</i>")
            linee_msg.append("")

            sid = s["id"]
            if not is_done:
                bottoni.append([
                    {"text": "✅ Chiudi", "callback_data": f"man_done_{sid}"},
                    {"text": "❌ Elimina", "callback_data": f"del_sess_{sid}"}
                ])
            else:
                bottoni.append([
                    {"text": "↩️ Riapri", "callback_data": f"reopen_sess_{sid}"},
                    {"text": "❌ Elimina", "callback_data": f"del_sess_{sid}"}
                ])

        self.notifier.send_message(
            "\n".join(linee_msg),
            reply_markup={"inline_keyboard": bottoni} if bottoni else None
        )

    def handle_plan_modification(self, testo: str) -> None:
        """Gestisce il comando /modifica <id> <nuovi_step>."""
        parti = testo.removeprefix("/modifica").strip().splitlines()
        if not parti:
            self.notifier.send_message("⚠️ Formato: /modifica <ID_sessione> seguito dagli step su nuove righe.")
            return

        prima_riga = parti[0].strip().split(maxsplit=1)
        session_id = prima_riga[0]
        nuovi_step = ([prima_riga[1]] if len(prima_riga) > 1 else []) + [r.strip() for r in parti[1:] if r.strip()]

        if not nuovi_step:
            self.notifier.send_message("⚠️ Specifica almeno uno step per modificare la sessione.")
            return

        if self.db.edit_session(session_id, nuovi_step):
            self.notifier.send_message(f"✏️ Sessione {session_id} aggiornata! Usa /piano per verificare.")
        else:
            self.notifier.send_message(f"❌ Impossibile trovare o modificare la sessione {session_id}.")

    def toggle_session_status(self, session_id: str, action: str) -> None:
        if action == "done" and self.db.mark_session_as_done(session_id):
            self.notifier.send_message("🎯 Sessione completata! Usa /piano per aggiornare la vista.")
        elif action == "reopen" and self.db.reopen_session(session_id):
            self.notifier.send_message("↩️ Sessione riaperta! Usa /piano per aggiornare la vista.")
        elif action == "delete" and self.db.delete_session(session_id):
            self.notifier.send_message("🗑️ Sessione rimossa! Usa /piano per aggiornare la vista.")

    # ==========================================
    # 3. GESTIONE OCR FOTO BILANCIA (Firestore Nativo)
    # ==========================================
    def process_incoming_photo(self, photo_array: list[dict[str, Any]]) -> None:
        logger.info("📸 [ORCHESTRATOR] Ricevuta foto in chat. Avvio pipeline OCR...")
        file_id = photo_array[-1]["file_id"]
        self.notifier.send_message("🔍 Analisi visiva dello screenshot in corso...")
        image_bytes = self.notifier.download_file(file_id)

        if not image_bytes:
            self.notifier.send_message("❌ Impossibile scaricare l'immagine da Telegram.")
            return

        dati_corporei = self.analyst.extract_body_metrics_from_image(image_bytes)
        if dati_corporei and self.db.save_body_metrics(dati_corporei):
            runalyze_ok = (
                self.runalyze_client.upload_body_metrics(dati_corporei)
                if self.runalyze_client else False
            )
            badge_runalyze = (
                "✅ <b>Runalyze:</b> Sincronizzato"
                if runalyze_ok else "⚠️ <b>Runalyze:</b> Errore di sincronizzazione"
            )

            msg = (
                f"⚖️ <b>Metriche salvate su Firestore!</b>\n\n"
                f"📅 Data misurazione: {dati_corporei.get('data', 'N/D')}\n"
                f"⚖️ Peso: <b>{dati_corporei.get('peso_kg', 'N/D')} kg</b>\n"
                f"📊 IMC: {dati_corporei.get('imc', 'N/D')}\n"
                f"🟡 Massa Grassa: {dati_corporei.get('massa_grassa_percentuale', 'N/D')}%\n"
                f"🔴 Massa Muscolare: {dati_corporei.get('massa_muscolare_percentuale', 'N/D')}%\n"
                f"🦴 Massa Ossea: {dati_corporei.get('massa_ossea_percentuale', 'N/D')}%\n"
                f"💧 Massa Idrica: {dati_corporei.get('massa_idrica_percentuale', 'N/D')}%\n\n"
                f"☁️ <b>Firestore:</b> Aggiornato per l'Agent MCP\n"
                f"{badge_runalyze}"
            )
            self.notifier.send_message(msg)
        else:
            self.notifier.send_message("❌ Errore tecnico o formato illeggibile. Riprova.")

    # ==========================================
    # 4. GESTIONE ANALISI DELLE SCARPE (100% MCP)
    # ==========================================
    def process_shoe_list(self, chat_id: int | str | None = None) -> None:
        """
        Mostra la scarpiera oppure delega direttamente al server MCP di Runalyze.
        Se runalyze_client fornisce la lista con i km nativi di Runalyze, mostra i bottoni;
        altrimenti passa direttamente la richiesta all'Agente MCP.
        """
        try:
            logger.info("👟 [ORCHESTRATOR] Recupero scarpiera (Zero-Firestore)...")
            scarpe_api = self.runalyze_client.fetch_athlete_shoes() if self.runalyze_client else None

            if scarpe_api:
                bottoni = []
                for scarpa in scarpe_api:
                    nome = scarpa.get("name", "Scarpa Sconosciuta").strip()
                    # Runalyze restituisce solitamente 'distance' in km o metri nel payload gear
                    dist_raw = float(scarpa.get("distance") or 0.0)
                    # Se il valore è espresso in metri (> 5000), lo convertiamo in km
                    km_runalyze = dist_raw / 1000.0 if dist_raw > 5000 else dist_raw

                    label_km = f" ({km_runalyze:.0f} km)" if km_runalyze > 0 else ""
                    bottoni.append([{
                        "text": f"👟 {nome}{label_km}",
                        "callback_data": f"shoe_{scarpa['id']}"
                    }])

                messaggio = (
                    "👟 <b>La tua Scarpiera su Runalyze</b>\n\n"
                    "Seleziona un modello per avviare l'analisi tecnica dell'usura tramite Agente MCP:"
                )
                self.notifier.send_message(messaggio, reply_markup={"inline_keyboard": bottoni})
                return

            # Fallback o modalità pura MCP se non si usa il client REST per i bottoni
            prompt = (
                "Usa i tuoi tool MCP di Runalyze per recuperare l'elenco completo delle mie scarpe da corsa attive, "
                "indicando per ciascuna i chilometri percorsi, lo stato di usura rispetto al mio peso corporeo "
                "(presente nel contesto biometrico) e i tuoi consigli di rotazione."
            )
            self.handle_chat_ai(chat_id, prompt)

        except Exception as e:
            logger.exception("❌ [ORCHESTRATOR] Errore in process_shoe_list: %s", e)
            self.notifier.send_message(f"❌ Errore durante il recupero delle scarpe: {e}")

    def process_shoe_analysis(self, chat_id: int | str | None, gear_id: str) -> None:
        """
        Delega interamente al server MCP l'estrazione dei km, dei dettagli della scarpa
        e delle ultime corse effettuate con quel modello.
        """
        try:
            logger.info("🔍 [ORCHESTRATOR] Avvio analisi tecnica scarpa via MCP: %s", gear_id)

            # Recuperiamo opzionalmente il nome se disponibile via API rapida, altrimenti passiamo l'ID all'MCP
            nome_info = f"con ID Runalyze {gear_id}"
            if self.runalyze_client:
                gear_details = self.runalyze_client.fetch_gear_details(gear_id)
                if gear_details and gear_details.get("name"):
                    nome_info = f"'{gear_details['name']}' (ID Runalyze: {gear_id})"

            prompt = (
                f"Agisci come esperto di materiali da running. Valuta lo stato e l'usura della mia scarpa {nome_info}. "
                f"Usa i tuoi tool MCP di Runalyze per:\n"
                f"1. Recuperare i dettagli aggiornati e il chilometraggio totale effettivo di questa scarpa su Runalyze.\n"
                f"2. Verificare in quali tipologie di allenamenti o corse recenti l'ho utilizzata.\n"
                f"3. Incrociare i chilometri percorsi con il mio peso corporeo attuale (che trovi nel contesto biometrico) "
                f"per darmi un'analisi dettagliata dello stato di usura dell'intersuola/schiuma, quanti km di vita utile "
                f"le restano e se c'è rischio infortuni."
            )

            self.handle_chat_ai(chat_id, prompt)

        except Exception as e:
            logger.exception("❌ [ORCHESTRATOR] Errore in process_shoe_analysis: %s", e)
            self.notifier.send_message(f"❌ Errore durante l'ispezione della scarpa: {e}")

    # ==========================================
    # 5. DELEGA ALL'AGENTE (MCP)
    # ==========================================
    def process_cron_weekly_report(self, chat_id: int | str | None = None) -> None:
        """Il cron job innesca un prompt per l'Agente."""
        self.notifier.send_message("⏰ Avvio l'elaborazione del report settimanale tramite Agente MCP...")
        prompt = (
            "Genera il report settimanale dettagliato per la settimana in corso. "
            "Usa i tuoi tool MCP per recuperare le ultime attività da Runalyze, filtra solo quelle degli ultimi 7 giorni, "
            "calcola il chilometraggio totale e analizza i trend. Dimmi cosa ne pensi da coach."
        )
        self.handle_chat_ai(chat_id or self.default_chat_id, prompt)

    def process_fallback_weekly_report(self) -> None:
        self.process_cron_weekly_report(self.default_chat_id)

    def handle_fallback_ignore(self) -> None:
        self.notifier.send_message("👌 Ricevuto, report della scorsa settimana ignorato.")

    def process_run_analysis(self, activity_id: str, chat_id: int | str | None = None) -> None:
        """Analisi di una singola corsa richiamata tramite ID via MCP."""
        self.notifier.send_message(f"🔍 Ho passato l'attività {activity_id} all'Agente per l'analisi...")
        prompt = (
            f"Usa i tuoi tool MCP per recuperare tutti i dettagli dell'attività Runalyze con ID {activity_id}. "
            f"Fammi un'analisi tecnica profonda."
        )
        self.handle_chat_ai(chat_id or self.default_chat_id, prompt)
