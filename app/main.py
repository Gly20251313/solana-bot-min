import os
import base58
import requests
from apscheduler.schedulers.background import BackgroundScheduler
from solana.keypair import Keypair
from solana.rpc.api import Client
import pytz

# Variables d'environnement
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT  = os.getenv("TELEGRAM_CHAT_ID")
TZ    = os.getenv("TZ", "Europe/Paris")

# Fonction envoi Telegram
def send(msg: str):
    if not TOKEN or not CHAT:
        print("[warn] Telegram non configuré")
        return
    try:
        requests.get(
            f"https://api.telegram.org/bot{TOKEN}/sendMessage",
            params={"chat_id": CHAT, "text": msg},
            timeout=10
        )
    except Exception as e:
        print("[error] Telegram:", e)

# Décodage clé privée
def _decode_private_key(pk_str: str) -> bytes:
    try:
        return base58.b58decode(pk_str)
    except Exception:
        try:
            # format JSON Phantom
            import json
            arr = json.loads(pk_str)
            return bytes(arr)
        except Exception as e:
            raise ValueError(f"Format clé invalide: {e}")

# Lecture solde wallet
def get_wallet_balance():
    pk_str = os.getenv("SOLANA_PRIVATE_KEY")
    if not pk_str:
        return "[erreur] SOLANA_PRIVATE_KEY manquante"

    secret = _decode_private_key(pk_str)
    print(f"[debug] Longueur clé: {len(secret)} octets")
    print(f"[debug] Bytes: {list(secret)}")

    # Normaliser en seed 32 octets
    if len(secret) >= 32:
        seed32 = secret[:32]
    else:
        return f"[erreur] Clé trop courte ({len(secret)}B), besoin ≥ 32B"

    kp = Keypair.from_seed(seed32)  # ✅

    rpc_url = os.getenv("RPC_URL", "https://api.mainnet-beta.solana.com")
    print(f"[debug] RPC_URL: {rpc_url}")
    print(f"[debug] Public key: {kp.pubkey()}")

    client = Client(rpc_url)
    resp = client.get_balance(kp.pubkey())
    print(f"[debug] Réponse RPC: {resp}")

    try:
        lamports = resp.value
    except AttributeError:
        lamports = resp["result"]["value"]

    balance_sol = lamports / 1_000_000_000
    return f"💰 Solde wallet BOT: {balance_sol:.4f} SOL (pubkey: {kp.pubkey()})"

# Tâche planifiée
def job_balance():
    send(get_wallet_balance())

# Message de démarrage
send("🚀 Bot prêt ✅ (Railway)")

# Scheduler
scheduler = BackgroundScheduler(timezone=pytz.timezone(TZ))
scheduler.add_job(job_balance, 'interval', minutes=1)  # toutes les minutes pour test
scheduler.start()

# Boucle infinie
import time
while True:
    time.sleep(1)
