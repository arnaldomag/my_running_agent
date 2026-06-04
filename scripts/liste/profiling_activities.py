import os
import sys
import pandas as pd

# Puntiamo alla cartella principale
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from app.database import db

def analizza_struttura():
    print("📊 Estrazione dati da Firestore in corso...")
    firestore_client = db.db
    
    # Leggiamo tutta la collection
    corse_ref = firestore_client.collection("activities").stream()
    
    # Trasformiamo i documenti in una lista di dizionari
    dati = [doc.to_dict() for doc in corse_ref]
    
    if not dati:
        print("La tabella è vuota.")
        return
        
    # Magia: convertiamo tutto in un DataFrame Pandas
    df = pd.DataFrame(dati)
    
    print("\n" + "="*50)
    print("📋 SCHEMA E TIPI DI DATO (PROFILING)")
    print("="*50)
    # df.info() ti dirà esattamente quante colonne ci sono, quanti valori non nulli e il tipo di dato
    print(df.info())
    
    print("\n" + "="*50)
    print("🔍 VALORI MANCANTI PER COLONNA")
    print("="*50)
    print(df.isnull().sum()[df.isnull().sum() > 0]) # Mostra solo le colonne che hanno dei "buchi"
    
    # print("\n" + "="*50)
    # print("👟 SCARPE PIÙ UTILIZZATE (DISTRIBUZIONE)")
    # print("="*50)
    # if 'scarpe' in df.columns:
    #     print(df['scarpe'].value_counts())

def select_all():
    # 1. Inizializza il client del database
    firestore_client = db.db
    
    # 2. Questa è la vera e propria "SELECT * FROM activities"
    corse_ref = firestore_client.collection("activities").stream()
    
    # 3. I dati arrivano grezzi, dobbiamo "scartarli" ed estrarli
    risultati = []
    for doc in corse_ref:
        dati_riga = doc.to_dict()   # Trasforma il documento in un dizionario Python (le tue "colonne")
        dati_riga['id_doc'] = doc.id # Opzionale: aggiungiamo l'ID interno del documento
        risultati.append(dati_riga)
        
    # Risultato finale
    print(f"✅ Esecuzione completata: trovate {len(risultati)} righe (documenti).")
    
    # Stampiamo la prima riga per farti vedere i dati
    if risultati:
        print("\nEcco la prima riga estratta:")
        print(risultati[0])
    
if __name__ == "__main__":
    # Assicurati di aver installato pandas: pip install pandas
    analizza_struttura()
    # select_all()