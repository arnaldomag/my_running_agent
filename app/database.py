import logging
from datetime import date
from typing import Any

from google import genai
from google.cloud import firestore

from .config import config

logger = logging.getLogger(__name__)


class RunningDB:
    MAX_HISTORY_LENGTH = 10

    def __init__(self):
        self.db = firestore.Client(project=config.project_id, database="my-running-agent")

    # ==========================================
    # 1. GESTIONE CRONOLOGIA AI (CHAT)
    # ==========================================
    def get_chat_history(self, chat_id: int | str) -> tuple[list[genai.types.Content], list[dict[str, Any]]]:
        """Recupera la cronologia dei messaggi e la converte in oggetti Content dell'SDK."""
        try:
            doc = self.db.collection("ai_chats").document(str(chat_id)).get()
            if not doc.exists:
                return [], []

            history_dicts: list[dict[str, Any]] = doc.to_dict().get("history", [])
            contents = [
                genai.types.Content(
                    role=msg["role"],
                    parts=[genai.types.Part.from_text(
                        text=msg["parts"][0] if isinstance(msg["parts"], list) else msg["parts"]
                    )]
                )
                for msg in history_dicts
            ]
            return contents, history_dicts
        except Exception as e:
            logger.error("❌ [DATABASE] Errore nel recupero della cronologia chat: %s", e)
            return [], []

    def save_chat_interaction(
        self,
        chat_id: int | str,
        history_dicts: list[dict[str, Any]],
        user_text: str,
        bot_reply: str
    ) -> bool:
        """Aggiorna l'array della cronologia mantenendo al massimo gli ultimi 10 messaggi."""
        try:
            doc_ref = self.db.collection("ai_chats").document(str(chat_id))

            history_dicts.append({"role": "user", "parts": [user_text]})
            history_dicts.append({"role": "model", "parts": [bot_reply]})

            if len(history_dicts) > self.MAX_HISTORY_LENGTH:
                history_dicts = history_dicts[-self.MAX_HISTORY_LENGTH:]

            doc_ref.set({
                "last_updated": firestore.SERVER_TIMESTAMP,
                "history": history_dicts
            }, merge=True)
            return True
        except Exception as e:
            logger.error("❌ [DATABASE] Errore nel salvataggio della cronologia chat: %s", e)
            return False

    def run_test_write(self) -> bool:
        doc_ref = self.db.collection("health_checks").document("current")
        doc_ref.set({
            "status": "healthy",
            "last_check": firestore.SERVER_TIMESTAMP
        })
        return True

    # ==========================================
    # 2. GESTIONE METRICHE CORPOREE (BILANCIA)
    # ==========================================
    def save_body_metrics(self, metrics_data: dict[str, Any]) -> bool:
        try:
            doc_id = metrics_data.get("data", "data_sconosciuta").replace(" ", "_").lower()
            doc_ref = self.db.collection("metrics").document(doc_id)

            payload = {**metrics_data, "timestamp": firestore.SERVER_TIMESTAMP}
            doc_ref.set(payload)
            logger.info("✅ [DATABASE] Metriche salvate su Firestore con ID Doc: %s", doc_id)
            return True
        except Exception as e:
            logger.error("❌ [DATABASE] Errore durante il salvataggio metriche: %s", e)
            return False

    def get_latest_weight(self, return_full_dict: bool = False) -> dict[str, Any] | float | None:
        """Recupera l'ultima misurazione corporea (intero dict o solo float peso_kg)."""
        try:
            docs = (
                self.db.collection("metrics")
                .order_by("timestamp", direction=firestore.Query.DESCENDING)
                .limit(1)
                .get()
            )
            doc_data = docs[0].to_dict() if docs else None

            if not doc_data:
                docs_fallback = self.db.collection("metrics").limit(1).get()
                doc_data = docs_fallback[0].to_dict() if docs_fallback else None

            if doc_data:
                return doc_data if return_full_dict else doc_data.get("peso_kg")
            return None
        except Exception as e:
            logger.error("❌ [DATABASE] Errore nel recupero delle metriche corporee: %s", e)
            return None

    # ==========================================
    # 3. GESTIONE PIANIFICAZIONE SETTIMANALE
    # ==========================================
    @staticmethod
    def get_current_week_id() -> str:
        anno, settimana, _ = date.today().isocalendar()
        return f"{anno}_W{settimana}"

    def save_weekly_plan_structured(self, sessions_list: list[dict[str, Any]]) -> bool:
        try:
            week_id = self.get_current_week_id()
            doc_ref = self.db.collection("training_plans").document(week_id)
            doc_ref.set({
                "week_id": week_id,
                "last_modified": firestore.SERVER_TIMESTAMP,
                "sessions": sessions_list
            })
            return True
        except Exception as e:
            logger.error("❌ [DATABASE] Errore nel salvataggio del piano strutturato: %s", e)
            return False

    def get_weekly_plan(self) -> dict[str, Any] | None:
        try:
            week_id = self.get_current_week_id()
            doc = self.db.collection("training_plans").document(week_id).get()
            return doc.to_dict() if doc.exists else None
        except Exception as e:
            logger.error("❌ [DATABASE] Errore recupero piano: %s", e)
            return None

    def _update_session_action(
        self,
        session_id: int | str,
        action: str,
        nuovi_step: list[str] | None = None
    ) -> bool:
        """Motore centrale per aggiornare stato o contenuto di una sessione."""
        try:
            week_id = self.get_current_week_id()
            doc_ref = self.db.collection("training_plans").document(week_id)
            doc = doc_ref.get()

            if not doc.exists:
                return False

            data = doc.to_dict()
            sessioni: list[dict[str, Any]] = data.get("sessions", [])
            target_id = str(session_id)
            aggiornato = False

            if action == "delete":
                sessioni_filtrate = [s for s in sessioni if str(s.get("id")) != target_id]
                if len(sessioni_filtrate) < len(sessioni):
                    data["sessions"] = sessioni_filtrate
                    aggiornato = True
            else:
                for s in sessioni:
                    if str(s.get("id")) == target_id:
                        if action == "done":
                            s["status"] = "done"
                        elif action == "reopen":
                            s["status"] = "todo"
                        elif action == "edit" and nuovi_step is not None:
                            s["status"] = "todo"
                            s["steps"] = nuovi_step
                        aggiornato = True
                        break

            if aggiornato:
                data["last_modified"] = firestore.SERVER_TIMESTAMP
                doc_ref.set(data)
                return True
            return False
        except Exception as e:
            logger.error("❌ [DATABASE] Errore nell'operazione '%s' sulla sessione %s: %s", action, session_id, e)
            return False

    def mark_session_as_done(self, session_id: int | str) -> bool:
        return self._update_session_action(session_id, action="done")

    def reopen_session(self, session_id: int | str) -> bool:
        return self._update_session_action(session_id, action="reopen")

    def edit_session(self, session_id: int | str, nuovi_step: list[str]) -> bool:
        return self._update_session_action(session_id, action="edit", nuovi_step=nuovi_step)

    def delete_session(self, session_id: int | str) -> bool:
        return self._update_session_action(session_id, action="delete")


db = RunningDB()
