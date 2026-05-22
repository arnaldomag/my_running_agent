from google.cloud import firestore
from .config import config
from datetime import date, datetime, timezone
from google import genai

class RunningDB:
    def __init__(self):
        self.db = firestore.Client(project=config.project_id, database="my-running-agent")
        self.collection_name = "activities"
    def get_chat_history(self, chat_id):
        """Recupera la cronologia dei messaggi e la converte in oggetti Content dell'SDK"""
        try:
            doc_ref = self.db.collection("ai_chats").document(str(chat_id))
            doc = doc_ref.get()
            
            history_dicts = []
            if doc.exists:
                history_dicts = doc.to_dict().get("history", [])
                
            # Convertiamo i dizionari piatti in oggetti genai.types.Content richiesti dall'SDK unificato
            contents = []
            for msg in history_dicts:
                # Gestione di sicurezza sulla struttura delle parti
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
            
            # Appendiamo i nuovi messaggi alla lista dei dizionari esistenti
            history_dicts.append({"role": "user", "parts": [user_text]})
            history_dicts.append({"role": "model", "parts": [bot_reply]})
            
            # Applichiamo il limite massimo della rolling window (10 messaggi = 5 interazioni complete)
            MAX_HISTORY_LENGTH = 10
            if len(history_dicts) > MAX_HISTORY_LENGTH:
                history_dicts = history_dicts[-MAX_HISTORY_LENGTH:]
                
            # Scrittura atomica su Firestore
            doc_ref.set({
                "last_updated": datetime.now(timezone.utc),
                "history": history_dicts
            }, merge=True)
            
            print(f"💾 [DATABASE] Cronologia chat aggiornata per chat_id: {chat_id}")
            return True
        except Exception as e:
            print(f"❌ [DATABASE] Errore nel salvataggio della cronologia chat: {e}")
            return False
    
    def run_test_write(self):
        """Funzione di test per verificare la scrittura"""
        doc_ref = self.db.collection('health_checks').document('current')
        # Usiamo il timestamp del server di Google
        doc_ref.set({
            "status": "healthy",
            "last_check": firestore.SERVER_TIMESTAMP 
        })
        return True

    def update_activity(self, activity_data):
        """Salva o aggiorna un'attività usando l'ID di Strava"""
        activity_id = str(activity_data.get('id'))
        if not activity_id:
            print("❌ Impossibile salvare: ID attività mancante.")
            return
        
        doc_ref = self.db.collection(self.collection_name).document(activity_id)
        # set con merge=True evita di sovrascrivere dati esistenti se ne aggiungiamo di nuovi
        doc_ref.set(activity_data, merge=True)
        print(f"✅ Attività {activity_id} sincronizzata su Firestore.")

    def get_recent_runs(self, limit=10):
        """Recupera le ultime corse salvate"""
        docs = self.db.collection(self.collection_name)\
                      .order_by("start_date", direction=firestore.Query.DESCENDING)\
                      .limit(limit).stream()
        return [doc.to_dict() for doc in docs]

    def save_body_metrics(self, metrics_data):
        """Salva le metriche corporee su Firestore nella collezione 'metrics'"""
        try:
            # Crea un ID documento pulito partendo dalla data (es: "sabato_16_maggio_2026")
            doc_id = metrics_data.get("data", "data_sconosciuta").replace(" ", "_").lower()
            
            # Riferimento alla collezione 'metrics' su Firestore
            doc_ref = self.db.collection("metrics").document(doc_id)
            
            # Inseriamo i dati
            doc_ref.set(metrics_data)
            print(f"✅ [DATABASE] Metriche salvate su Firestore con ID Doc: {doc_id}")
            return True
        except Exception as e:
            print(f"❌ [DATABASE] Errore durante il salvataggio su Firestore: {e}")
            return False

    def get_latest_weight(self):
        """Recupera il peso corporeo più recente salvato in Firestore"""
        try:
            # Recuperiamo un documento dalla collezione metrics
            docs = self.db.collection("metrics").limit(1).get()
            for doc in docs:
                data = doc.to_dict()
                return data.get("peso_kg")
            return None
        except Exception as e:
            print(f"❌ [DATABASE] Errore nel recupero del peso: {e}")
            return None

    def get_current_week_id(self):
        """Calcola l'ID univoco per la settimana in corso (es: '2026_W21')"""
        oggi = date.today()
        anno, settimana, giorno_settimana = oggi.isocalendar()
        return f"{anno}_W{settimana}"

    def save_weekly_plan(self, workouts):
        """Salva il piano di allenamento per la settimana in corso"""
        try:
            week_id = self.get_current_week_id()
            doc_ref = self.db.collection("training_plans").document(week_id)
            
            # Creiamo una struttura per ogni allenamento
            plan_data = {
                "week_id": week_id,
                "workouts": []
            }
            
            for i, workout_text in enumerate(workouts):
                plan_data["workouts"].append({
                    "id": i, # Un indice semplice (0, 1, 2...)
                    "descrizione": workout_text.strip(),
                    "status": "todo", # Può essere 'todo' o 'done'
                    "run_id": None # Qui salveremo l'ID di Strava quando lo assocerai
                })
                
            doc_ref.set(plan_data)
            return True
        except Exception as e:
            print(f"❌ [DATABASE] Errore salvataggio piano: {e}")
            return False

    def get_weekly_plan(self):
        """Recupera il piano della settimana in corso"""
        try:
            week_id = self.get_current_week_id()
            doc = self.db.collection("training_plans").document(week_id).get()
            if doc.exists:
                return doc.to_dict()
            return None
        except Exception as e:
            print(f"❌ [DATABASE] Errore recupero piano: {e}")
            return None

    def mark_workout_as_done(self, workout_id):
        """Segna un allenamento come completato (MVP dell'associazione)"""
        try:
            week_id = self.get_current_week_id()
            doc_ref = self.db.collection("training_plans").document(week_id)
            doc = doc_ref.get()
            
            if doc.exists:
                data = doc.to_dict()
                # Cerchiamo l'allenamento con l'ID corrispondente e lo aggiorniamo
                for w in data["workouts"]:
                    if str(w["id"]) == str(workout_id):
                        w["status"] = "done"
                        break
                
                doc_ref.set(data)
                return True
            return False
        except Exception as e:
            print(f"❌ [DATABASE] Errore aggiornamento status allenamento: {e}")
            return False

# Istanza pronta all'uso
db = RunningDB()
