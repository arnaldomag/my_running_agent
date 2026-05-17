from google.cloud import firestore
from .config import config

class RunningDB:
    def __init__(self):
        self.db = firestore.Client(project=config.project_id, database="my-running-agent")
        self.collection_name = "activities"

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

# Istanza pronta all'uso
db = RunningDB()