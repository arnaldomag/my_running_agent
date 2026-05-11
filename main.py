import os
import requests
from dotenv import load_dotenv

# 1. Carica le chiavi in modo sicuro dal file .env
load_dotenv()

CLIENT_ID = os.getenv('STRAVA_CLIENT_ID')
CLIENT_SECRET = os.getenv('STRAVA_CLIENT_SECRET')


def get_strava_tokens():
    # FASE 1: Generazione del link di autorizzazione
    # Chiediamo lo scope 'activity:read_all' per poter leggere tutte le corse e i tag
    auth_url = (
        f"https://www.strava.com/oauth/authorize?"
        f"client_id={CLIENT_ID}&"
        f"response_type=code&"
        f"redirect_uri=http://localhost/callback&"
        f"approval_prompt=force&"
        f"scope=activity:read_all,activity:write"
    )

    print("\n=== FASE 1: RICHIESTA ACCESSO ===")
    print("Tieni premuto CTRL e clicca su questo link (o copialo nel browser):")
    print(f"\n{auth_url}\n")
    print("1. Clicca su 'Autorizza' nella pagina di Strava.")
    print("2. Il browser cercherà di caricare 'localhost' e probabilmente darà errore (È NORMALE!).")
    print("3. Guarda l'URL nella barra degli indirizzi e copia la stringa di testo subito dopo 'code='")

    # Aspettiamo che tu inserisca il codice copiato dall'URL
    auth_code = input("\nIncolla qui il 'code' copiato dall'URL: ")

    # FASE 2: Scambio del codice temporaneo con i Token definitivi
    token_url = "https://www.strava.com/oauth/token"
    payload = {
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'code': auth_code.strip(), # strip() rimuove eventuali spazi copiati per sbaglio
        'grant_type': 'authorization_code'
    }

    print("\n=== FASE 2: ELABORAZIONE TOKEN ===")
    response = requests.post(token_url, data=payload)

    if response.status_code == 200:
        dati = response.json()
        print("\n✅ Successo! Hai estratto i tuoi token:")
        print(f"Access Token:  {dati['access_token']}")
        print(f"Refresh Token: {dati['refresh_token']}")
        print("\nConserva questi token! Ci serviranno per lo step successivo.")
    else:
        print("\n❌ Errore durante la chiamata API:")
        print(response.json())

if __name__ == "__main__":
    get_strava_tokens()