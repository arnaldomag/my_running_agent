import os
import sys

# Diciamo a Python di considerare la cartella principale del progetto
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# Importiamo l'istanza ufficiale del database
from app.database import db

def rinomina_scarpe():
    print("🔄 Inizio procedura di rinomina scarpe su Firestore...")
    
    # ================================================================
    # 1. IMPOSTA QUI LA TUA MAPPA DI RINOMINAZIONE
    # Formato: "Vecchio Nome Sbagliato": "Nuovo Nome Esatto"
    # ================================================================
    mappa_rinomina = {
        "Saucony Endorphin Speed 5 SauconyEndorphinSpeed5": "Saucony Endorphin Speed 5",
        "Adidas Adizero Boston 13 AdidasAdizeroBoston13": "Adidas Adizero Boston 13",
        "HOKA One One Rocket X 3": "Hoka One One Rocket X 3",
        "N/D": "Scarpa running generica" # Esempio se vuoi cambiare i "N/D"
        # Aggiungi tutte le righe che vuoi, separate da virgola
    }
    
    firestore_client = db.db
    
    print("📊 Lettura delle attività storiche da Firestore in corso...")
    corse_ref = firestore_client.collection("activities").stream()
    
    corse_aggiornate = 0
    
    for doc in corse_ref:
        dati_corsa = doc.to_dict()
        scarpa_attuale = dati_corsa.get("scarpe")
        
        # Se la scarpa attuale è presente nella nostra lista dei "vecchi nomi"
        if scarpa_attuale in mappa_rinomina:
            nuovo_nome = mappa_rinomina[scarpa_attuale]
            
            print(f"✏️ Aggiorno {dati_corsa.get('start_date')}: '{scarpa_attuale}' -> '{nuovo_nome}'")
            
            # Eseguiamo l'aggiornamento su Firestore
            firestore_client.collection("activities").document(doc.id).update({
                "scarpe": nuovo_nome
            })
            
            corse_aggiornate += 1
            
    print("\n" + "="*50)
    print(f"✅ RINOMINA COMPLETATA: {corse_aggiornate} corse aggiornate con successo!")
    print("="*50 + "\n")

if __name__ == "__main__":
    rinomina_scarpe()