from google.cloud import firestore
from .config import config
from datetime import date, datetime, timezone
from google import genai

class RunningDB:
    def __init__(self):
        self.db = firestore.Client(project=config.project_id, database="my-running-agent")
        # Puntamento aggiornato alla nuova tabella Runalyze
        self.collection_name = "attivita"

    # ==========================================
    # 1. GESTIONE CRONOLOGIA AI (CHAT)
    # ==========================================
    def get_chat_history(self, chat_id):
        """Recupera la cronologia dei messaggi e la converte in oggetti Content dell'SDK"""
        try:
            doc_ref = self.db.collection("ai_chats").document(str(chat_id))
            doc = doc_ref.get()
            
            history_dicts = []
            if doc.exists:
                history_dicts = doc.to_dict().get("history", [])
                
            contents = []
            for msg in history_dicts:
                text_part = msg["parts"][0] if isinstance(msg["parts"], list) else msg["parts"]
                content_obj = genai.types.Content(
                    role=msg["role"],
                    parts=[genai.types.Part.from_text(text=text_part)]
                )
                contents.append(content_obj)
                
            return contents, history_dicts
        except Exception as e:
            print(f"❌ [DATABASE] Errore nel recupero della cronologia chat: {e}")
            return [], []

    def save_chat_interaction(self, chat_id, history_dicts, user_text, bot_reply):
        """Aggiorna l'array della cronologia mantenendo al massimo gli ultimi 10 messaggi"""
        try:
            doc_ref = self.db.collection("ai_chats").document(str(chat_id))
            
            history_dicts.append({"role": "user", "parts": [user_text]})
            history_dicts.append({"role": "model", "parts": [bot_reply]})
            
            MAX_HISTORY_LENGTH = 10
            if len(history_dicts) > MAX_HISTORY_LENGTH:
                history_dicts = history_dicts[-MAX_HISTORY_LENGTH:]
                
            doc_ref.set({
                "last_updated": firestore.SERVER_TIMESTAMP,
                "history": history_dicts
            }, merge=True)
            
            return True
        except Exception as e:
            print(f"❌ [DATABASE] Errore nel salvataggio della cronologia chat: {e}")
            return False

    def run_test_write(self):
        doc_ref = self.db.collection('health_checks').document('current')
        doc_ref.set({
            "status": "healthy",
            "last_check": firestore.SERVER_TIMESTAMP 
        })
        return True

    # ==========================================
    # 2. GESTIONE ATTIVITÀ RUNALYZE (ETL)
    # ==========================================
    def update_activity(self, activity_data):
        activity_id = str(activity_data.get('id'))
        if not activity_id:
            print("❌ Impossibile salvare: ID attività mancante.")
            return
        
        doc_ref = self.db.collection(self.collection_name).document(activity_id)
        doc_ref.set(activity_data, merge=True)
        print(f"✅ Attività {activity_id} sincronizzata su Firestore.")

    def get_recent_runs(self, limit=10):
        docs = self.db.collection(self.collection_name)\
                      .order_by("start_date", direction=firestore.Query.DESCENDING)\
                      .limit(limit).stream()
        return [doc.to_dict() for doc in docs]

    # ==========================================
    # 3. GESTIONE METRICHE CORPOREE (BILANCIA)
    # ==========================================
    def save_body_metrics(self, metrics_data):
        try:
            doc_id = metrics_data.get("data", "data_sconosciuta").replace(" ", "_").lower()
            doc_ref = self.db.collection("metrics").document(doc_id)
            
            # AGGIUNTA CRITICA: Inseriamo il timestamp del server per poter estrarre l'ultimo peso!
            metrics_data["timestamp"] = firestore.SERVER_TIMESTAMP
            
            doc_ref.set(metrics_data)
            print(f"✅ [DATABASE] Metriche salvate su Firestore con ID Doc: {doc_id}")
            return True
        except Exception as e:
            print(f"❌ [DATABASE] Errore durante il salvataggio su Firestore: {e}")
            return False

    def get_latest_weight(self, return_full_dict=False):
        """
        Recupera l'ultima misurazione corporea.
        Di default restituisce solo il peso in kg (float) per retrocompatibilità.
        Se return_full_dict=True, restituisce l'intero dizionario con tutte le metriche.
        """
        try:
            doc_data = None
            
            # 1. Tentativo con ordine decrescente (funziona per i nuovi record salvati con il timestamp)
            docs = self.db.collection("metrics").order_by("timestamp", direction=firestore.Query.DESCENDING).limit(1).get()
            for doc in docs:
                doc_data = doc.to_dict()
                break  # Trovato il primo, esce dal ciclo
                
            # 2. Fallback per i vecchi record (senza timestamp, estrae il primo disponibile)
            if not doc_data:
                docs_fallback = self.db.collection("metrics").limit(1).get()
                for doc in docs_fallback:
                    doc_data = doc.to_dict()
                    break

            # 3. Restituzione del risultato in base al parametro richiesto
            if doc_data:
                if return_full_dict:
                    return doc_data  # Restituisce tutto: massa ossea, idrica, grassa, ecc.
                else:
                    return doc_data.get("peso_kg")  # Comportamento classico: restituisce solo il numero
                    
            return None
        except Exception as e:
            print(f"❌ [DATABASE] Errore nel recupero delle metriche corporee: {e}")
            return None

    # ==========================================
    # 4. GESTIONE PIANIFICAZIONE SETTIMANALE
    # ==========================================
    def get_current_week_id(self):
        oggi = date.today()
        anno, settimana, giorno_settimana = oggi.isocalendar()
        return f"{anno}_W{settimana}"

    def save_weekly_plan_structured(self, sessions_list):
        try:
            week_id = self.get_current_week_id()
            doc_ref = self.db.collection("training_plans").document(week_id)
            
            plan_data = {
                "week_id": week_id,
                "last_modified": firestore.SERVER_TIMESTAMP,
                "sessions": sessions_list
            }
            
            doc_ref.set(plan_data)
            return True
        except Exception as e:
            print(f"❌ [DATABASE] Errore nel salvataggio del piano strutturato: {e}")
            return False

    def get_weekly_plan(self):
        try:
            week_id = self.get_current_week_id()
            doc = self.db.collection("training_plans").document(week_id).get()
            if doc.exists:
                return doc.to_dict()
            return None
        except Exception as e:
            print(f"❌ [DATABASE] Errore recupero piano: {e}")
            return None

    # --- METODO PRIVATO UNIFICATO PER MODIFICARE LE SESSIONI (DRY PRINCIPLE) ---
    def _update_session_action(self, session_id, action, nuovi_step=None):
        """Motore centrale che esegue tutte le operazioni (done, reopen, edit, delete) su una sessione"""
        try:
            week_id = self.get_current_week_id()
            doc_ref = self.db.collection("training_plans").document(week_id)
            doc = doc_ref.get()
            
            if not doc.exists:
                return False
                
            data = doc.to_dict()
            sessioni = data.get("sessions", [])
            aggiornato = False
            
            if action == "delete":
                # Filtra via la sessione da eliminare
                sessioni_filtrate = [s for s in sessioni if str(s["id"]) != str(session_id)]
                if len(sessioni_filtrate) < len(sessioni):
                    data["sessions"] = sessioni_filtrate
                    aggiornato = True
            else:
                # Modifica la sessione trovata
                for s in sessioni:
                    if str(s["id"]) == str(session_id):
                        if action == "done":
                            s["status"] = "done"
                        elif action == "reopen":
                            s["status"] = "todo"
                        elif action == "edit":
                            s["status"] = "todo"
                            s["steps"] = nuovi_step
                        aggiornato = True
                        break
            
            if aggiornato:
                doc_ref.set(data)
                return True
            return False
        except Exception as e:
            print(f"❌ [DATABASE] Errore nell'operazione '{action}' sulla sessione {session_id}: {e}")
            return False

    # --- LE 4 FUNZIONI PUBBLICHE DIVENTATE MONORIGA GRAZIE AL METODO UNIFICATO ---
    
    def mark_session_as_done(self, session_id):
        return self._update_session_action(session_id, action="done")

    def reopen_session(self, session_id):
        return self._update_session_action(session_id, action="reopen")

    def edit_session(self, session_id, nuovi_step):
        return self._update_session_action(session_id, action="edit", nuovi_step=nuovi_step)

    def delete_session(self, session_id):
        return self._update_session_action(session_id, action="delete")

# Istanza pronta all'uso esportata come singleton
db = RunningDB()