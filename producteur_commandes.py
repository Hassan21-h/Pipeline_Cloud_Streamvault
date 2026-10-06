import os
import time
import json
import random
from datetime import datetime
from pymongo import MongoClient
from azure.eventhub import EventHubProducerClient, EventData
from dotenv import load_dotenv

load_dotenv()

# -------------------------------------------------------------------------
# 1. Configuration des connexions 
# -------------------------------------------------------------------------
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
EVENTHUB_CONNECTION_STR = os.getenv(
    "EVENTHUB_CONNECTION_STR", 
    "Endpoint=sb://<your-eventhub-namespace>.servicebus.windows.net/;SharedAccessKeyName=RootManageSharedAccessKey;SharedAccessKey=<your-key>"
)
EVENTHUB_NAME = os.getenv("EVENTHUB_NAME", "commandes")

# -------------------------------------------------------------------------
# 2. Chargement du catalogue réel depuis MongoDB
# -------------------------------------------------------------------------
print("Connexion à MongoDB et chargement des données...")
mongo_client = MongoClient(MONGO_URI)
db = mongo_client["StreamVaultDB"]

# Extraction des clients et du catalogue (Films + Livres)
clients = list(db["Clients"].find({}, {"_id": 1, "nom": 1, "prenom": 1}))
medias = list(db["FilmsEtLivres"].find({}, {"_id": 1, "title": 1, "prix": 1, "price": 1, "type": 1}))

if not clients or not medias:
    raise ValueError("Erreur : Les collections MongoDB 'Clients' ou 'FilmsEtLivres' sont vides !")

print(f"Catalogue chargé : {len(clients)} clients et {len(medias)} médias trouvés.")

# -------------------------------------------------------------------------
# 3. Producteur Event Hubs (Envoi en temps réel tous les 3s)
# -------------------------------------------------------------------------
producer = EventHubProducerClient.from_connection_string(
    conn_str=EVENTHUB_CONNECTION_STR,
    eventhub_name=EVENTHUB_NAME
)

id_commande = 1000

print("Démarrage du flux de commandes vers Event Hubs (Appuie sur Ctrl+C pour arrêter)...")

try:
    with producer:
        while True:
            # Sélection d'un VRAI client et d'un VRAI média
            c = random.choice(clients)
            m = random.choice(medias)
            media_id_str = str(m["_id"])

            # Récupération ou calcul d'un prix fixe et stable par titre
            if "prix" in m:
                prix_unitaire = float(m["prix"])
            elif "price" in m:
                prix_unitaire = float(m["price"])
            else:
                # Prix déterministe basé sur l'_id (toujours identique pour le même film/livre)
                prix_unitaire = round(5.0 + (abs(hash(media_id_str)) % 2000) / 100.0, 2)

            # Construction du message JSON
            commande = {
                "id_commande": f"CMD-{id_commande}",
                "timestamp": datetime.utcnow().isoformat(),
                "client_id": str(c["_id"]),
                "client_nom": f"{c.get('prenom', '')} {c.get('nom', '')}".strip(),
                "media_id": media_id_str,
                "titre": m.get("title", "Titre inconnu"),
                "type_media": m.get("type", "inconnu"),
                "prix_unitaire": prix_unitaire
            }

            # Envoi vers Azure Event Hubs
            batch = producer.create_batch()
            batch.add(EventData(json.dumps(commande)))
            producer.send_batch(batch)

            print(f"[{datetime.now().strftime('%H:%M:%S')}] Commande envoyée : {commande['id_commande']} | Client: {commande['client_nom']} | Article: {commande['titre']} ({commande['prix_unitaire']} €)")

            id_commande += 1
            time.sleep(3)

except KeyboardInterrupt:
    print("\nArrêt du producteur de commandes.")