import os, time, requests, signal
from datetime import datetime
import pytz
from apscheduler.schedulers.background import BackgroundScheduler

# Librairies Solana
from solana.rpc.api import Client
from solana.keypair import Keypair
import base58

# Variables d'environnement
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT  = os.getenv("TELEGRAM_CHAT_ID")
TZ    = os.getenv("TZ", "Europe/Paris")

def send(msg: str):
    """Envoie un message Telegram"""
    if not TOKEN or not CHAT:
        print("[warn] Telegram not configured")
        return
    try:
        requests.get(
            f"https://api.telegram.org/bot{TOKEN}/sendMessage",
            params={"chat_id": CHAT, "text": msg}, timeout=10
        )
    except Exception as e:
        print("[error] telegram:", e)

def get_wallet_balance():
    """Récupère le solde du wallet BOT"""
    try:
        pk_str = os.getenv("SOLANA_PRIVATE_KEY")
        if not pk_str:
            return "[erreur] clé privée manquante"

        secret_key = base58.b58decode(pk_str)
        kp = Keypair.from_secret_key(secret_key)

        rpc_url = os.getenv("RPC_URL", "https://api.mainnet-beta.solana.com")
        client = Client(rpc_url)

        balance_sol = client.get_balance(kp.public_key)["result"]["value"] / 1_000_000_000
        return f"💰 Solde wallet BOT: {balance_sol:.4f} SOL"
    except Exception as e:
        return f"[erreur lecture solde] {e}"

# Message de démarrage
send("🚀 Bot prêt ✅ (Railway)")

# Lecture du solde et envoi
send(get_wallet_balance())

# Scheduler : heartbeat + résumé 21:00
scheduler = BackgroundScheduler(timezone=TZ)

def heartbeat():
    now = datetime.now(pytz.timezone(TZ)).strftime("%Y-%m-%d %H:%M:%S")
    print(f"[hb] {now}")

scheduler.add_job(heartbeat, "interval", minutes=30, id="hb")
scheduler.add_job(lambda: send("📝 Résumé quotidien (placeholder)"), "cron", hour=21, minute=0, id="daily")
scheduler.start()

_running = True
def handle_stop(signum, frame):
    global _running
    _running = False

signal.signal(signal.SIGTERM, handle_stop)
signal.signal(signal.SIGINT, handle_stop)

while _running:
    time.sleep(1)

scheduler.shutdown()
print("[exit] bye")
