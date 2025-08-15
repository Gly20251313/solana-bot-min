# Force rebuild – auto Base58/JSON key, solders Keypair, balance compat

import os, time, json, re, base64, base58, requests, pytz
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from solana.rpc.api import Client
from solders.keypair import Keypair  # compatible solana==0.30.x

# ========= Config =========
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT  = os.getenv("TELEGRAM_CHAT_ID")
TZ    = os.getenv("TZ", "Europe/Paris")
RPC_URL = os.getenv("RPC_URL", "https://api.mainnet-beta.solana.com")

# ========= Utils =========
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

def decode_private_key(pk_str: str) -> bytes:
    """Accepte Base58 Phantom OU JSON [..] d'octets; fallback Base64/HEX."""
    s = pk_str.strip()
    # JSON d’octets
    if s.startswith("[") and s.endswith("]"):
        print("[info] Clé détectée: JSON d’octets")
        return bytes(json.loads(s))
    # HEX pur
    if re.fullmatch(r"[0-9a-fA-F]+", s):
        print("[info] Clé détectée: HEX")
        return bytes.fromhex(s)
    # Base64 possible
    try:
        b = base64.b64decode(s, validate=True)
        # Heuristique: si ça décode proprement et longueur plausible, ok
        if len(b) in (32, 64, 66):
            print("[info] Clé détectée: Base64")
            return b
    except Exception:
        pass
    # Base58 (cas Phantom le plus courant)
    print("[info] Clé détectée: Base58")
    return base58.b58decode(s)

def keypair_from_secret(secret: bytes) -> Keypair:
    """Construit un Keypair robuste à 32/64/66 octets.
       - 32B: seed
       - 64B: secretKey (seed+pubkey)
       - 66B: on tronque proprement aux 64 premiers (artefacts de copie)"""
    n = len(secret)
    print(f"[debug] Longueur clé décodée: {n} octets")
    if n == 32:
        return Keypair.from_seed(secret)
    if n == 64:
        return Keypair.from_bytes(secret)
    if n == 66:
        print("[fix] Clé 66B détectée → tronque à 64B")
        return Keypair.from_bytes(secret[:64])
    if n > 64:
        print(f"[fix] Clé >64B ({n}) → on prend les 64 premiers")
        return Keypair.from_bytes(secret[:64])
    raise ValueError(f"Clé trop courte ({n}B) – besoin ≥32B")

def get_wallet_balance_message() -> str:
    try:
        pk_str = os.getenv("SOLANA_PRIVATE_KEY")
        if not pk_str:
            return "[erreur] SOLANA_PRIVATE_KEY manquante"

        secret = decode_private_key(pk_str)
        kp = keypair_from_secret(secret)

        print(f"[debug] RPC_URL: {RPC_URL}")
        print(f"[debug] Public key: {kp.pubkey()}")

        client = Client(RPC_URL)
        resp = client.get_balance(kp.pubkey())
        print(f"[debug] Réponse RPC type: {type(resp)} | {resp}")

        # Compat solders/dict
        try:
            lamports = resp.value              # GetBalanceResp
        except AttributeError:
            lamports = resp["result"]["value"] # dict JSON

        balance_sol = lamports / 1_000_000_000
        return f"💰 Solde wallet BOT: {balance_sol:.4f} SOL (pubkey: {kp.pubkey()})"
    except Exception as e:
        return f"[erreur lecture solde] {e}"

# ========= Boot =========
send("🚀 Bot prêt ✅ (Railway)")

msg_balance = get_wallet_balance_message()
send(msg_balance)
print(f"[info] Message solde envoyé: {msg_balance}")

# ========= Scheduler =========
def heartbeat():
    now = datetime.now(pytz.timezone(TZ)).strftime("%Y-%m-%d %H:%M:%S")
    print(f"[hb] {now}")

scheduler = BackgroundScheduler(timezone=TZ)
scheduler.add_job(heartbeat, "interval", minutes=30, id="hb")
scheduler.add_job(lambda: send("📝 Résumé quotidien (placeholder)"), "cron", hour=21, minute=0, id="daily")
scheduler.start()

# ========= Loop =========
_running = True
def _stop(*_):
    global _running
    _running = False

import signal
signal.signal(signal.SIGTERM, _stop)
signal.signal(signal.SIGINT, _stop)

while _running:
    time.sleep(1)

scheduler.shutdown()
print("[exit] bye")
