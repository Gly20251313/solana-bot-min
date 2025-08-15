# Trading bot complet – Solana (DexScreener + Jupiter)
# - Seuil pump par défaut: 70% (ENTRY_THRESHOLD=0.70)
# - 25% du capital par trade
# - Stop-loss -10%, Trailing +30% (throwback 20%)
# - Filtres: liquidité >=10 SOL, volume >=5 SOL (auto convertis en USD via prix SOL)
# - Jusqu’à 4 positions en parallèle
# - Notifications Telegram

import os, time, json, base64, requests, base58, math
from datetime import datetime
import pytz
from apscheduler.schedulers.background import BackgroundScheduler

# ==== Solana (stack stable) ====
from solana.keypair import Keypair           # solana==0.25.0
from solana.rpc.api import Client
from solana.transaction import Transaction
from solana.rpc.types import TxOpts

# ==== ENV ====
TOKEN   = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT    = os.getenv("TELEGRAM_CHAT_ID")
TZ_NAME = os.getenv("TZ", "Europe/Paris")
RPC_URL = os.getenv("RPC_URL", "https://api.mainnet-beta.solana.com")

ENTRY_THRESHOLD          = float(os.getenv("ENTRY_THRESHOLD", "0.70"))   # 70% par défaut
POSITION_SIZE_PCT        = float(os.getenv("POSITION_SIZE_PCT", "0.25")) # 25% du capital par trade
STOP_LOSS_PCT            = float(os.getenv("STOP_LOSS_PCT", "0.10"))     # -10%
TRAILING_TRIGGER_PCT     = float(os.getenv("TRAILING_TRIGGER_PCT", "0.30"))  # +30%
TRAILING_THROWBACK_PCT   = float(os.getenv("TRAILING_THROWBACK_PCT", "0.20")) # -20% du plus haut
MAX_OPEN_TRADES          = int(os.getenv("MAX_OPEN_TRADES", "4"))
SCAN_INTERVAL_SEC        = int(os.getenv("SCAN_INTERVAL_SEC", "30"))     # scan toutes les 30s
PRICE_WINDOW             = os.getenv("PRICE_WINDOW", "h1")               # m5 | h1 | h6 | h24
SLIPPAGE_BPS             = int(os.getenv("SLIPPAGE_BPS", "100"))         # 1.00%
MIN_TRADE_SOL            = float(os.getenv("MIN_TRADE_SOL", "0.03"))     # min notional pour créer ATA etc.

# Filtres sécurité, définis en SOL puis convertis en USD via prix SOL live
MIN_LIQ_SOL              = float(os.getenv("MIN_LIQ_SOL", "10.0"))
MIN_VOL_SOL              = float(os.getenv("MIN_VOL_SOL", "5.0"))

# ==== Constantes Jupiter & réseaux ====
JUP_API  = "https://quote-api.jup.ag/swap/v1"
PRICE_API = "https://price.jup.ag/v4/price?ids=SOL"  # prix SOL en USD
WSOL = "So11111111111111111111111111111111111111112"

# ==== Telegram ====
def send(msg: str):
    if not TOKEN or not CHAT:
        print("[warn] Telegram non configuré"); return
    try:
        requests.get(
            f"https://api.telegram.org/bot{TOKEN}/sendMessage",
            params={"chat_id": CHAT, "text": msg}, timeout=10
        )
    except Exception as e:
        print("[error] telegram:", e)

# ==== Clé privée Phantom (Base58 forcé) ====
def load_keypair() -> Keypair:
    pk_str = os.getenv("SOLANA_PRIVATE_KEY")
    if not pk_str:
        raise ValueError("Variable SOLANA_PRIVATE_KEY manquante")
    secret = base58.b58decode(pk_str.strip())
    if len(secret) != 64:
        raise ValueError(f"Clé invalide: {len(secret)} octets — attendu 64")
    kp = Keypair.from_secret_key(secret)
    print(f"[boot] Public key: {kp.public_key}")
    return kp

kp = load_keypair()
client = Client(RPC_URL)
TZ = pytz.timezone(TZ_NAME)

# ==== Prix SOL (USD) via Jupiter ====
def get_sol_usd() -> float:
    try:
        r = requests.get(PRICE_API, timeout=10)
        r.raise_for_status()
        data = r.json()
        return float(data["data"]["SOL"]["price"])
    except Exception as e:
        print("[warn] prix SOL indisponible, fallback 150 USD", e)
        return 150.0

# ==== DexScreener scan (pairs Solana) ====
DEX_SCREENER_PAIRS = "https://api.dexscreener.com/latest/dex/pairs/solana"

def fetch_pairs() -> list:
    r = requests.get(DEX_SCREENER_PAIRS, timeout=20)
    r.raise_for_status()
    data = r.json()
    return data.get("pairs", [])

def get_price_change_pct(pair: dict, window: str) -> float:
    pc = pair.get("priceChange", {})
    val = pc.get(window)
    try:
        return float(val)
    except Exception:
        return float("nan")

def pair_liquidity_usd(pair: dict) -> float:
    liq = pair.get("liquidity", {})
    return float(liq.get("usd") or 0)

def pair_volume_h24_usd(pair: dict) -> float:
    vol = pair.get("volume", {})
    return float(vol.get("h24") or 0)

def pair_price_in_sol(pair: dict, sol_usd: float) -> float:
    # Retourne le prix du baseToken en SOL (si quote=SOL, on a priceNative; sinon on convertit via priceUsd)
    price_native = pair.get("priceNative")
    quote_sym = (pair.get("quoteToken") or {}).get("symbol", "")
    if quote_sym.upper() in ("SOL", "WSOL") and price_native:
        try:
            return float(price_native)
        except Exception:
            pass
    # sinon via USD
    price_usd = pair.get("priceUsd")
    if price_usd:
        try:
            return float(price_usd) / max(sol_usd, 1e-9)
        except Exception:
            pass
    return float("nan")

# ==== Jupiter (quote + swap) ====
def jup_quote(input_mint: str, output_mint: str, in_amount_lamports: int, slippage_bps: int):
    params = {
        "inputMint": input_mint,
        "outputMint": output_mint,
        "amount": in_amount_lamports,
        "slippageBps": slippage_bps,
        "onlyDirectRoutes": "false",
        "asLegacyTransaction": "true",
    }
    r = requests.get(f"{JUP_API}/quote", params=params, timeout=15)
    r.raise_for_status()
    return r.json()

def jup_swap_tx(quote_resp: dict, user_pubkey: str, wrap_unwrap_sol: bool = True):
    payload = {
        "quoteResponse": quote_resp,
        "userPublicKey": user_pubkey,
        "wrapAndUnwrapSol": wrap_unwrap_sol,
        "asLegacyTransaction": True,
    }
    r = requests.post(f"{JUP_API}/swap", json=payload, timeout=20)
    r.raise_for_status()
    data = r.json()
    return data["swapTransaction"]  # base64

def sign_and_send(serialized_b64: str):
    tx_bytes = base64.b64decode(serialized_b64)
    tx = Transaction.deserialize(tx_bytes)
    tx.sign(kp)
    resp = client.send_raw_transaction(tx.serialize(), opts=TxOpts(skip_preflight=True, preflight_commitment="processed"))
    return resp.get("result", resp) if isinstance(resp, dict) else resp

# ==== Solde SOL ====
def get_balance_sol() -> float:
    resp = client.get_balance(kp.public_key)
    lamports = resp["result"]["value"]
    return lamports / 1_000_000_000

# ==== Balance token SPL ====
def get_token_balance(mint: str) -> int:
    # retourne la balance en "amount" (entiers en plus petites unités) pour le mint donné
    try:
        params = {
            "owner": str(kp.public_key),
            "mint": mint
        }
        resp = client._provider.make_request("getTokenAccountsByOwner", str(kp.public_key), {"mint": mint}, {"encoding": "jsonParsed"})
        # compat si on utilise _provider : on peut utiliser directement client.get_token_accounts_by_owner_json_parsed plus récent
        if "result" not in resp or not resp["result"]["value"]:
            return 0
        acct = resp["result"]["value"][0]["account"]["data"]["parsed"]["info"]["tokenAmount"]
        return int(acct["amount"])  # quantité en plus petites unités
    except Exception as e:
        print("[warn] get_token_balance:", e)
        return 0

# ==== Positions ====
positions = {}  # mint -> dict(info)

def open_positions_count() -> int:
    return len(positions)

def can_open_more() -> bool:
    return open_positions_count() < MAX_OPEN_TRADES

def now_str():
    return datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")

# ==== Trading ====
def enter_trade(pair: dict, sol_usd: float):
    if not can_open_more():
        return

    # sizing
    balance = get_balance_sol()
    size_sol = max(balance * POSITION_SIZE_PCT, MIN_TRADE_SOL)
    if size_sol > balance * 0.99:
        size_sol = balance * 0.99
    lamports = int(size_sol * 1_000_000_000)

    base_mint = (pair.get("baseToken") or {}).get("address")
    base_sym  = (pair.get("baseToken") or {}).get("symbol") or "TOKEN"
    pair_url  = pair.get("url") or "https://dexscreener.com/solana"

    # Quote & swap SOL -> token
    try:
        q = jup_quote(WSOL, base_mint, lamports, SLIPPAGE_BPS)
        sig = sign_and_send(jup_swap_tx(q, str(kp.public_key)))
        send(f"📈 Achat {base_sym} (Seuil {int(ENTRY_THRESHOLD*100)}%)\n"
             f"Montant: {size_sol:.4f} SOL\n"
             f"Pair: {pair_url}\n"
             f"Tx: {sig}")
    except Exception as e:
        send(f"❌ Achat {base_sym} échoué: {e}")
        return

    # Enregistrer la position
    price_sol = pair_price_in_sol(pair, sol_usd)
    positions[base_mint] = {
        "symbol": base_sym,
        "entry_price_sol": price_sol,
        "peak_price_sol": price_sol,
        "pair_url": pair_url,
        "opened_at": now_str(),
    }

def check_positions(sol_usd: float):
    # Pour chaque position, on récupère le prix actuel et on applique SL / Trailing
    to_close = []
    for mint, pos in positions.items():
        symbol = pos["symbol"]
        entry  = pos["entry_price_sol"]
        peak   = pos["peak_price_sol"]

        # Récupère la paire principale de ce mint via DexScreener
        try:
            r = requests.get(f"https://api.dexscreener.com/latest/dex/tokens/{mint}", timeout=15)
            r.raise_for_status()
            data = r.json()
            pairs = data.get("pairs", [])
            if not pairs:
                continue
            # choisir la paire avec meilleure liquidité
            pair = max(pairs, key=lambda p: float((p.get("liquidity") or {}).get("usd") or 0))
            price = pair_price_in_sol(pair, sol_usd)
            if math.isnan(price) or price <= 0:
                continue
        except Exception as e:
            print("[warn] check_positions fetch:", e)
            continue

        # update peak
        if price > peak:
            pos["peak_price_sol"] = price
            peak = price

        # pertes depuis l'entrée
        draw_from_entry = (entry - price) / entry
        if draw_from_entry >= STOP_LOSS_PCT:
            if close_position(mint, symbol, "🛑 Stop-loss"):
                to_close.append(mint)
            continue

        # throwback depuis le plus haut
        drop_from_peak = (peak - price) / peak if peak > 0 else 0.0
        gain_from_entry = (price - entry) / entry
        if gain_from_entry >= TRAILING_TRIGGER_PCT and drop_from_peak >= TRAILING_THROWBACK_PCT:
            if close_position(mint, symbol, "✅ Trailing take-profit"):
                to_close.append(mint)
            continue

    for m in to_close:
        positions.pop(m, None)

def close_position(mint: str, symbol: str, reason: str) -> bool:
    # Vendre 100% du token -> SOL via Jupiter
    try:
        bal_amount = get_token_balance(mint)
        if bal_amount <= 0:
            send(f"{reason} {symbol}: aucun solde token détecté (déjà vendu ?)")
            return True

        q = jup_quote(mint, WSOL, int(bal_amount * 0.99), SLIPPAGE_BPS)  # 99% du solde par sécurité
        sig = sign_and_send(jup_swap_tx(q, str(kp.public_key)))
        send(f"{reason} {symbol}\nTx: {sig}")
        return True
    except Exception as e:
        send(f"❌ Vente {symbol} échouée: {e}")
        return False

# ==== Scan de marché ====
def scan_market():
    try:
        sol_usd = get_sol_usd()
        min_liq_usd = MIN_LIQ_SOL * sol_usd
        min_vol_usd = MIN_VOL_SOL * sol_usd

        pairs = fetch_pairs()
        if not pairs:
            return

        # filtrage sécurité + seuil pump
        candidates = []
        for p in pairs:
            # filtres liquidité / volume
            liq_usd = pair_liquidity_usd(p)
            vol_usd = pair_volume_h24_usd(p)
            if liq_usd < min_liq_usd or vol_usd < min_vol_usd:
                continue

            # pump sur la fenêtre choisie
            chg = get_price_change_pct(p, PRICE_WINDOW)
            if math.isnan(chg):
                continue
            if chg >= ENTRY_THRESHOLD * 100:
                candidates.append((chg, p))

        # Trier par % pump desc
        candidates.sort(key=lambda x: x[0], reverse=True)

        # ouvrir des positions tant qu'on peut
        for chg, p in candidates:
            if not can_open_more():
                break
            base_mint = (p.get("baseToken") or {}).get("address")
            if base_mint in positions:
                continue  # déjà en position
            enter_trade(p, sol_usd)

        # Gestion des positions ouvertes
        check_positions(sol_usd)

    except Exception as e:
        print("[scan error]", e)

# ==== Démarrage ====
def boot_message():
    b = get_balance_sol()
    send(
        "🚀 Bot prêt ✅ (Railway)\n"
        f"Seuil: {int(ENTRY_THRESHOLD*100)}% | SL: -{int(STOP_LOSS_PCT*100)}% | "
        f"Trailing: +{int(TRAILING_TRIGGER_PCT*100)}% / -{int(TRAILING_THROWBACK_PCT*100)}%\n"
        f"Max trades: {MAX_OPEN_TRADES} | Taille: {int(POSITION_SIZE_PCT*100)}%\n"
        f"Filtres: Liqu≥{MIN_LIQ_SOL} SOL, Vol≥{MIN_VOL_SOL} SOL\n"
        f"Solde: {b:.4f} SOL"
    )

boot_message()

# ==== Scheduler ====
scheduler = BackgroundScheduler(timezone=TZ)
scheduler.add_job(scan_market, "interval", seconds=SCAN_INTERVAL_SEC, id="scan")
scheduler.start()

# Boucle de vie
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
