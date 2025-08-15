import os
import requests
import base58
from solana.keypair import Keypair
from solana.rpc.api import Client
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime
import pytz

# === Variables d'environnement ===
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT = os.getenv("TELEGRAM_CHAT_ID")
TZ = os.getenv("TZ", "Europe/Paris")
RPC_URL = os.getenv("RPC_URL", "https://api.mainnet-beta.solana.com")

# === Fonction d'envoi Telegram ===
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
        print("[error] telegram:", e)

# === Chargement clé privée Phantom (Base58 forcé) ===
pk_str = os.getenv("SOLANA_PRIVATE_KEY")
if not pk_str:
    raise ValueError("Variable SOLANA_PRIVATE_KEY non définie")

try:
    # Forçage Base58
    secret = base58.b58decode(pk_str.strip())
    print(f"[info] Clé Base58 forcée et décodée ({len(secret)} octets)")
except Exception as e:
    raise ValueError(f"Erreur décodage Base58: {e}")

# Vérifie la longueur
if len(secret) != 64:
    raise ValueError(f"Clé invalide: {len(secret)} octets au lieu de 64")

kp = Keypair.from_secret_key(secret)
print(f"[debug] Public key générée: {kp.pubkey()}")

# === Client RPC Solana ===
client = Client(RPC_URL)

def get_wallet_balance():
    try:
        balance_resp = client.get_balance(kp.pubkey())
        lamports = balance_resp["result"]["value"]
        sol = lamports / 1_000_000_000
        return sol
    except Exception as e:
        return f"[erreur lecture solde] {e}"

def job_balance():
    sol = get_wallet_balance()
    send(f"💰 Solde wallet BOT: {sol} SOL (pubkey: {kp.pubkey()})")

# === Planificateur ===
scheduler = BackgroundScheduler(timezone=pytz.timezone(TZ))
scheduler.add_job(job_balance, 'interval', minutes=1)  # Vérifie toutes les minutes
scheduler.start()

# === Message démarrage ===
send("🚀 Bot prêt ✅ (Railway)")

# Garde le script actif
import time
while True:
    time.sleep(1)
