# Force rebuild (solana 0.25.0 + solders 0.2.x)

import os
import time
import requests
import base58
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime
import pytz

# API solana 0.25.x
from solana.keypair import Keypair
from solana.rpc.api import Client

# ====== Env ======
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT  = os.getenv("TELEGRAM_CHAT_ID")
TZ    = os.getenv("TZ", "Europe/Paris")
RPC_URL = os.getenv("RPC_URL", "https://api.mainnet-beta.solana.com")

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

# === Charge la clé privée Phantom (Base58 forcé) ===
pk_str = os.getenv("SOLANA_PRIVATE_KEY")
if not pk_str:
    raise ValueError("Variable SOLANA_PRIVATE_KEY non définie")

secret = base58.b58decode(pk_str.strip())
print(f"[info] Clé Base58 décodée: {len(secret)} octets")
if len(secret) != 64:
    raise ValueError(f"Clé invalide: {len(secret)} octets — attendu 64 (secretKey seed+pub)")

kp = Keypair.from_secret_key(secret)
print(f"[debug] Public key générée: {kp.public_key}")

# === RPC client ===
client = Client(RPC_URL)

def get_wallet_balance_sol() -> float:
    resp = client.get_balance(kp.public_key)
    lamports = resp["result"]["value"]  # solana 0.25 -> dict JSON
    return lamports / 1_000_000_000

def job_balance():
    try:
        sol = get_wallet_balance_sol()
        send(f"💰 Solde wallet BOT: {sol:.4f} SOL (pubkey: {kp.public_key})")
    except Exception as e:
        send(f"[erreur lecture solde] {e}")

# Message de démarrage + solde immédiat
send("🚀 Bot prêt ✅ (Railway)")
job_balance()

# Scheduler (heartbeat + résumé)
scheduler = BackgroundScheduler(timezone=pytz.timezone(TZ))
def heartbeat():
    now = datetime.now(pytz.timezone(TZ)).strftime("%Y-%m-%d %H:%M:%S")
    print(f"[hb] {now}")
scheduler.add_job(heartbeat, "interval", minutes=30, id="hb")
scheduler.add_job(job_balance, "interval", minutes=5, id="bal")  # solde toutes les 5 min
scheduler.start()

# Boucle
_running = True
import signal
def _stop(*_): 
    global _running; _running = False
signal.signal(signal.SIGTERM, _stop)
signal.signal(signal.SIGINT, _stop)

while _running:
    time.sleep(1)

scheduler.shutdown()
print("[exit] bye")
