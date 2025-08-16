# -*- coding: utf-8 -*-
import os, time, json, base64, math, tempfile, shutil, logging, uuid
from datetime import datetime
import requests
import based58  # ⚠️ pas "base58"
import pytz
from typing import Dict, Any, Set

from apscheduler.schedulers.background import BackgroundScheduler

# Solana stack (versions stables)
from solana.keypair import Keypair           # solana==0.25.0
from solana.rpc.api import Client
from solana.transaction import Transaction
from solana.rpc.types import TxOpts

# ==========================
# ENV & Réglages par défaut
# ==========================
TOKEN   = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHAT    = os.getenv("TELEGRAM_CHAT_ID", "")
TZ_NAME = os.getenv("TZ", "Europe/Paris")
RPC_URL = os.getenv("RPC_URL", "https://api.mainnet-beta.solana.com")

# Signal de pump
ENTRY_THRESHOLD          = float(os.getenv("ENTRY_THRESHOLD", "0.70"))   # 70% par défaut
PRICE_WINDOW             = os.getenv("PRICE_WINDOW", "h1")               # m5 | h1 | h6 | h24

# Sizing & risque
POSITION_SIZE_PCT        = float(os.getenv("POSITION_SIZE_PCT", "0.25")) # 25% du capital par trade (A+)
STOP_LOSS_PCT            = float(os.getenv("STOP_LOSS_PCT", "0.10"))     # -10% depuis l'entrée
TRAILING_TRIGGER_PCT     = float(os.getenv("TRAILING_TRIGGER_PCT", "0.30"))  # +30% vs entry pour activer trailing
TRAILING_THROWBACK_PCT   = float(os.getenv("TRAILING_THROWBACK_PCT", "0.20")) # -20% depuis le plus haut
MAX_OPEN_TRADES          = int(os.getenv("MAX_OPEN_TRADES", "4"))

# Exécution
SCAN_INTERVAL_SEC        = int(os.getenv("SCAN_INTERVAL_SEC", "30"))
SLIPPAGE_BPS             = int(os.getenv("SLIPPAGE_BPS", "100"))         # 1.00%
MAX_SLIPPAGE_BPS         = int(os.getenv("MAX_SLIPPAGE_BPS", "150"))     # hard cap 1.50%
MIN_TRADE_SOL            = float(os.getenv("MIN_TRADE_SOL", "0.03"))
DRY_RUN                  = os.getenv("DRY_RUN", "0") == "1"

# Sonde anti-honeypot
PROBE_ENABLED            = os.getenv("PROBE_ENABLED", "1") == "1"
PROBE_SOL                = float(os.getenv("PROBE_SOL", "0.003"))        # micro-trade (ex. 0.003 SOL)

# Filtres sécurité marché (exprimés en SOL puis convertis en USD)
MIN_LIQ_SOL              = float(os.getenv("MIN_LIQ_SOL", "10.0"))
MIN_VOL_SOL              = float(os.getenv("MIN_VOL_SOL", "5.0"))
MIN_POOL_AGE_SEC         = int(os.getenv("MIN_POOL_AGE_SEC", str(2*60*60)))  # 2h

# A-trades facultatifs (par défaut OFF -> on ne trade que A+)
ALLOW_A_TRADES           = os.getenv("ALLOW_A_TRADES", "0") == "1"

# Heartbeat & fichiers
HEARTBEAT_MINUTES        = int(os.getenv("HEARTBEAT_MINUTES", "30"))
POSITIONS_PATH           = os.getenv("POSITIONS_PATH", "./positions.json")
BLACKLIST_PATH           = os.getenv("BLACKLIST_PATH", "./blacklist.json")
DYN_CACHE_PATH           = os.getenv("DYN_CACHE_PATH", "./dynamic_tokens.json")

# Whitelist dynamique max
DYNAMIC_MAX_TOKENS       = int(os.getenv("DYNAMIC_MAX_TOKENS", "50"))   # on complète jusqu’à ~100 total

# Logs
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=getattr(logging, LOG_LEVEL, logging.INFO), format='[%(levelname)s] %(message)s')
logger = logging.getLogger("bot")

# ==== Mints / Endpoints ====
WSOL = "So11111111111111111111111111111111111111112"
USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"

# Jupiter Lite (public, stable)
JUP_QUOTE_URL = "https://lite-api.jup.ag/swap/v1/quote"
JUP_SWAP_URL  = "https://lite-api.jup.ag/swap/v1/swap"
PRICE_API     = f"https://lite-api.jup.ag/price/v3?ids={WSOL}"  # lit usdPrice de WSOL

# DexScreener
DEX_SCREENER_SEARCH = "https://api.dexscreener.com/latest/dex/search"     # ?q=solana
DEX_TOKENS_BY_MINT  = "https://api.dexscreener.com/tokens/v1/solana"      # + /{mint}

# Whitelist de protocoles pour routes Jupiter (ajuste si besoin)
ALLOWED_PROTOCOLS = {"Raydium", "Orca", "Phoenix", "Lifinity"}

# ==========
# Telegram
# ==========
def send(msg: str):
    if not TOKEN or not CHAT:
        logger.warning("Telegram non configuré")
        return
    try:
        requests.get(
            f"https://api.telegram.org/bot{TOKEN}/sendMessage",
            params={"chat_id": CHAT, "text": msg},
            timeout=10
        )
    except Exception as e:
        logger.error(f"telegram error: {e}")

TELEGRAM_OFFSET_PATH = "./tg_offset.json"

def _load_tg_offset() -> int:
    try:
        if os.path.exists(TELEGRAM_OFFSET_PATH):
            return int(json.load(open(TELEGRAM_OFFSET_PATH)).get("offset", 0))
    except Exception:
        pass
    return 0

def _save_tg_offset(offset: int):
    try:
        json.dump({"offset": offset}, open(TELEGRAM_OFFSET_PATH, "w"))
    except Exception:
        pass

# =======
# HTTP
# =======
def http_get(url, params=None, timeout=15, retries=3, backoff=0.6):
    err = None
    for i in range(retries):
        try:
            r = requests.get(url, params=params, timeout=timeout)
            r.raise_for_status()
            return r
        except requests.exceptions.RequestException as e:
            err = e
            if i < retries - 1:
                time.sleep(backoff * (2 ** i))
            else:
                raise err

def http_post(url, json_payload=None, timeout=20, retries=3, backoff=0.6):
    err = None
    for i in range(retries):
        try:
            r = requests.post(url, json=json_payload, timeout=timeout)
            r.raise_for_status()
            return r
        except requests.exceptions.RequestException as e:
            err = e
            if i < retries - 1:
                time.sleep(backoff * (2 ** i))
            else:
                raise err

# ============
# Clé / Client
# ============
def load_keypair() -> Keypair:
    pk_str = os.getenv("SOLANA_PRIVATE_KEY")
    if not pk_str:
        raise ValueError("Variable SOLANA_PRIVATE_KEY manquante")
    secret = based58.b58decode(pk_str.strip())
    if len(secret) != 64:
        raise ValueError(f"Clé invalide: {len(secret)} octets — attendu 64 (après décodage base58)")
    kp = Keypair.from_secret_key(secret)
    logger.info(f"[boot] Public key: {kp.public_key}")
    return kp

kp = load_keypair()
client = Client(RPC_URL)
TZ = pytz.timezone(TZ_NAME)

# =====================
# Persistance / État
# =====================
positions: Dict[str, Dict[str, Any]] = {}  # mint -> dict
BLACKLIST: Dict[str, float] = {}           # mint -> epoch expiry
DYNAMIC_TOKENS: Set[str] = set()           # cache dynamique
HALT_TRADING = False

def atomic_write_json(path: str, data: dict):
    d = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(d, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", delete=False, dir=d) as tmp:
        json.dump(data, tmp, ensure_ascii=False, indent=2)
        tmp.flush()
        os.fsync(tmp.fileno())
        tmp_name = tmp.name
    shutil.move(tmp_name, path)

def save_positions():
    try:
        payload = {"updated_at": now_str(), "positions": positions}
        atomic_write_json(POSITIONS_PATH, payload)
    except Exception as e:
        logger.warning(f"save_positions: {e}")

def load_positions():
    global positions
    try:
        if not os.path.exists(POSITIONS_PATH):
            positions = {}
            return
        data = json.load(open(POSITIONS_PATH)) or {}
        positions = data.get("positions") or {}
        logger.info(f"[boot] positions restaurées: {len(positions)}")
    except Exception as e:
        logger.warning(f"load_positions: {e}")
        positions = {}

def save_blacklist():
    try:
        atomic_write_json(BLACKLIST_PATH, {"updated_at": now_str(), "blacklist": BLACKLIST})
    except Exception as e:
        logger.warning(f"save_blacklist: {e}")

def load_blacklist():
    global BLACKLIST
    try:
        if os.path.exists(BLACKLIST_PATH):
            BL = json.load(open(BLACKLIST_PATH)) or {}
            BLACKLIST = BL.get("blacklist", {}) or {}
            logger.info(f"[boot] blacklist restaurée: {len(BLACKLIST)}")
    except Exception as e:
        logger.warning(f"load_blacklist: {e}")
        BLACKLIST = {}

def save_dynamic_tokens():
    try:
        atomic_write_json(DYN_CACHE_PATH, {"updated_at": now_str(), "tokens": list(DYNAMIC_TOKENS)})
    except Exception as e:
        logger.warning(f"save_dynamic_tokens: {e}")

def load_dynamic_tokens():
    global DYNAMIC_TOKENS
    try:
        if os.path.exists(DYN_CACHE_PATH):
            data = json.load(open(DYN_CACHE_PATH)) or {}
            DYNAMIC_TOKENS = set(data.get("tokens") or [])
            logger.info(f"[boot] dynamic tokens restaurés: {len(DYNAMIC_TOKENS)}")
    except Exception as e:
        logger.warning(f"load_dynamic_tokens: {e}")
        DYNAMIC_TOKENS = set()

# ===================
# Whitelist fixe (≈50)
# ===================
# ⚠️ Par sécurité, je fournis un noyau dur (solides & bien connus).
# Tu peux ajouter d’autres mints sûrs ici si tu veux atteindre ~50 fixes.
FIXED_TOKENS: Set[str] = {
    WSOL,                # WSOL
    USDC,                # USDC
    "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",  # USDT
    "JUP4Fb2w9Q3ZHzGVzF4Xz9c2yRt7ppJQkG5CS84VmQp",   # JUP
    "DezXAZ8z7PnrnRJjz3wXBoTvuQYFxRpwk4cEb9CZxbnS",  # BONK
    "4k3Dyjzvzp8eK7CkHxYfzznHVfhnF1Vd1z1dcz7URb1t",  # RAY
    "orcaEGLhXZcJuz2o1qgTt1rYfM8nRAPdY6inZY3khQk",   # ORCA
    "mSoLzysDnAqFLQ9dLru6T3rzEdd3TvTjL2AcK8tq7M2",   # mSOL
    "7dHbWXmci3dT8Q2ZUr9z5r5j6CkhdV8kFVUMbiZyJHcN",  # stSOL
    # Ajoute ici tes mints fixes supplémentaires si tu veux atteindre ~50
}

# ==================
# Prix / DexScreener
# ==================
def now_str():
    return datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")

def get_sol_usd() -> float:
    try:
        r = http_get(PRICE_API, timeout=10)
        data = r.json() or {}
        entry = None
        if isinstance(data, dict) and WSOL in data:
            entry = data.get(WSOL)
        if entry is None and isinstance(data, dict):
            dd = data.get("data")
            if isinstance(dd, dict):
                entry = dd.get(WSOL)
        if not entry:
            raise KeyError("entrée WSOL absente")
        price = entry.get("usdPrice")
        if price is None:
            raise KeyError("usdPrice manquant")
        return float(price)
    except Exception as e:
        logger.warning(f"prix SOL indisponible, fallback 150 USD: {e}")
        return 150.0

def fetch_pairs() -> list:
    """Récupère des paires Solana via /search?q=solana et filtre chainId='solana'."""
    try:
        r = http_get(DEX_SCREENER_SEARCH, params={"q": "solana"}, timeout=20)
        data = r.json() or {}
        pairs = data.get("pairs", []) or []
        return [p for p in pairs if (p.get("chainId") or "").lower() == "solana"]
    except Exception as e:
        logger.warning(f"fetch_pairs error: {e}")
        return []

def get_price_change_pct(pair: dict, window: str) -> float:
    pc = pair.get("priceChange", {})
    val = pc.get(window)
    try:
        return float(val)
    except Exception:
        return float("nan")

def pair_liquidity_usd(pair: dict) -> float:
    liq = pair.get("liquidity", {})
    return float(liq.get("usd") or 0.0)

def pair_volume_h24_usd(pair: dict) -> float:
    vol = pair.get("volume", {})
    return float(vol.get("h24") or 0.0)

def pair_price_in_sol(pair: dict, sol_usd: float) -> float:
    price_native = pair.get("priceNative")
    quote_sym = (pair.get("quoteToken") or {}).get("symbol", "")
    if quote_sym and quote_sym.upper() in ("SOL", "WSOL") and price_native:
        try:
            return float(price_native)
        except Exception:
            pass
    price_usd = pair.get("priceUsd")
    if price_usd:
        try:
            return float(price_usd) / max(sol_usd, 1e-9)
        except Exception:
            pass
    return float("nan")

def pair_age_sec(pair: dict) -> float:
    ts = pair.get("pairCreatedAt")  # ms epoch si présent
    try:
        if ts:
            return max(0, (time.time()*1000 - float(ts)) / 1000.0)
    except Exception:
        pass
    return 0.0

# ==========
# Jupiter
# ==========
def jup_quote(input_mint: str, output_mint: str, in_amount_lamports: int, slippage_bps: int):
    params = {
        "inputMint": input_mint,
        "outputMint": output_mint,
        "amount": in_amount_lamports,
        "slippageBps": min(int(slippage_bps), MAX_SLIPPAGE_BPS),
        "onlyDirectRoutes": "false",
        "asLegacyTransaction": "true",
    }
    r = http_get(JUP_QUOTE_URL, params=params, timeout=15)
    return r.json()

def jup_swap_tx(quote_resp: dict, user_pubkey: str, wrap_unwrap_sol: bool = True):
    payload = {
        "quoteResponse": quote_resp,
        "userPublicKey": user_pubkey,
        "wrapAndUnwrapSol": wrap_unwrap_sol,
        "asLegacyTransaction": True,
    }
    r = http_post(JUP_SWAP_URL, json_payload=payload, timeout=20)
    data = r.json()
    return data["swapTransaction"]  # base64

def route_is_whitelisted(quote: dict) -> bool:
    rp = quote.get("routePlan") or quote.get("marketInfos") or []
    if not isinstance(rp, list):
        return False
    labels = []
    for step in rp:
        info = step.get("swapInfo") or step
        label = (info.get("label") or info.get("protocol") or "").strip()
        if label:
            labels.append(label)
            if label not in ALLOWED_PROTOCOLS:
                return False
    return bool(labels)

def sign_and_send(serialized_b64: str):
    if DRY_RUN:
        return {"dry_run": True, "note": "swap non envoyé (DRY_RUN=1)"}
    tx_bytes = base64.b64decode(serialized_b64)
    tx = Transaction.deserialize(tx_bytes)
    tx.sign(kp)
    resp = client.send_raw_transaction(
        tx.serialize(),
        opts=TxOpts(skip_preflight=False, preflight_commitment="confirmed")
    )
    return resp.get("result", resp) if isinstance(resp, dict) else resp

# ==============
# Wallet & SPL
# ==============
def get_balance_sol() -> float:
    resp = client.get_balance(kp.public_key)
    lamports = (resp.get("result") or {}).get("value", 0)
    return lamports / 1_000_000_000

def get_token_balance(mint: str) -> int:
    try:
        resp = client.get_token_accounts_by_owner_json_parsed(
            kp.public_key, {"mint": mint}, commitment="confirmed"
        )
        vals = (resp.get("result") or {}).get("value") or []
        if not vals:
            return 0
        total = 0
        for v in vals:
            info = (((v or {}).get("account") or {}).get("data") or {}).get("parsed", {})
            amt = (((info.get("info") or {}).get("tokenAmount")) or {}).get("amount")
            if amt is not None:
                total += int(amt)
        return total
    except Exception as e:
        logger.warning(f"get_token_balance: {e}")
        return 0

# ======
# Utils
# ======
def open_positions_count() -> int:
    return len(positions)

def can_open_more() -> bool:
    return open_positions_count() < MAX_OPEN_TRADES

def new_trade_id() -> str:
    return uuid.uuid4().hex[:8]

def ok(b: bool) -> str:
    return "✅" if b else "❌"

# ======================
# Blacklist & Sonde
# ======================
def is_blacklisted(mint: str) -> bool:
    exp = BLACKLIST.get(mint, 0)
    return bool(exp and time.time() < exp)

def blacklist(mint: str, hours=24):
    BLACKLIST[mint] = time.time() + hours*3600
    save_blacklist()

def probe_trade(mint: str, user_pubkey: str) -> bool:
    """Micro-achat puis revente immédiate. Si KO → False (blacklist par appelant)."""
    if not PROBE_ENABLED:
        return True
    try:
        lamports = int(PROBE_SOL * 1_000_000_000)
        q_buy = jup_quote(WSOL, mint, lamports, SLIPPAGE_BPS)
        if not q_buy or not route_is_whitelisted(q_buy):
            return False
        if not DRY_RUN:
            txb = jup_swap_tx(q_buy, user_pubkey)
            sign_and_send(txb)
        q_sell = jup_quote(mint, WSOL, int(lamports*0.95), SLIPPAGE_BPS)
        if not q_sell or not route_is_whitelisted(q_sell):
            return False
        if not DRY_RUN:
            txs = jup_swap_tx(q_sell, user_pubkey)
            sign_and_send(txs)
        return True
    except Exception as e:
        logger.warning(f"probe_trade: {e}")
        return False

# =================
# Scoring & sizing
# =================
def score_pair(chg_pct: float, liq_usd: float, vol_usd: float, age_sec: float, min_liq_usd: float, min_vol_usd: float) -> str:
    if chg_pct < ENTRY_THRESHOLD * 100:
        return "B"
    hard = (liq_usd >= min_liq_usd) and (vol_usd >= min_vol_usd) and (age_sec >= MIN_POOL_AGE_SEC)
    if hard:
        return "A+"
    soft = (liq_usd >= 0.9*min_liq_usd) and (vol_usd >= min_vol_usd) and (age_sec >= 0.5*MIN_POOL_AGE_SEC)
    return "A" if soft else "B"

def size_for_score(balance_sol: float, score: str) -> float:
    if score == "A+":
        pct = POSITION_SIZE_PCT
    elif score == "A" and ALLOW_A_TRADES:
        pct = 0.15
    else:
        return 0.0
    size_sol = max(balance_sol * pct, MIN_TRADE_SOL)
    if size_sol > balance_sol * 0.99:
        size_sol = balance_sol * 0.99
    return max(0.0, size_sol)

# ==========================
# Whitelist dynamique (DexS)
# ==========================
def refresh_dynamic_tokens():
    """Construit une liste dynamique (jusqu’à DYNAMIC_MAX_TOKENS) selon volume/liquidité/âge."""
    global DYNAMIC_TOKENS
    try:
        sol_usd = get_sol_usd()
        min_liq_usd = MIN_LIQ_SOL * sol_usd
        min_vol_usd = MIN_VOL_SOL * sol_usd

        pairs = fetch_pairs()
        if not pairs:
            return

        found: Set[str] = set()
        # Tri par volume 24h desc pour capter les plus liquides
        pairs.sort(key=lambda p: pair_volume_h24_usd(p), reverse=True)

        for p in pairs:
            if len(found) >= DYNAMIC_MAX_TOKENS:
                break
            if (p.get("chainId") or "").lower() != "solana":
                continue

            liq_usd = pair_liquidity_usd(p)
            vol_usd = pair_volume_h24_usd(p)
            age = pair_age_sec(p)
            if liq_usd < min_liq_usd or vol_usd < min_vol_usd or age < MIN_POOL_AGE_SEC:
                continue

            base_mint = (p.get("baseToken") or {}).get("address")
            quote_sym = ((p.get("quoteToken") or {}).get("symbol") or "").upper()
            # On prend préférentiellement les paires côté SOL/USDC
            if not base_mint:
                continue
            if quote_sym not in ("SOL", "WSOL", "USDC"):
                continue

            found.add(base_mint)

        DYNAMIC_TOKENS = found
        save_dynamic_tokens()
        logger.info(f"[dynamic] rafraîchi: {len(DYNAMIC_TOKENS)} tokens")
    except Exception as e:
        logger.warning(f"refresh_dynamic_tokens: {e}")

def final_whitelist() -> Set[str]:
    return set(FIXED_TOKENS) | set(DYNAMIC_TOKENS)

# =================
# Trading
# =================
def enter_trade(pair: dict, sol_usd: float, score: str):
    if not can_open_more():
        return

    base_mint = (pair.get("baseToken") or {}).get("address")
    base_sym  = (pair.get("baseToken") or {}).get("symbol") or "TOKEN"
    pair_url  = pair.get("url") or "https://dexscreener.com/solana"

    wl = final_whitelist()
    if not base_mint or base_mint in positions:
        return
    if base_mint not in wl:
        return
    if is_blacklisted(base_mint):
        return

    balance = get_balance_sol()
    size_sol = size_for_score(balance, score)
    if size_sol <= 0:
        return

    lamports = int(size_sol * 1_000_000_000)
    if lamports <= 0:
        send("❌ Achat annulé: solde SOL insuffisant"); return

    trade_id = new_trade_id()

    try:
        # Sonde anti-honeypot
        if not probe_trade(base_mint, str(kp.public_key)):
            blacklist(base_mint, hours=24)
            send(f"🧪 Sonde KO → blacklist 24h : {base_mint}")
            return

        q = jup_quote(WSOL, base_mint, lamports, SLIPPAGE_BPS)
        if not q or not route_is_whitelisted(q):
            send(f"⛔ Route non whitelist pour {base_sym} — rejet")
            return
        sig = sign_and_send(jup_swap_tx(q, str(kp.public_key)))
        send(
            f"📈 Achat {base_sym} [{score}]\n"
            f"Montant: {size_sol:.4f} SOL\n"
            f"Pair: {pair_url}\n"
            f"ID: {trade_id}\nTx: {sig}"
        )
    except Exception as e:
        send(f"❌ Achat {base_sym} échoué: {e}")
        return

    price_sol = pair_price_in_sol(pair, sol_usd)
    positions[base_mint] = {
        "symbol": base_sym,
        "entry_price_sol": price_sol,
        "peak_price_sol": price_sol,
        "pair_url": pair_url,
        "opened_at": now_str(),
        "score": score,
        "trade_id": trade_id,
    }
    save_positions()

def close_position(mint: str, symbol: str, reason: str) -> bool:
    try:
        bal_amount = get_token_balance(mint)
        if bal_amount <= 0:
            send(f"{reason} {symbol}: aucun solde token détecté (déjà vendu ?)")
            return True

        q = jup_quote(mint, WSOL, int(bal_amount * 0.99), SLIPPAGE_BPS)
        if not q or not route_is_whitelisted(q):
            send(f"⛔ Route non whitelist à la vente pour {symbol} — tentative annulée")
            return False
        sig = sign_and_send(jup_swap_tx(q, str(kp.public_key)))
        send(f"{reason} {symbol}\nTx: {sig}")
        return True
    except Exception as e:
        send(f"❌ Vente {symbol} échouée: {e}")
        return False

def check_positions(sol_usd: float):
    to_close = []
    for mint, pos in list(positions.items()):
        symbol = pos["symbol"]
        entry  = pos.get("entry_price_sol") or 0.0
        peak   = pos.get("peak_price_sol") or entry

        try:
            r = http_get(f"{DEX_TOKENS_BY_MINT}/{mint}", timeout=15)
            pairs = r.json() or []
            if not pairs:
                continue
            pair = max(pairs, key=lambda p: float((p.get("liquidity") or {}).get("usd") or 0))
            price = pair_price_in_sol(pair, sol_usd)
            if math.isnan(price) or price <= 0:
                continue
        except Exception as e:
            logger.warning(f"check_positions fetch: {e}")
            continue

        # update peak
        if price > peak:
            pos["peak_price_sol"] = price
            peak = price
            save_positions()

        # stop-loss (depuis l'entrée)
        if entry and (entry - price) / entry >= STOP_LOSS_PCT:
            if close_position(mint, symbol, "🛑 Stop-loss"):
                to_close.append(mint)
            continue

        # trailing TP
        gain_from_entry = (price - entry) / entry if entry else 0.0
        drop_from_peak  = (peak - price) / peak if peak else 0.0
        if gain_from_entry >= TRAILING_TRIGGER_PCT and drop_from_peak >= TRAILING_THROWBACK_PCT:
            if close_position(mint, symbol, "✅ Trailing take-profit"):
                to_close.append(mint)
            continue

    for m in to_close:
        positions.pop(m, None)
    if to_close:
        save_positions()

# =====================
# Scan de marché (loop)
# =====================
def scan_market():
    if HALT_TRADING:
        return
    try:
        sol_usd = get_sol_usd()
        min_liq_usd = MIN_LIQ_SOL * sol_usd
        min_vol_usd = MIN_VOL_SOL * sol_usd

        pairs = fetch_pairs()
        if not pairs:
            return

        wl = final_whitelist()
        candidates = []
        for p in pairs:
            base_mint = (p.get("baseToken") or {}).get("address")
            if not base_mint or base_mint not in wl:
                continue

            liq_usd = pair_liquidity_usd(p)
            vol_usd = pair_volume_h24_usd(p)
            age = pair_age_sec(p)
            if liq_usd < min_liq_usd or vol_usd < min_vol_usd or age < MIN_POOL_AGE_SEC:
                continue

            chg = get_price_change_pct(p, PRICE_WINDOW)
            if math.isnan(chg):
                continue

            score = score_pair(chg, liq_usd, vol_usd, age, min_liq_usd, min_vol_usd)
            if score in ("A+", "A"):
                candidates.append((chg, score, p))

        candidates.sort(key=lambda x: x[0], reverse=True)

        for chg, score, p in candidates:
            if not can_open_more():
                break
            base_mint = (p.get("baseToken") or {}).get("address")
            if not base_mint or base_mint in positions:
                continue
            enter_trade(p, sol_usd, score)

        check_positions(sol_usd)

    except Exception as e:
        err = f"[scan error] {type(e).__name__}: {e}"
        logger.error(err)
        send(f"⚠️ {err}")

# ==============================
# Boot self-check & monitoring
# ==============================
def health_check():
    results = {}
    try:
        bal = get_balance_sol()
        results["rpc"] = bal >= 0
        results["balance"] = bal
    except Exception as e:
        results["rpc"] = False
        results["balance"] = f"err: {e}"

    try:
        p = get_sol_usd()
        results["jup_price"] = p > 0
        results["sol_usd"] = p
    except Exception as e:
        results["jup_price"] = False
        results["sol_usd"] = f"err: {e}"

    try:
        pairs = fetch_pairs()
        results["dex_search"] = len(pairs) > 0
        results["pairs_count"] = len(pairs)
    except Exception as e:
        results["dex_search"] = False
        results["pairs_count"] = f"err: {e}"

    try:
        test_amt = int(0.01 * 1_000_000_000)  # 0.01 SOL
        q = jup_quote(WSOL, USDC, test_amt, SLIPPAGE_BPS)
        results["jup_quote"] = bool(q) and ("outAmount" in json.dumps(q))
    except Exception:
        results["jup_quote"] = False
    return results

def send_boot_diagnostics():
    res = health_check()
    msg = (
        "🩺 Self-check démarrage\n"
        f"RPC: {ok(res.get('rpc', False))} | Solde: {res.get('balance')}\n"
        f"Jupiter Price: {ok(res.get('jup_price', False))} | SOL≈{res.get('sol_usd')}\n"
        f"DexScreener /search: {ok(res.get('dex_search', False))} | pairs={res.get('pairs_count')}\n"
        f"Jupiter quote: {ok(res.get('jup_quote', False))}\n"
        f"Params ⇒ Seuil {int(ENTRY_THRESHOLD*100)}% | SL -{int(STOP_LOSS_PCT*100)}% | "
        f"Trailing +{int(TRAILING_TRIGGER_PCT*100)}% / -{int(TRAILING_THROWBACK_PCT*100)}% | "
        f"Max {MAX_OPEN_TRADES} | Taille A+: {int(POSITION_SIZE_PCT*100)}% | A: 15%{' (off)' if not ALLOW_A_TRADES else ''}\n"
        f"Filtres: Liqu≥{MIN_LIQ_SOL} SOL, Vol≥{MIN_VOL_SOL} SOL, Âge≥{MIN_POOL_AGE_SEC//3600}h | Fenêtre: {PRICE_WINDOW}"
    )
    send(msg)

def heartbeat():
    send(f"⏱️ Heartbeat {now_str()} | positions: {len(positions)} | blacklist: {len(BLACKLIST)} | dyn: {len(DYNAMIC_TOKENS)}")

def daily_summary():
    if positions:
        lines = []
        for m, p in positions.items():
            ep = p.get('entry_price_sol') or 0.0
            pk = p.get('peak_price_sol') or 0.0
            lines.append(f"- {p['symbol']} [{p.get('score','?')}] | entry {ep:.6f} SOL | peak {pk:.6f} SOL")
        body = "\n".join(lines)
    else:
        body = "Aucune position ouverte."
    send(f"📰 Résumé quotidien {now_str()}\n{body}")

# ======================
# Telegram commandes
# ======================
def handle_command(text: str):
    global HALT_TRADING
    t = text.strip().lower()

    if t.startswith("/start"):
        HALT_TRADING = False
        send("▶️ Trading activé.")
    elif t.startswith("/stop"):
        HALT_TRADING = True
        send("⏸️ Trading en pause.")
    elif t.startswith("/status"):
        send(f"ℹ️ Status {now_str()} | positions: {len(positions)} | blacklist: {len(BLACKLIST)} | dyn: {len(DYNAMIC_TOKENS)} | halt={HALT_TRADING}")
    elif t.startswith("/testtrade"):
        try:
            amt = max(0.002, PROBE_SOL)
            lamports = int(amt * 1_000_000_000)
            q = jup_quote(WSOL, USDC, lamports, min(SLIPPAGE_BPS, 50))
            if not q or not route_is_whitelisted(q):
                send("🔍 TestTrade: route non whitelist ou quote vide")
                return
            sig1 = sign_and_send(jup_swap_tx(q, str(kp.public_key)))
            # back
            q2 = jup_quote(USDC, WSOL, int(float(q.get("outAmount", "0"))*0.98), min(SLIPPAGE_BPS, 50))
            if not q2 or not route_is_whitelisted(q2):
                send("🔍 TestTrade SELL: route non whitelist ou quote vide")
                return
            sig2 = sign_and_send(jup_swap_tx(q2, str(kp.public_key)))
            send(f"✅ TestTrade OK\nBuy Tx: {sig1}\nSell Tx: {sig2}")
        except Exception as e:
            send(f"❌ TestTrade error: {e}")

def poll_telegram():
    if not TOKEN or not CHAT:
        return
    try:
        offset = _load_tg_offset()
        r = http_get(
            f"https://api.telegram.org/bot{TOKEN}/getUpdates",
            params={"timeout": 0, "offset": offset+1, "allowed_updates": json.dumps(["message"])},
            timeout=10
        )
        data = r.json() or {}
        upd = data.get("result", []) or []
        last = offset
        for u in upd:
            last = max(last, int(u.get("update_id", 0)))
            msg = u.get("message") or {}
            chat_id = str(((msg.get("chat") or {}).get("id")) or "")
            text = (msg.get("text") or "").strip()
            if not text or chat_id != str(CHAT):
                continue
            handle_command(text)
        if last != offset:
            _save_tg_offset(last)
    except Exception as e:
        logger.warning(f"poll_telegram: {e}")

# ============
# Boot message
# ============
def boot_message():
    b = get_balance_sol()
    send(
        "🚀 Bot prêt ✅ (Railway)\n"
        f"Seuil: {int(ENTRY_THRESHOLD*100)}% | SL: -{int(STOP_LOSS_PCT*100)}% | "
        f"Trailing: +{int(TRAILING_TRIGGER_PCT*100)}% / -{int(TRAILING_THROWBACK_PCT*100)}%\n"
        f"Max trades: {MAX_OPEN_TRADES} | Taille A+: {int(POSITION_SIZE_PCT*100)}% | A: 15%{' (off)' if not ALLOW_A_TRADES else ''}\n"
        f"Filtres: Liqu≥{MIN_LIQ_SOL} SOL, Vol≥{MIN_VOL_SOL} SOL, Âge≥{MIN_POOL_AGE_SEC//3600}h | Fenêtre: {PRICE_WINDOW}\n"
        f"DRY_RUN: {DRY_RUN} | PROBE: {PROBE_ENABLED} ({PROBE_SOL} SOL)\n"
        f"Whitelist fixe: {len(FIXED_TOKENS)} | dynamique max: {DYNAMIC_MAX_TOKENS}"
    )

# =====================
# Init & Scheduler
# =====================
def main():
    load_positions()
    load_blacklist()
    load_dynamic_tokens()

    boot_message()
    send_boot_diagnostics()

    # Première construction dynamique immédiate
    refresh_dynamic_tokens()

    scheduler = BackgroundScheduler(timezone=TZ)
    scheduler.add_job(scan_market, "interval", seconds=SCAN_INTERVAL_SEC, id="scan")
    scheduler.add_job(heartbeat, "interval", minutes=HEARTBEAT_MINUTES, id="heartbeat")
    scheduler.add_job(daily_summary, "cron", hour=21, minute=0, id="daily_summary")
    scheduler.add_job(poll_telegram, "interval", seconds=15, id="tg_poll")
    # refresh dynamique toutes les 10 minutes
    scheduler.add_job(refresh_dynamic_tokens, "interval", minutes=10, id="dyn_refresh")
    scheduler.start()

    # Boucle de vie + kill clean
    running = True
    import signal
    def _stop(*_):
        nonlocal running
        running = False
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    while running:
        time.sleep(1)

    scheduler.shutdown()
    print("[exit] bye")

if __name__ == "__main__":
    main()
