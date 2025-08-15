# Force rebuild
import os, time, requests, signal, json, re, base64, base58
from datetime import datetime
import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from solana.rpc.api import Client
from solana.keypair import Keypair

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

def _decode_private_key(pk_str: str) -> bytes:
    pk_str = pk_str.strip()
    # JSON d’octets: "[12,34,...]"
    if pk_str.startswith('[') and pk_str.endswith(']'):
        print("[debug] Clé détectée: JSON d’octets")
        arr = json.loads(pk_str)
        return bytes(arr)
    # HEX pur
    if re.fullmatch(r'[0-9a-fA-F]+', pk_str):
        print("[debug] Clé détectée: HEX")
        return bytes.fromhex(pk_str)
    # Base64
    try:
        decoded = base64.b64decode(pk_str, validate=True)
        print("[debug] Clé détectée: Base64")
        return decoded
    except Exception:
        pass
    # Base58 (par défaut Phantom)
    print("[debug] Clé détectée: Base58")
    return base58.b58decode(pk_str)

def get_wallet_balance():
    """Récupère le solde du wallet BOT"""
    try:
        pk_str = os.getenv("SOLANA_PRIVATE_KEY")
        if not pk_str:
            msg = "[erreur] SOLANA_PRIVATE_KEY manquante"
            print(msg)
            return msg

        secret = _decode_private_key(pk_str)
        print(f"[debug] Longueur clé: {len(secret)} octets")

        # 32 octets = seed; 64 octets = secretKey complet
        if len(secret) == 32:
            kp = Keypair.from_seed(secret)
        elif len(secret) == 64:
            kp = Keypair.from_secret_key(secret)
        else:
            return f"[erreur] Longueur clé inattendue: {len(secret)} octets"

        rpc_url = os.getenv("RPC_URL", "https://api.mainnet-beta.solana.com")
        print(f"[debug] RPC_URL: {rpc_url}")
        print(f"[debug] Public key: {kp.public_key}")

        client = Client(rpc_url)
        resp = client.get_balance(kp.public_key)
        print(f"[debug] Réponse RPC: {resp}")

        if "result" not in resp or "value" not in resp["result"]:
            return f"[erreur RPC] réponse inattendue: {resp}"
        balance_sol = resp["result"]["value"] / 1_000_000_000
        return f"💰 Solde wallet BOT: {balance_sol:.4f} SOL (pubkey: {kp.public_key})"
    except Exception as e:
        err_msg = f"[erreur lecture solde] {e}"
        print(err_msg)
        return err_msg

# Message de démarrage
send("🚀 Bot prêt ✅ (Railway)")

# Lecture du solde et envoi
msg_balance = get_wallet_balance()
send(msg_balance)
print(f"[info] Message solde envoyé: {msg_balance}")

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
