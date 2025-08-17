# -*- coding: utf-8 -*-
"""
Solana Pump-Scanner + Trader (DexScreener + Jupiter Lite)
Version blindée (robuste) — 2025-08-17
- Whitelist fixe + dynamique (quotes configurables par ENV)
- Résolution symbole->mint (Jupiter token list + fallback DexScreener)
- Filtres sécurité (liq/vol/âge), route Jupiter whitelistee, micro-sonde anti-honeypot (optionnelle)
- Risk: SL dur, Trailing TP, sizing A+/A (A lisible via ENV)
- Telegram: /start /stop /status /testtrade /refresh_tokens /dyninfo /forcebuy /reset_offset /whoami /version
- Diagnostics dyn (compteurs rejets), logs plus verbeux en DEBUG
- Endpoints DexScreener: pairs/solana (fallback search)

Dépendances (versions conseillées):
  requests, based58==2.1.1, pytz, apscheduler, solana==0.25.0
"""

import os, time, json, base64, math, uuid, re, logging
from typing import Dict, Any, Set, Tuple
from datetime import datetime

import requests
import based58  # pip install base58==2.1.1
import pytz
from apscheduler.schedulers.background import BackgroundScheduler

# Solana stack (versions stables pour Python 3.12)
from solana.keypair import Keypair           # solana==0.25.0
from solana.rpc.api import Client
from solana.transaction import Transaction
from solana.rpc.types import TxOpts

# =========================
# Version & ENV
# =========================
BOT_VERSION = os.getenv("BOT_VERSION", "v1.2-bulwark-2025-08-17")

TOKEN   = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHAT    = os.getenv("TELEGRAM_CHAT_ID", "")  # peut être négatif (groupes)
TZ_NAME = os.getenv("TZ", "Europe/Paris")
RPC_URL = os.getenv("RPC_URL", "https://api.mainnet-beta.solana.com")

# Signal de pump
ENTRY_THRESHOLD          = float(os.getenv("ENTRY_THRESHOLD", "0.70"))   # 70% par défaut
PRICE_WINDOW             = os.getenv("PRICE_WINDOW", "h1")               # m5|h1|h6|h24

# Sizing & risque
POSITION_SIZE_PCT        = float(os.getenv("POSITION_SIZE_PCT", "0.25")) # A+ = 25%
A_SIZE_PCT_ENV           = os.getenv("A_SIZE_PCT")                         # optionnel (str)
STOP_LOSS_PCT            = float(os.getenv("STOP_LOSS_PCT", "0.10"))     # -10%
TRAILING_TRIGGER_PCT     = float(os.getenv("TRAILING_TRIGGER_PCT", "0.30"))  # +30%
TRAILING_THROWBACK_PCT   = float(os.getenv("TRAILING_THROWBACK_PCT", "0.20")) # -20% du plus haut
MAX_OPEN_TRADES          = int(os.getenv("MAX_OPEN_TRADES", "4"))

# Exécution
SCAN_INTERVAL_SEC        = int(os.getenv("SCAN_INTERVAL_SEC", "30"))
SLIPPAGE_BPS             = int(os.getenv("SLIPPAGE_BPS", "100"))         # 1.00%
MAX_SLIPPAGE_BPS         = int(os.getenv("MAX_SLIPPAGE_BPS", "150"))     # 1.50%
MIN_TRADE_SOL            = float(os.getenv("MIN_TRADE_SOL", "0.03"))
DRY_RUN                  = os.getenv("DRY_RUN", "0") == "1"

# Sonde anti-honeypot
PROBE_ENABLED            = os.getenv("PROBE_ENABLED", "1") == "1"
PROBE_SOL                = float(os.getenv("PROBE_SOL", "0.003"))        # micro-trade

# Filtres sécurité marché (exprimés en SOL puis convertis en USD)
MIN_LIQ_SOL              = float(os.getenv("MIN_LIQ_SOL", "10.0"))
MIN_VOL_SOL              = float(os.getenv("MIN_VOL_SOL", "5.0"))
MIN_POOL_AGE_SEC         = int(os.getenv("MIN_POOL_AGE_SEC", str(2*60*60)))  # 2h
DYNAMIC_MAX_TOKENS       = int(os.getenv("DYNAMIC_MAX_TOKENS", "50"))
DYN_IGNORE_FILTERS       = os.getenv("DYN_IGNORE_FILTERS", "0") == "1"  # diag only

# A-trades facultatifs (par défaut OFF -> on ne trade que A+)
ALLOW_A_TRADES           = os.getenv("ALLOW_A_TRADES", "0") == "1"

# Heartbeat & fichiers
HEARTBEAT_MINUTES        = int(os.getenv("HEARTBEAT_MINUTES", "30"))
POSITIONS_PATH           = os.getenv("POSITIONS_PATH", "./positions.json")
BLACKLIST_PATH           = os.getenv("BLACKLIST_PATH", "./blacklist.json")
DYN_CACHE_PATH           = os.getenv("DYN_CACHE_PATH", "./dynamic_tokens.json")
TOKENMAP_CACHE_PATH      = os.getenv("TOKENMAP_CACHE_PATH", "./token_map.json")
TG_OFFSET_PATH           = os.getenv("TELEGRAM_OFFSET_PATH", "./tg_offset.json")

# Logs
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=getattr(logging, LOG_LEVEL, logging.INFO), format='[%(levelname)s] %(message)s')
logger = logging.getLogger("bot")

# ==== Mints / Endpoints ====
WSOL = "So11111111111111111111111111111111111111112"
USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"

# Jupiter Lite
JUP_QUOTE_URL = "https://lite-api.jup.ag/swap/v1/quote"
JUP_SWAP_URL  = "https://lite-api.jup.ag/swap/v1/swap"
PRICE_API     = f"https://lite-api.jup.ag/price/v3?ids={WSOL}"

# Jupiter token list (map symbol -> mint)
JUP_TOKEN_LIST = "https://token.jup.ag/all"

# DexScreener
DEX_SCREENER_SEARCH = "https://api.dexscreener.com/latest/dex/search"     # ?q=solana
DEX_PAIRS_SOLANA    = "https://api.dexscreener.com/latest/dex/pairs/solana"
DEX_TOKENS_BY_MINT  = "https://api.dexscreener.com/tokens/v1/solana"      # + /{mint}

# Quotes autorisées (configurable via ENV)
ALLOWED_QUOTES = {
    q.strip().upper()
    for q in os.getenv("ALLOWED_QUOTES", "SOL,WSOL,USDC,USDT").split(",")
    if q.strip()
}

# Whitelist de protocoles pour routes Jupiter
ALLOWED_PROTOCOLS = {"Raydium", "Orca", "Phoenix", "Lifinity"}
EXTRA_PROTOCOLS = os.getenv("ALLOWED_PROTOCOLS_EXTRA", "")
if EXTRA_PROTOCOLS:
    ALLOWED_PROTOCOLS |= {p.strip() for p in EXTRA_PROTOCOLS.split(",") if p.strip()}

# ==========================
# Telegram minimal (polling)
# ==========================
def _load_tg_offset() -> int:
    try:
        if os.path.exists(TG_OFFSET_PATH):
            return int(json.load(open(TG_OFFSET_PATH)).get("offset", 0))
    except Exception:
        pass
    return 0

def _save_tg_offset(offset: int):
    try:
        json.dump({"offset": offset}, open(TG_OFFSET_PATH, "w"))
    except Exception:
        pass

def send(msg: str):
    if not TOKEN or not CHAT:
        logger.warning("Telegram non configuré (TOKEN/CHAT)")
        return
    try:
        requests.get(
            f"https://api.telegram.org/bot{TOKEN}/sendMessage",
            params={"chat_id": CHAT, "text": msg},
            timeout=10
        )
    except Exception as e:
        logger.error(f"telegram error: {e}")

# Permet de répondre à un chat arbitraire (utile pour /whoami)
def send_to(chat_id: str, msg: str):
    if not TOKEN:
        logger.warning("Telegram TOKEN non configuré")
        return
    try:
        requests.get(
            f"https://api.telegram.org/bot{TOKEN}/sendMessage",
            params={"chat_id": chat_id, "text": msg},
            timeout=10
        )
    except Exception as e:
        logger.error(f"telegram send_to error: {e}")

# ======= HTTP helpers =======
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

# ========= Clé / Client =========
def load_keypair() -> Keypair:
    pk_str = os.getenv("SOLANA_PRIVATE_KEY") or os.getenv("SOL_PRIVATE_KEY") or ""
    if not pk_str:
        raise ValueError("Variable SOLANA_PRIVATE_KEY manquante")
    # supporte b58 (32/64 bytes) ou JSON [..]
    if pk_str.strip().startswith("["):
        arr = json.loads(pk_str)
        secret = bytes(arr)
    else:
        secret = based58.b58decode(pk_str.strip().encode("utf-8"))
    if len(secret) == 64:
        kp = Keypair.from_secret_key(secret)
    elif len(secret) == 32:
        # seed 32 bytes
        kp = Keypair.from_seed(secret)
    else:
        raise ValueError(f"Clé invalide: {len(secret)} octets — attendu 32 ou 64")
    logger.info(f"[boot] Public key: {kp.public_key}")
    return kp

kp = load_keypair()
client = Client(RPC_URL)
TZ = pytz.timezone(TZ_NAME)

# ====== État & persistance ======
positions: Dict[str, Dict[str, Any]] = {}
BLACKLIST: Dict[str, float] = {}
DYNAMIC_TOKENS: Set[str] = set()
TOKEN_MAP: Dict[str, Dict[str, Any]] = {}
SYMBOL_TO_MINT: Dict[str, str] = {}
HALT_TRADING = False

# ===== helpers persistance =====
def now_str():
    return datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")

def atomic_write_json(path: str, data: dict):
    try:
        d = os.path.dirname(os.path.abspath(path)) or "."
        os.makedirs(d, exist_ok=True)
        tmp_path = os.path.join(d, f".tmp_{uuid.uuid4().hex}.json")
        with open(tmp_path, "w") as tmp:
            json.dump(data, tmp, ensure_ascii=False, indent=2)
        os.replace(tmp_path, path)
    except Exception as e:
        logger.warning(f"atomic_write_json: {e}")

def save_positions():
    try:
        atomic_write_json(POSITIONS_PATH, {"updated_at": now_str(), "positions": positions})
    except Exception as e:
        logger.warning(f"save_positions: {e}")

def load_positions():
    global positions
    try:
        if os.path.exists(POSITIONS_PATH):
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

def save_token_map():
    try:
        atomic_write_json(TOKENMAP_CACHE_PATH, {"updated_at": now_str(), "map": TOKEN_MAP})
    except Exception as e:
        logger.warning(f"save_token_map: {e}")

def load_token_map():
    global TOKEN_MAP, SYMBOL_TO_MINT
    try:
        if os.path.exists(TOKENMAP_CACHE_PATH):
            data = json.load(open(TOKENMAP_CACHE_PATH)) or {}
            TOKEN_MAP = data.get("map") or {}
            SYMBOL_TO_MINT = { (v.get("symbol") or "").upper(): m for m,v in TOKEN_MAP.items() if v }
            logger.info(f"[boot] token map restaurée: {len(TOKEN_MAP)}")
    except Exception as e:
        logger.warning(f"load_token_map: {e}")
        TOKEN_MAP, SYMBOL_TO_MINT = {}, {}

# ===================
# Whitelist fixe (exemples de bluechips + SOL/USDC)
# ===================
FIXED_TOKENS: Set[str] = {
    WSOL, USDC,
    "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",  # USDT
    "JUP4Fb2w9Q3ZHzGVzF4Xz9c2yRt7ppJQkG5CS84VmQp",   # JUP
    "DezXAZ8z7PnrnRJjz3wXBoTvuQYFxRpwk4cEb9CZxbnS",  # BONK
    "4k3Dyjzvzp8eK7CkHxYfzznHVfhnF1Vd1z1dcz7URb1t",  # RAY
    "orcaEGLhXZcJuz2o1qgTt1rYfM8nRAPdY6inZY3khQk",   # ORCA
    "mSoLzysDnAqFLQ9dLru6T3rzEdd3TvTjL2AcK8tq7M2",   # mSOL
    "7dHbWXmci3dT8Q2ZUr9z5r5j6CkhdV8kFVUMbiZyJHcN",  # stSOL
    "9n4nbM75f5Ui33ZbPYXn59EwSgE8CGsHtAeTH5YFeJ9E",  # soBTC
    "7XS5r6X1o8Z1CazTAp3GEXLMaLLq5yRvCNr4AaVsgY1v",  # PYTH
}

# ==================
# Prix / DexScreener helpers
# ==================
MINT_RE = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")

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
    """Récupère un large set de paires Solana. Tente /pairs/solana puis fallback /search."""
    # 1) Endpoint dédié à la chaîne (souvent plus riche)
    try:
        r = http_get(DEX_PAIRS_SOLANA, timeout=20)
        data = r.json() or {}
        pairs = data.get("pairs", []) or data or []
        pairs = [p for p in pairs if (p.get("chainId") or "").lower() == "solana"]
        if pairs:
            return pairs
    except Exception as e:
        logger.debug(f"fetch_pairs primary failed: {e}")
    # 2) Fallback search
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
    ts = pair.get("pairCreatedAt")
    try:
        if ts:
            return max(0, (time.time()*1000 - float(ts)) / 1000.0)
    except Exception:
        pass
    return 0.0

# ========== Jupiter ==========

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
    return data["swapTransaction"]


def route_is_whitelisted(quote: dict) -> bool:
    rp = quote.get("routePlan") or quote.get("marketInfos") or []
    if not isinstance(rp, list):
        return False
    for step in rp:
        info = step.get("swapInfo") or step
        label = (info.get("label") or info.get("protocol") or "").strip()
        if not label or label not in ALLOWED_PROTOCOLS:
            return False
    return True


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

# ============= Wallet & SPL =============

def get_balance_sol() -> float:
    try:
        resp = client.get_balance(kp.public_key)
        lamports = (resp.get("result") or {}).get("value", 0)
        return lamports / 1_000_000_000
    except Exception as e:
        logger.warning(f"get_balance_sol error: {e}")
        return 0.0


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
    except Exception:
        return 0

# ===== Utils =====

def open_positions_count() -> int:
    return len(positions)

def can_open_more() -> bool:
    return open_positions_count() < MAX_OPEN_TRADES

def new_trade_id() -> str:
    return uuid.uuid4().hex[:8]

def ok(b: bool) -> str:
    return "✅" if b else "❌"

# ==============================
# Token map & résolution symboles
# ==============================

def refresh_token_map():
    """Charge la token list Jupiter et construit symbol -> mint + mint -> info."""
    global TOKEN_MAP, SYMBOL_TO_MINT
    try:
        r = http_get(JUP_TOKEN_LIST, timeout=20)
        data = r.json() or []
        new_map: Dict[str, Dict[str, Any]] = {}
        sym_map: Dict[str, str] = {}
        for t in data:
            mint = t.get("address") or t.get("mint")
            symbol = (t.get("symbol") or "").upper()
            if not mint or not symbol:
                continue
            new_map[mint] = {"symbol": symbol, "decimals": t.get("decimals"), "name": t.get("name")}
            if symbol not in sym_map:
                sym_map[symbol] = mint
        TOKEN_MAP = new_map
        SYMBOL_TO_MINT = sym_map
        save_token_map()
        logger.info(f"[tokenmap] chargé: {len(TOKEN_MAP)} mints, {len(SYMBOL_TO_MINT)} symboles")
    except Exception as e:
        logger.warning(f"refresh_token_map: {e}")


def resolve_symbol_or_mint(val: str) -> Tuple[str, str]:
    """Retourne (mint, symbol). Si `val` est déjà un mint, renvoie le mint et son symbole si connu."""
    s = val.strip()
    if MINT_RE.match(s):
        info = TOKEN_MAP.get(s) or {}
        return s, (info.get("symbol") or "?")
    sym = s.upper()
    mint = SYMBOL_TO_MINT.get(sym)
    if mint:
        return mint, sym
    # fallback DexScreener search
    try:
        r = http_get(DEX_SCREENER_SEARCH, params={"q": sym}, timeout=10)
        pairs = (r.json() or {}).get("pairs", []) or []
        pairs = [p for p in pairs if (p.get("chainId") or "").lower() == "solana"]
        if pairs:
            best = max(pairs, key=lambda p: float((p.get("liquidity") or {}).get("usd") or 0))
            mint2 = (best.get("baseToken") or {}).get("address")
            if mint2:
                return mint2, sym
    except Exception:
        pass
    return "", sym

# =================
# Blacklist & Sonde
# =================

def is_blacklisted(mint: str) -> bool:
    exp = BLACKLIST.get(mint, 0)
    return bool(exp and time.time() < exp)


def blacklist(mint: str, hours=24):
    BLACKLIST[mint] = time.time() + hours*3600
    save_blacklist()


def probe_trade(mint: str, user_pubkey: str) -> bool:
    if not PROBE_ENABLED:
        return True
    try:
        lamports = int(PROBE_SOL * 1_000_000_000)
        q_buy = jup_quote(WSOL, mint, lamports, min(SLIPPAGE_BPS, 50))
        if not q_buy or not route_is_whitelisted(q_buy):
            return False
        if not DRY_RUN:
            txb = jup_swap_tx(q_buy, user_pubkey); sign_and_send(txb)
        q_sell = jup_quote(mint, WSOL, int(lamports*0.95), min(SLIPPAGE_BPS, 50))
        if not q_sell or not route_is_whitelisted(q_sell):
            return False
        if not DRY_RUN:
            txs = jup_swap_tx(q_sell, user_pubkey); sign_and_send(txs)
        return True
    except Exception as e:
        logger.warning(f"probe_trade: {e}")
        return False

# =================
# Scoring & sizing
# =================

def score_pair(chg_pct: float, liq_usd: float, vol_usd: float, age_sec: float, min_liq_usd: float, min_vol_usd: float) -> str:
    if chg_pct < ENTRY_THRESHOLD * 100:  # DexS donne %
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
        pct = float(A_SIZE_PCT_ENV) if A_SIZE_PCT_ENV else 0.15
    else:
        return 0.0
    size_sol = max(balance_sol * pct, MIN_TRADE_SOL)
    return min(size_sol, balance_sol * 0.99)

# ==========================
# Whitelist dynamique (DexS)
# ==========================

def refresh_dynamic_tokens():
    """Met à jour la whitelist dynamique à partir de DexScreener, avec compteurs de rejets."""
    global DYNAMIC_TOKENS
    try:
        sol_usd = get_sol_usd()
        min_liq_usd = MIN_LIQ_SOL * sol_usd
        min_vol_usd = MIN_VOL_SOL * sol_usd

        pairs = fetch_pairs()
        if not pairs:
            DYNAMIC_TOKENS = set()
            save_dynamic_tokens()
            logger.warning("[dynamic] fetch_pairs a renvoyé 0 paire")
            send("⚠️ dynamic=0 (DexScreener vide)")
            return

        found = set()
        rej_liq = rej_vol = rej_age = rej_quote = 0

        pairs.sort(key=lambda p: pair_volume_h24_usd(p), reverse=True)
        for p in pairs:
            if len(found) >= DYNAMIC_MAX_TOKENS:
                break
            if (p.get("chainId") or "").lower() != "solana":
                continue

            base_mint = (p.get("baseToken") or {}).get("address")
            if not base_mint:
                continue

            quote_sym = ((p.get("quoteToken") or {}).get("symbol") or "").upper()
            if quote_sym not in ALLOWED_QUOTES:
                rej_quote += 1
                continue

            if DYN_IGNORE_FILTERS:
                found.add(base_mint)
                continue

            liq_usd = pair_liquidity_usd(p)
            vol_usd = pair_volume_h24_usd(p)
            age = pair_age_sec(p)

            if liq_usd < min_liq_usd:
                rej_liq += 1; continue
            if vol_usd < min_vol_usd:
                rej_vol += 1; continue
            if age < MIN_POOL_AGE_SEC:
                rej_age += 1; continue

            found.add(base_mint)

        DYNAMIC_TOKENS = found
        save_dynamic_tokens()
        logger.info(
            f"[dynamic] rafraîchi: {len(DYNAMIC_TOKENS)} tokens "
            f"(rejets: liq={rej_liq}, vol={rej_vol}, age={rej_age}, quote={rej_quote})"
        )
        send(
            f"✅ dynamic={len(DYNAMIC_TOKENS)} "
            f"(rejets liq={rej_liq}, vol={rej_vol}, age={rej_age}, quote={rej_quote})"
        )
    except Exception as e:
        logger.warning(f"refresh_dynamic_tokens: {e}")
        send(f"⚠️ dynamic=0 (erreur: {e})")


def final_whitelist() -> Set[str]:
    return set(FIXED_TOKENS) | set(DYNAMIC_TOKENS)

# ============ Trading ============

def enter_trade(pair: dict, sol_usd: float, score: str):
    if not can_open_more():
        return
    base_mint = (pair.get("baseToken") or {}).get("address")
    base_sym  = (pair.get("baseToken") or {}).get("symbol") or "TOKEN"
    pair_url  = pair.get("url") or "https://dexscreener.com/solana"
    wl = final_whitelist()
    if not base_mint or base_mint in positions or base_mint not in wl or is_blacklisted(base_mint):
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
        if not probe_trade(base_mint, str(kp.public_key)):
            blacklist(base_mint, hours=24); send(f"🧪 Sonde KO → blacklist 24h : {base_mint}"); return
        q = jup_quote(WSOL, base_mint, lamports, SLIPPAGE_BPS)
        if not q or not route_is_whitelisted(q):
            send(f"⛔ Route non whitelist pour {base_sym} — rejet"); return
        sig = sign_and_send(jup_swap_tx(q, str(kp.public_key)))
        send(f"📈 Achat {base_sym} [{score}]\nMontant: {size_sol:.4f} SOL\nPair: {pair_url}\nID: {trade_id}\nTx: {sig}")
    except Exception as e:
        send(f"❌ Achat {base_sym} échoué: {e}"); return
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
            send(f"{reason} {symbol}: aucun solde token détecté (déjà vendu ?)"); return True
        q = jup_quote(mint, WSOL, int(bal_amount * 0.99), SLIPPAGE_BPS)
        if not q or not route_is_whitelisted(q):
            send(f"⛔ Route non whitelist à la vente pour {symbol} — tentative annulée"); return False
        sig = sign_and_send(jup_swap_tx(q, str(kp.public_key)))
        send(f"{reason} {symbol}\nTx: {sig}")
        return True
    except Exception as e:
        send(f"❌ Vente {symbol} échouée: {e}"); return False


def check_positions(sol_usd: float):
    to_close = []
    for mint, pos in list(positions.items()):
        symbol = pos["symbol"]
        entry  = pos.get("entry_price_sol") or 0.0
        peak   = pos.get("peak_price_sol") or entry
        try:
            r = http_get(f"{DEX_TOKENS_BY_MINT}/{mint}", timeout=15)
            pairs = r.json() or []
            if not pairs: continue
            pair = max(pairs, key=lambda p: float((p.get("liquidity") or {}).get("usd") or 0))
            price = pair_price_in_sol(pair, sol_usd)
            if math.isnan(price) or price <= 0: continue
        except Exception:
            continue
        if price > peak:
            pos["peak_price_sol"] = price; peak = price; save_positions()
        if entry and (entry - price) / entry >= STOP_LOSS_PCT:
            if close_position(mint, symbol, "🛑 Stop-loss"): to_close.append(mint); continue
        gain_from_entry = (price - entry) / entry if entry else 0.0
        drop_from_peak  = (peak - price) / peak if peak else 0.0
        if gain_from_entry >= TRAILING_TRIGGER_PCT and drop_from_peak >= TRAILING_THROWBACK_PCT:
            if close_position(mint, symbol, "✅ Trailing take-profit"): to_close.append(mint); continue
    for m in to_close:
        positions.pop(m, None)
    if to_close: save_positions()

# ====================
# Scan de marché (loop)
# ====================

def scan_market():
    if HALT_TRADING: return
    try:
        sol_usd = get_sol_usd()
        min_liq_usd = MIN_LIQ_SOL * sol_usd
        min_vol_usd = MIN_VOL_SOL * sol_usd
        pairs = fetch_pairs()
        if not pairs: return
        wl = final_whitelist()
        candidates = []
        for p in pairs:
            base_mint = (p.get("baseToken") or {}).get("address")
            if not base_mint or base_mint not in wl: continue
            liq_usd = pair_liquidity_usd(p)
            vol_usd = pair_volume_h24_usd(p)
            age = pair_age_sec(p)
            if not DYN_IGNORE_FILTERS:  # en mode diag on laisse passer
                if liq_usd < min_liq_usd or vol_usd < min_vol_usd or age < MIN_POOL_AGE_SEC: continue
            chg = get_price_change_pct(p, PRICE_WINDOW)
            if math.isnan(chg): continue
            score = score_pair(chg, liq_usd, vol_usd, age, min_liq_usd, min_vol_usd)
            if score in ("A+","A"): candidates.append((chg, score, p))
        candidates.sort(key=lambda x: x[0], reverse=True)
        for chg, score, p in candidates:
            if not can_open_more(): break
            base_mint = (p.get("baseToken") or {}).get("address")
            if not base_mint or base_mint in positions: continue
            enter_trade(p, sol_usd, score)
        check_positions(sol_usd)
    except Exception as e:
        send(f"⚠️ [scan error] {type(e).__name__}: {e}")

# ==============================
# Diagnostics & résumés
# ==============================

def health_check():
    results = {}
    try:
        bal = get_balance_sol(); results["rpc"] = bal >= 0; results["balance"] = bal
    except Exception as e:
        results["rpc"] = False; results["balance"] = f"err: {e}"
    try:
        p = get_sol_usd(); results["jup_price"] = p > 0; results["sol_usd"] = p
    except Exception as e:
        results["jup_price"] = False; results["sol_usd"] = f"err: {e}"
    try:
        pairs = fetch_pairs(); results["dex_search"] = len(pairs) > 0; results["pairs_count"] = len(pairs)
    except Exception as e:
        results["dex_search"] = False; results["pairs_count"] = f"err: {e}"
    try:
        test_amt = int(0.01 * 1_000_000_000)
        q = jup_quote(WSOL, USDC, test_amt, min(SLIPPAGE_BPS, 50))
        results["jup_quote"] = bool(q) and ("outAmount" in json.dumps(q))
    except Exception:
        results["jup_quote"] = False
    return results


def send_boot_diagnostics():
    res = health_check()
    msg = (
        f"[{BOT_VERSION}] 🩺 Self-check démarrage\n"
        f"RPC: {ok(res.get('rpc', False))} | Solde: {res.get('balance')}\n"
        f"Jupiter Price: {ok(res.get('jup_price', False))} | SOL≈{res.get('sol_usd')}\n"
        f"DexScreener: {ok(res.get('dex_search', False))} | pairs={res.get('pairs_count')}\n"
        f"Jupiter quote: {ok(res.get('jup_quote', False))}\n"
        f"Params ⇒ Seuil {int(ENTRY_THRESHOLD*100)}% | SL -{int(STOP_LOSS_PCT*100)}% | "
        f"Trailing +{int(TRAILING_TRIGGER_PCT*100)}% / -{int(TRAILING_THROWBACK_PCT*100)}% | "
        f"Max {MAX_OPEN_TRADES} | Taille A+: {int(POSITION_SIZE_PCT*100)}% | A: {A_SIZE_PCT_ENV or '15%'}{' (off)' if not ALLOW_A_TRADES else ''}\n"
        f"Filtres: Liqu≥{MIN_LIQ_SOL} SOL, Vol≥{MIN_VOL_SOL} SOL, Âge≥{MIN_POOL_AGE_SEC//3600}h | Fenêtre: {PRICE_WINDOW}\n"
        f"Quotes dyn: {','.join(sorted(ALLOWED_QUOTES))} | Whitelist fixe: {len(FIXED_TOKENS)} | dyn: {len(DYNAMIC_TOKENS)} | tokenmap: {len(TOKEN_MAP)}\n"
        f"Protocols: {','.join(sorted(ALLOWED_PROTOCOLS))}\n"
    )
    send(msg)


def heartbeat():
    send(f"⏱️ Heartbeat {now_str()} | positions: {len(positions)} | blacklist: {len(BLACKLIST)} | dyn: {len(DYNAMIC_TOKENS)} | halt={HALT_TRADING}")


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

def handle_command(text: str, chat_id: str = None):
    global HALT_TRADING
    t = text.strip()
    tl = t.lower()
    if tl.startswith("/start"):
        HALT_TRADING = False; send("▶️ Trading activé.")
    elif tl.startswith("/stop"):
        HALT_TRADING = True; send("⏸️ Trading en pause.")
    elif tl.startswith("/status"):
        send(f"ℹ️ Status {now_str()} | positions: {len(positions)} | blacklist: {len(BLACKLIST)} | dyn: {len(DYNAMIC_TOKENS)} | halt={HALT_TRADING}")
    elif tl.startswith("/testtrade"):
        try:
            amt = max(0.002, PROBE_SOL); lamports = int(amt * 1_000_000_000)
            q = jup_quote(WSOL, USDC, lamports, min(SLIPPAGE_BPS, 50))
            if not q or not route_is_whitelisted(q): send("🔍 TestTrade: route non whitelist ou quote vide"); return
            sig1 = sign_and_send(jup_swap_tx(q, str(kp.public_key)))
            q2 = jup_quote(USDC, WSOL, int(float(q.get("outAmount","0"))*0.98), min(SLIPPAGE_BPS, 50))
            if not q2 or not route_is_whitelisted(q2): send("🔍 TestTrade SELL: route non whitelist ou quote vide"); return
            sig2 = sign_and_send(jup_swap_tx(q2, str(kp.public_key)))
            send(f"✅ TestTrade OK\nBuy Tx: {sig1}\nSell Tx: {sig2}")
        except Exception as e:
            send(f"❌ TestTrade error: {e}")
    elif tl.startswith("/refresh_tokens"):
        refresh_token_map(); refresh_dynamic_tokens();
    elif tl.startswith("/dyninfo"):
        try:
            refresh_dynamic_tokens()
        except Exception as e:
            send(f"/dyninfo erreur: {e}")
    elif tl.startswith("/forcebuy"):
        try:
            parts = t.split()
            if len(parts) < 3:
                send("Usage: /forcebuy <SYMBOL_ou_MINT> <montant_SOL>"); return
            token = parts[1]
            size_sol = float(parts[2])
            mint, sym = resolve_symbol_or_mint(token)
            if not mint:
                send(f"Token introuvable: {token}"); return
            if is_blacklisted(mint):
                send(f"Token blacklist: {mint}"); return
            if not PROBE_ENABLED or probe_trade(mint, str(kp.public_key)):
                lamports = int(size_sol * 1_000_000_000)
                q = jup_quote(WSOL, mint, lamports, SLIPPAGE_BPS)
                if not q or not route_is_whitelisted(q):
                    send("Route non whitelistée pour /forcebuy"); return
                sig = sign_and_send(jup_swap_tx(q, str(kp.public_key)))
                send(f"🚨 FORCE BUY {sym} ({mint})\nMontant: {size_sol:.4f} SOL\nTx: {sig}")
            else:
                send("Sonde anti-honeypot KO — /forcebuy annulé.")
        except Exception as e:
            send(f"/forcebuy erreur: {e}")
    elif tl.startswith("/reset_offset"):
        try:
            if os.path.exists(TG_OFFSET_PATH):
                os.remove(TG_OFFSET_PATH)
            send("♻️ Telegram offset reset. Réessayez vos commandes.")
        except Exception as e:
            send(f"reset_offset erreur: {e}")
    elif tl.startswith("/whoami"):
        if chat_id:
            send_to(chat_id, f"Votre chat_id: {chat_id}")
        else:
            send("(whoami) chat_id indisponible")
    elif tl.startswith("/version"):
        send(f"{BOT_VERSION} | quotes={','.join(sorted(ALLOWED_QUOTES))} | protos={','.join(sorted(ALLOWED_PROTOCOLS))}")


def poll_telegram():
    if not TOKEN:
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
            logger.info(f"[tg] recv chat_id={chat_id} text={text!r}")
            # si CHAT est défini, on ne répond qu'à ce chat
            if CHAT and chat_id != str(CHAT):
                # mais on permet /whoami pour récupérer l'ID
                if text.lower().startswith("/whoami"):
                    send_to(chat_id, f"Votre chat_id: {chat_id}")
                continue
            if not text:
                continue
            handle_command(text, chat_id)
        if last != offset:
            _save_tg_offset(last)
    except Exception as e:
        logger.warning(f"poll_telegram: {e}")

# ============ Boot message ============

def boot_message():
    b = get_balance_sol()
    send(
        f"[{BOT_VERSION}] 🚀 Bot prêt ✅\n"
        f"Seuil: {int(ENTRY_THRESHOLD*100)}% | SL: -{int(STOP_LOSS_PCT*100)}% | "
        f"Trailing: +{int(TRAILING_TRIGGER_PCT*100)}% / -{int(TRAILING_THROWBACK_PCT*100)}%\n"
        f"Max trades: {MAX_OPEN_TRADES} | Taille A+: {int(POSITION_SIZE_PCT*100)}% | A: {A_SIZE_PCT_ENV or '15%'}{' (off)' if not ALLOW_A_TRADES else ''}\n"
        f"Filtres: Liqu≥{MIN_LIQ_SOL} SOL, Vol≥{MIN_VOL_SOL} SOL, Âge≥{MIN_POOL_AGE_SEC//3600}h | Fenêtre: {PRICE_WINDOW}\n"
        f"DRY_RUN: {DRY_RUN} | PROBE: {PROBE_ENABLED} ({PROBE_SOL} SOL)\n"
        f"Quotes dyn: {','.join(sorted(ALLOWED_QUOTES))} | Whitelist fixe: {len(FIXED_TOKENS)} | dynamique max: {DYNAMIC_MAX_TOKENS}\n"
        f"Protocols: {','.join(sorted(ALLOWED_PROTOCOLS))}"
    )

# =====================
# Init & Scheduler
# =====================

def main():
    load_positions()
    load_blacklist()
    load_dynamic_tokens()
    load_token_map()

    boot_message()
    refresh_token_map()
    refresh_dynamic_tokens()
    send_boot_diagnostics()

    scheduler = BackgroundScheduler(timezone=TZ)
    scheduler.add_job(scan_market, "interval", seconds=SCAN_INTERVAL_SEC, id="scan")
    scheduler.add_job(heartbeat, "interval", minutes=HEARTBEAT_MINUTES, id="heartbeat")
    scheduler.add_job(daily_summary, "cron", hour=21, minute=0, id="daily_summary")
    scheduler.add_job(poll_telegram, "interval", seconds=15, id="tg_poll")
    scheduler.add_job(refresh_dynamic_tokens, "interval", minutes=10, id="dyn_refresh")
    scheduler.add_job(refresh_token_map, "interval", minutes=30, id="map_refresh")
    scheduler.start()

    running = True
    import signal
    def _stop(*_):
        nonlocal running; running = False
    signal.signal(signal.SIGTERM, _stop); signal.signal(signal.SIGINT, _stop)

    try:
        while running:
            time.sleep(1)
    finally:
        scheduler.shutdown(); print("[exit] bye")

if __name__ == "__main__":
    main()
