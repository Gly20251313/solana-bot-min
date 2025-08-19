# ==========================================================
#  FINAL BOT VERSION - GeckoTerminal only + Detailed logging
#  Date: 2025-08-19
# ==========================================================

# -*- coding: utf-8 -*-
"""
Bot Solana — version 'full logs détaillés'
- Journaux verbeux à chaque étape (fetch, ranking, dyn , scan, probe, buy/sell)
- Whitelist de routes élargie + modes 'strict' / 'permissive'
- Gestion des erreurs Jupiter (slippage/exactOut) avec retry et dynamic slippage
- Seuils en USD (MIN_LIQ_USD) + fallback en SOL
- Télégram + battement + récap quotidien
"""
import os, sys, time, json, base64, math, uuid, re, logging
from typing import Dict, Any, Set, Tuple, List
from datetime import datetime

import requests
import base58 as based58
import pytz
from apscheduler.schedulers.background import BackgroundScheduler

from solana.keypair import Keypair
from solana.rpc.api import Client
from solana.transaction import Transaction
from solana.rpc.types import TxOpts

# ======================
# Version & ENV
# ======================
BOT_VERSION = os.getenv("BOT_VERSION", "v2.3-full-logs-2025-08-17")

TOKEN   = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHAT    = os.getenv("TELEGRAM_CHAT_ID", "")
TZ_NAME = os.getenv("TZ", "Europe/Paris")
RPC_URL = os.getenv("RPC_URL", "https://api.mainnet-beta.solana.com")

ENTRY_THRESHOLD          = float(os.getenv("ENTRY_THRESHOLD", "0.02"))  # 2% par défaut
PRICE_WINDOW             = os.getenv("PRICE_WINDOW", "m5")
POSITION_SIZE_PCT        = float(os.getenv("POSITION_SIZE_PCT", "0.25"))
A_SIZE_PCT_ENV           = os.getenv("A_SIZE_PCT", "0.15")
STOP_LOSS_PCT            = float(os.getenv("STOP_LOSS_PCT", "0.10"))
TRAILING_TRIGGER_PCT     = float(os.getenv("TRAILING_TRIGGER_PCT", "0.30"))
TRAILING_THROWBACK_PCT   = float(os.getenv("TRAILING_THROWBACK_PCT", "0.20"))
MAX_OPEN_TRADES          = int(os.getenv("MAX_OPEN_TRADES", "2"))

SCAN_INTERVAL_SEC        = int(os.getenv("SCAN_INTERVAL_SEC", "30"))
SLIPPAGE_BPS             = int(os.getenv("SLIPPAGE_BPS", "100"))
MAX_SLIPPAGE_BPS         = int(os.getenv("MAX_SLIPPAGE_BPS", "300"))
MIN_TRADE_SOL            = float(os.getenv("MIN_TRADE_SOL", "0.03"))
DRY_RUN                  = os.getenv("DRY_RUN", "0") == "1"

PROBE_ENABLED            = os.getenv("PROBE_ENABLED", "1") == "1"
PROBE_SOL                = float(os.getenv("PROBE_SOL", "0.005"))
PROBE_SLIPPAGE_BPS       = int(os.getenv("PROBE_SLIPPAGE_BPS", "120"))
PROBE_SELL_FACTOR        = float(os.getenv("PROBE_SELL_FACTOR", "0.95"))

# Seuils marché
MIN_LIQ_USD              = float(os.getenv("MIN_LIQ_USD", "20000"))  # seuil USD
MIN_LIQ_SOL              = float(os.getenv("MIN_LIQ_SOL", "1.0"))    # fallback si MIN_LIQ_USD<=0
MIN_VOL_SOL              = float(os.getenv("MIN_VOL_SOL", "0.5"))
MIN_POOL_AGE_SEC         = int(os.getenv("MIN_POOL_AGE_SEC", "600"))
DYNAMIC_MAX_TOKENS       = int(os.getenv("DYNAMIC_MAX_TOKENS", "200"))
DYN_IGNORE_FILTERS       = os.getenv("DYN_IGNORE_FILTERS", "0") == "1"
MAX_PER_QUOTE            = int(os.getenv("MAX_PER_QUOTE", "12"))

ALLOW_A_TRADES           = os.getenv("ALLOW_A_TRADES", "1") == "1"

HEARTBEAT_MINUTES        = int(os.getenv("HEARTBEAT_MINUTES", "30"))
POSITIONS_PATH           = os.getenv("POSITIONS_PATH", "./positions.json")
BLACKLIST_PATH           = os.getenv("BLACKLIST_PATH", "./blacklist.json")
DYN_CACHE_PATH           = os.getenv("DYN_CACHE_PATH", "./dynamic_tokens.json")
TOKENMAP_CACHE_PATH      = os.getenv("TOKENMAP_CACHE_PATH", "./token_map.json")
TG_OFFSET_PATH           = os.getenv("TELEGRAM_OFFSET_PATH", "./tg_offset.json")

_MODE           = os.getenv("_MODE", "permissive").strip().lower()  # "strict"|"permissive"
DATA_SOURCE              = os.getenv("DATA_SOURCE", "").upper()  # "", "GECKO"

# Logs détaillés
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_SAMPLE_LIMIT = int(os.getenv("LOG_SAMPLE_LIMIT", "5"))
DEBUG_REJECTIONS = os.getenv("DEBUG_REJECTIONS", "1") == "1"
ROUTE_LOG_LIMIT  = int(os.getenv("ROUTE_LOG_LIMIT", "4"))
MAX_DEBUG_SENDS_PER_SCAN = int(os.getenv("MAX_DEBUG_SENDS_PER_SCAN", "6"))

logging.basicConfig(level=getattr(logging, LOG_LEVEL, logging.INFO), format='[%(levelname)s] %(message)s')
logger = logging.getLogger("bot")

# ======================
# Constants & Endpoints
# ======================
WSOL = "So11111111111111111111111111111111111111112"
USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"

JUP_QUOTE_URL = "https://lite-api.jup.ag/swap/v1/quote"
JUP_SWAP_URL  = "https://lite-api.jup.ag/swap/v1/swap"
PRICE_API     = f"https://lite-api.jup.ag/price/v3?ids={WSOL}"
JUP_TOKEN_LIST = "https://token.jup.ag/all"

DEX_SCREENER_SEARCH = "https://api.dexscreener.com/latest/dex/search"
DEX_TOKENS_BY_MINT  = "https://api.dexscreener.com/tokens/v1/solana"  # /{mint}

GECKO_BASE = os.getenv("GECKO_BASE", "https://api.geckoterminal.com/api/v2")
GECKO_PAGES = int(os.getenv("GECKO_PAGES", "7"))

ALLOWED_QUOTES: Set[str] = {
    q.strip().upper() for q in os.getenv(
        "ALLOWED_QUOTES",
        "SOL,WSOL,USDC,USDT,BONK,JITOSOL,MSOL"
    ).split(",") if q.strip()
}
ALLOWED_PROTOCOLS = {
    "Raydium","Orca","Phoenix","OpenBook","Serum","Meteora","Lifinity",
    "Whirlpool","CLMM","CPMM","DLMM","Pump.fun",
    "GooseFX","Crema","Invariant","Saros","Step","Raydium AMM"
}
EXTRA_PROTOCOLS = os.getenv("ALLOWED_PROTOCOLS_EXTRA", "")
if EXTRA_PROTOCOLS:
    ALLOWED_PROTOCOLS |= {p.strip() for p in EXTRA_PROTOCOLS.split(",") if p.strip()}

# ======================
# Telegram
# ======================
def send(msg: str):
    if not TOKEN or not CHAT:
        logger.warning("Telegram non configuré")
        return
    try:
        requests.get("https://api.telegram.org/bot"+TOKEN+"/sendMessage",
                     params={"chat_id": CHAT, "text": msg}, timeout=10)
    except Exception as e:
        logger.error("telegram error: "+str(e))

def send_to(chat_id: str, msg: str):
    if not TOKEN:
        return
    try:
        requests.get("https://api.telegram.org/bot"+TOKEN+"/sendMessage",
                     params={"chat_id": chat_id, "text": msg}, timeout=10)
    except Exception as e:
        logger.error("telegram send_to error: "+str(e))

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

# ======================
# HTTP helpers
# ======================
def http_get(url, params=None, timeout=15):
    r = requests.get(url, params=params, timeout=timeout)
    r.raise_for_status()
    return r

def http_post(url, json_payload=None, timeout=25):
    r = requests.post(url, json=json_payload, timeout=timeout)
    r.raise_for_status()
    return r

# ======================
# Keypair & RPC
# ======================
def load_keypair() -> Keypair:
    pk_str = os.getenv("SOLANA_PRIVATE_KEY", "") or os.getenv("SOL_PRIVATE_KEY", "")
    if not pk_str:
        raise ValueError("SOLANA_PRIVATE_KEY manquante")
    if pk_str.strip().startswith("["):
        secret = bytes(json.loads(pk_str))
    else:
        secret = based58.b58decode(pk_str.strip().encode("utf-8"))
    if len(secret) == 64:
        kp = Keypair.from_secret_key(secret)
    elif len(secret) == 32:
        kp = Keypair.from_seed(secret)
    else:
        raise ValueError("Clé invalide ("+str(len(secret))+" bytes)")
    logger.info("[boot] Public key: "+str(kp.public_key))
    return kp

kp = load_keypair()
client = Client(RPC_URL)
TZ = pytz.timezone(TZ_NAME)

# ======================
# State
# ======================
positions: Dict[str, Dict[str, Any]] = {}
BLACKLIST: Dict[str, float] = {}
DYNAMIC_TOKENS: Set[str] = set()
TOKEN_MAP: Dict[str, Dict[str, Any]] = {}
SYMBOL_TO_MINT: Dict[str, str] = {}
HALT_TRADING = False

def now_str():
    return datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")

def atomic_write_json(path: str, data: dict):
    d = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(d, exist_ok=True)
    tmp = os.path.join(d, ".tmp_"+uuid.uuid4().hex+".json")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)

def save_positions(): atomic_write_json(POSITIONS_PATH, {"updated_at": now_str(), "positions": positions})
def save_blacklist(): atomic_write_json(BLACKLIST_PATH, {"updated_at": now_str(), "blacklist": BLACKLIST})
def save_dynamic_tokens(): atomic_write_json(DYN_CACHE_PATH, {"updated_at": now_str(), "tokens": list(DYNAMIC_TOKENS)})
def save_token_map(): atomic_write_json(TOKENMAP_CACHE_PATH, {"updated_at": now_str(), "map": TOKEN_MAP})

def load_positions():
    global positions
    if os.path.exists(POSITIONS_PATH):
        data = json.load(open(POSITIONS_PATH, encoding="utf-8")) or {}
        positions = data.get("positions") or {}
        logger.info("[boot] positions restaurées: "+str(len(positions)))

def load_blacklist():
    global BLACKLIST
    if os.path.exists(BLACKLIST_PATH):
        BL = json.load(open(BLACKLIST_PATH, encoding="utf-8")) or {}
        BLACKLIST = BL.get("blacklist", {}) or {}
        logger.info("[boot] blacklist restaurée: "+str(len(BLACKLIST)))

def load_dynamic_tokens():
    global DYNAMIC_TOKENS
    if os.path.exists(DYN_CACHE_PATH):
        data = json.load(open(DYN_CACHE_PATH, encoding="utf-8")) or {}
        DYNAMIC_TOKENS = set(data.get("tokens") or [])
        logger.info("[boot] dynamic tokens restaurés: "+str(len(DYNAMIC_TOKENS)))

def load_token_map():
    global TOKEN_MAP, SYMBOL_TO_MINT
    if os.path.exists(TOKENMAP_CACHE_PATH):
        data = json.load(open(TOKENMAP_CACHE_PATH, encoding="utf-8")) or {}
        TOKEN_MAP = data.get("map") or {}
        SYMBOL_TO_MINT = {(v.get("symbol") or "").upper(): m for m, v in TOKEN_MAP.items() if v}
        logger.info("[boot] token map restaurée: "+str(len(TOKEN_MAP)))

# ======================
# Price & APIs
# ======================
MINT_RE = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")

def get_sol_usd() -> float:
    try:
        r = http_get(PRICE_API, timeout=10)
        data = r.json() or {}
        entry = data.get(WSOL) or (data.get("data") or {}).get(WSOL)
        price = float((entry or {}).get("usdPrice"))
        return price
    except Exception as e:
        logger.warning("prix SOL fallback 150 USD ("+str(e)+")")
        return 150.0

def gecko_get(path, params=None, timeout=10):
    return http_get(GECKO_BASE + path, params=params or {}, timeout=timeout).json()

def gecko_pairs_from_page(data) -> List[dict]:
    out = []
    if not isinstance(data, dict):
        return out
    included = {i.get("id"): i for i in (data.get("included") or [])}
    for it in (data.get("data") or []):
        attr = it.get("attributes") or {}
        rel  = it.get("relationships") or {}
        base_id  = ((rel.get("base_token")  or {}).get("data") or {}).get("id")
        quote_id = ((rel.get("quote_token") or {}).get("data") or {}).get("id")
        base  = (included.get(base_id)  or {}).get("attributes") or {}
        quote = (included.get(quote_id) or {}).get("attributes") or {}
        out.append({
            "chainId": "solana",
            "pairAddress": it.get("id"),
            "url": "https://www.geckoterminal.com/solana/pools/"+str(it.get("id")),
            "baseToken":  {"address": base.get("address"),  "symbol": (base.get("symbol") or "").upper()},
            "quoteToken": {"address": quote.get("address"), "symbol": (quote.get("symbol") or "").upper()},
            "liquidity": {"usd": float(attr.get("reserve_in_usd") or 0)},
            "volume": {"h24": float(((attr.get("volume_usd") or {}).get("h24")) or 0)},
            "priceChange": {
                "m5":  float(((attr.get("price_change_percentage") or {}).get("m5"))  or 0),
                "h1":  float(((attr.get("price_change_percentage") or {}).get("h1"))  or 0),
                "h6":  float(((attr.get("price_change_percentage") or {}).get("h6"))  or 0),
                "h24": float(((attr.get("price_change_percentage") or {}).get("h24")) or 0),
            },
            "pairCreatedAt": attr.get("pool_created_at"),
        })
    return out

def fetch_pairs() -> list:
    """DexScreener (search=solana) → Gecko fallback; GECKO mode force Gecko trending+new."""
    t0 = time.time()
    if DATA_SOURCE == "GECKO":
        results, seen = [], set()
        for p in range(1, max(1, GECKO_PAGES) + 1):
            try:
                d = gecko_get("/networks/solana/trending_pools",
                              {"page": p, "include": "base_token,quote_token"})
                page_pairs = gecko_pairs_from_page(d)
                for pair in page_pairs:
                    pid = pair.get("pairAddress")
                    if pid and pid not in seen:
                        seen.add(pid); results.append(pair)
            except Exception as e:
                logger.debug(f"[fetch] gecko trending p{p} fail: {e}")
        for p in range(1, min(2, max(1, GECKO_PAGES)) + 1):
            try:
                d = gecko_get("/networks/solana/new_pools",
                              {"page": p, "include": "base_token,quote_token"})
                page_pairs = gecko_pairs_from_page(d)
                for pair in page_pairs:
                    pid = pair.get("pairAddress")
                    if pid and pid not in seen:
                        seen.add(pid); results.append(pair)
            except Exception as e:
                logger.debug(f"[fetch] gecko new_pools p{p} fail: {e}")
        logger.info(f"[fetch] source=GECKO pairs={len(results)} in {time.time()-t0:.2f}s")
        return results

    # DexScreener
    try:
        r = http_get(DEX_SCREENER_SEARCH, params={"q": "solana"}, timeout=20)
        data = r.json() or {}
        pairs = data.get("pairs", []) or []
        out = [p for p in pairs if (p.get("chainId") or "").lower() == "solana"]
        logger.info(f"[fetch] source=Gecko pairs={len(out)} in {time.time()-t0:.2f}s")
        logger.info(f"[debug] fetch done: pairs={len(pairs)} seuils: liq>={MIN_LIQUIDITY}, m5>={MIN_M5_CHANGE}, vol>={MIN_VOL_SOL}")
        if out: return out
    except Exception as e:
        logger.debug("[fetch] DexScreener fail: "+str(e))

    # Gecko fallback
    results, seen = [], set()
    for p in range(1, max(1, GECKO_PAGES) + 1):
        try:
            d = gecko_get("/networks/solana/trending_pools",
                          {"page": p, "include": "base_token,quote_token"})
            page_pairs = gecko_pairs_from_page(d)
            for pair in page_pairs:
                pid = pair.get("pairAddress")
                if pid and pid not in seen:
                    seen.add(pid); results.append(pair)
        except Exception as e:
            logger.debug(f"[fetch] gecko trending p{p} fail: {e}")
    for p in range(1, min(2, max(1, GECKO_PAGES)) + 1):
        try:
            d = gecko_get("/networks/solana/new_pools",
                          {"page": p, "include": "base_token,quote_token"})
            page_pairs = gecko_pairs_from_page(d)
            for pair in page_pairs:
                pid = pair.get("pairAddress")
                if pid and pid not in seen:
                    seen.add(pid); results.append(pair)
        except Exception as e:
            logger.debug(f"[fetch] gecko new_pools p{p} fail: {e}")
    logger.info(f"[fetch] source=Gecko-fallback pairs={len(results)} in {time.time()-t0:.2f}s")
    logger.info(f"[debug] fetch done: pairs={len(pairs)} seuils: liq>={MIN_LIQUIDITY}, m5>={MIN_M5_CHANGE}, vol>={MIN_VOL_SOL}")
    return results

def get_price_change_pct(pair: dict, window: str) -> float:
    pc = pair.get("priceChange", {})
    val = pc.get(window)
    try: return float(val)
    except Exception: return float("nan")

def pair_liquidity_usd(pair: dict) -> float: return float((pair.get("liquidity") or {}).get("usd") or 0.0)
def pair_volume_h24_usd(pair: dict) -> float: return float((pair.get("volume") or {}).get("h24") or 0.0)

def pair_price_in_sol(pair: dict, sol_usd: float) -> float:
    price_native = pair.get("priceNative")
    quote_sym = (pair.get("quoteToken") or {}).get("symbol", "")
    if quote_sym and quote_sym.upper() in ("SOL","WSOL") and price_native:
        try: return float(price_native)
        except Exception: pass
    price_usd = pair.get("priceUsd")
    if price_usd:
        try: return float(price_usd) / max(sol_usd, 1e-9)
        except Exception: pass
    return float("nan")

def pair_age_sec(pair: dict) -> float:
    ts = pair.get("pairCreatedAt")
    try:
        if ts: return max(0, (time.time()*1000 - float(ts)) / 1000.0)
    except Exception: pass
    return 0.0

# ======================
# Ranking / Scoring
# ======================
def _candidate_score(p: dict, sol_usd: float) -> float:
    ch5 = float(get_price_change_pct(p, "m5") or 0.0)
    ch1 = float(get_price_change_pct(p, "h1") or 0.0)
    v   = pair_volume_h24_usd(p)
    liq = pair_liquidity_usd(p)
    v_term   = min(v / (sol_usd * 5.0), 2.0)
    liq_term = min(liq / (sol_usd * 10.0), 1.0)
    return (ch5 * 1.0) + (max(ch1, 0.0) * 0.5) + v_term + liq_term

def rank_candidates(pairs: list, sol_usd: float) -> list:
    ranked = sorted(pairs, key=lambda p: _candidate_score(p, sol_usd), reverse=True)
    # Log top sample
    for i, p in enumerate(ranked[:LOG_SAMPLE_LIMIT]):
        b = (p.get("baseToken") or {}).get("symbol") or "?"
        q = (p.get("quoteToken") or {}).get("symbol") or "?"
        logger.info(f"[rank] top{i+1}: {b}/{q} liq=${pair_liquidity_usd(p):.0f} vol24=${pair_volume_h24_usd(p):.0f} m5={get_price_change_pct(p,'m5'):.1f}% url={p.get('url','-')}")
    return ranked

# ======================
# Whitelist patterns
# ======================
def _build_allowed_patterns():
    pats = set()
    for p in ALLOWED_PROTOCOLS:
        s = str(p).lower().strip()
        if not s: continue
        pats.add(s)
        if s == "orca": pats.update(["whirlpool"])
        if s == "raydium": pats.update(["raydium clmm","raydium cpmm","raydium amm"])
        if s in ("openbook","serum","phoenix"): pats.update(["openbook","serum","phoenix"])
        if s == "lifinity": pats.update(["lifinity"])
        if s == "meteora": pats.update(["meteora","dlmm"])
        if s == "pump.fun": pats.update(["pump.fun","amm"])
        pats.update(["cpmm","clmm","dlmm"])
    return pats
_ALLOWED_PATTERNS = _build_allowed_patterns()

def route_is_ed(quote: dict, return_labels: bool=False):
    rp = quote.get("routePlan") or quote.get("marketInfos") or []
    labels = []
    if not isinstance(rp, list):
        return (False, labels) if return_labels else False
    unknowns = []
    for step in rp:
        info = step.get("swapInfo") or step
        label = (info.get("label") or info.get("protocol") or "").strip()
        labels.append(label)
        lbl = label.lower()
        if not any(pat in lbl for pat in _ALLOWED_PATTERNS):
            unknowns.append(label)
    if unknowns and _MODE == "strict":
        return (False, labels) if return_labels else False
    if unknowns and _MODE == "permissive":
        logger.info("route tolerated (permissive): "+", ".join([u for u in unknowns if u]))
    return (True, labels) if return_labels else True

def route_is_ed_relaxed(quote: dict, return_labels: bool=False):
    """If _MODE in {'off','permissive'}: allow everything (probe still protects)."""
    try:
        if '_MODE' in globals() and _MODE in {'off','permissive'}:
            return (True, ['*']) if return_labels else True
    except Exception:
        pass
    return route_is_ed_relaxed(quote, return_labels=return_labels)


# ======================
# Jupiter (quote/swap)
# ======================
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

def jup_swap_tx(quote_resp: dict, user_pubkey: str, wrap_unwrap_sol: bool=True, use_dynamic: bool=True):
    payload = {
        "quoteResponse": quote_resp,
        "userPublicKey": user_pubkey,
        "wrapAndUnwrapSol": wrap_unwrap_sol,
        "asLegacyTransaction": True,
    }
    if use_dynamic:
        payload["dynamicSlippage"] = {"minBps": 50, "maxBps": MAX_SLIPPAGE_BPS}
        payload["prioritizationFeeLamports"] = "auto"
        payload["dynamicComputeUnitLimit"] = True

    r = http_post(JUP_SWAP_URL, json_payload=payload, timeout=25)
    data = r.json()
    return data["swapTransaction"]

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

def _is_jup_slippage_err(err: Exception) -> bool:
    s = str(err)
    return ("0x1771" in s) or ("6001" in s) or ("6017" in s) or ("0x1789" in s) or ("6025" in s)

# ======================
# Wallet / SPL
# ======================
def get_balance_sol() -> float:
    try:
        resp = client.get_balance(kp.public_key)
        lamports = (resp.get("result") or {}).get("value", 0)
        return lamports / 1_000_000_000
    except Exception as e:
        logger.warning("get_balance_sol error: "+str(e)); return 0.0

def get_token_balance(mint: str) -> int:
    try:
        resp = client.get_token_accounts_by_owner_json_parsed(
            kp.public_key, {"mint": mint}, commitment="confirmed"
        )
        vals = (resp.get("result") or {}).get("value") or []
        total = 0
        for v in vals:
            info = (((v or {}).get("account") or {}).get("data") or {}).get("parsed", {})
            amt = (((info.get("info") or {}).get("tokenAmount")) or {}).get("amount")
            if amt is not None: total += int(amt)
        return total
    except Exception:
        return 0

# ======================
# Utils
# ======================
def open_positions_count() -> int: return len(positions)
def can_open_more() -> bool: return open_positions_count() < MAX_OPEN_TRADES
def new_trade_id() -> str: return uuid.uuid4().hex[:8]
def ok(b: bool) -> str: return "✅" if b else "❌"

def short_mint(m: str) -> str:
    return (m[:4]+"…"+m[-4:]) if (m and len(m) > 10) else (m or "?")

def log_env_config():
    send(
        f"[{BOT_VERSION}] ⚙️ ENV\n"
        f"WL-mode={_MODE} | DATA_SOURCE={DATA_SOURCE}\n"
        f"MIN_LIQ_USD={MIN_LIQ_USD} | MIN_LIQ_SOL={MIN_LIQ_SOL} | MIN_VOL_SOL={MIN_VOL_SOL} | AGE≥{MIN_POOL_AGE_SEC}s\n"
        f"Quotes dyn={','.join(sorted(ALLOWED_QUOTES))}\n"
        f"Protos={','.join(sorted(ALLOWED_PROTOCOLS))}\n"
        f"Scan={SCAN_INTERVAL_SEC}s | MaxTrades={MAX_OPEN_TRADES} | DRY_RUN={DRY_RUN}"
    )

# ==============================
# Token map & résolution
# ==============================
def refresh_token_map():
    global TOKEN_MAP, SYMBOL_TO_MINT
    try:
        r = http_get(JUP_TOKEN_LIST, timeout=20)
        data = r.json() or []
        new_map, sym_map = {}, {}
        for t in data:
            mint = t.get("address") or t.get("mint")
            symbol = (t.get("symbol") or "").upper()
            if not mint or not symbol: continue
            new_map[mint] = {"symbol": symbol, "decimals": t.get("decimals"), "name": t.get("name")}
            if symbol not in sym_map: sym_map[symbol] = mint
        TOKEN_MAP = new_map; SYMBOL_TO_MINT = sym_map
        save_token_map()
        logger.info(f"[tokenmap] mints={len(TOKEN_MAP)} symbols={len(SYMBOL_TO_MINT)}")
    except Exception as e:
        logger.warning("refresh_token_map: "+str(e))

def resolve_symbol_or_mint(val: str) -> Tuple[str, str]:
    s = val.strip()
    if MINT_RE.match(s):
        info = TOKEN_MAP.get(s) or {}; return s, (info.get("symbol") or "?")
    sym = s.upper(); mint = SYMBOL_TO_MINT.get(sym)
    if mint: return mint, sym
    try:
        r = http_get(DEX_SCREENER_SEARCH, params={"q": sym}, timeout=10)
        pairs = (r.json() or {}).get("pairs", []) or []
        pairs = [p for p in pairs if (p.get("chainId") or "").lower()=="solana"]
        if pairs:
            best = max(pairs, key=lambda p: float((p.get("liquidity") or {}).get("usd") or 0))
            mint2 = (best.get("baseToken") or {}).get("address")
            if mint2: return mint2, sym
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

def probe_trade(mint: str, user_pubkey: str):
    if not PROBE_ENABLED: return True
    try:
        lamports = max(1, int(PROBE_SOL * 1_000_000_000))

        q_buy  = jup_quote(WSOL, mint, lamports, PROBE_SLIPPAGE_BPS)
        if not q_buy:
            logger.info("🧪 probe BUY: quote vide"); send("🧪 probe BUY: quote vide"); return None
        ok_buy, buy_labels = route_is_ed_relaxed(q_buy, return_labels=True)
        logger.info(f"🧪 probe BUY route labels={buy_labels} ok={ok_buy}")
        if not ok_buy: return None

        q_sell = jup_quote(mint, WSOL, int(lamports * PROBE_SELL_FACTOR), PROBE_SLIPPAGE_BPS)
        if not q_sell:
            logger.info("🧪 probe SELL: quote vide"); send("🧪 probe SELL: quote vide"); return None
        ok_sell, sell_labels = route_is_ed_relaxed(q_sell, return_labels=True)
        logger.info(f"🧪 probe SELL route labels={sell_labels} ok={ok_sell}")
        if not ok_sell: return None

        if DRY_RUN: return True

        try:
            txb64 = jup_swap_tx(q_buy, user_pubkey, use_dynamic=True)
            _ = sign_and_send(txb64)
        except Exception as e:
            if _is_jup_slippage_err(e):
                logger.info("🧪 probe BUY retry slippage++")
                q_buy = jup_quote(WSOL, mint, lamports, min(PROBE_SLIPPAGE_BPS*2, MAX_SLIPPAGE_BPS))
                txb64 = jup_swap_tx(q_buy, user_pubkey, use_dynamic=True)
                _ = sign_and_send(txb64)
            else:
                raise

        try:
            txb64 = jup_swap_tx(q_sell, user_pubkey, use_dynamic=True)
            _ = sign_and_send(txb64)
        except Exception as e:
            if _is_jup_slippage_err(e):
                logger.info("🧪 probe SELL retry slippage++")
                q_sell = jup_quote(mint, WSOL, int(lamports * PROBE_SELL_FACTOR), min(PROBE_SLIPPAGE_BPS*2, MAX_SLIPPAGE_BPS))
                txb64 = jup_swap_tx(q_sell, user_pubkey, use_dynamic=True)
                _ = sign_and_send(txb64)
            else:
                raise

        return True
    except Exception as e:
        logger.warning("probe_trade: "+str(e)); send("🧪 probe exception: "+str(e)); return False

# =================
# Sizing & scoring
# =================
def score_pair(chg_pct: float, liq_usd: float, vol_usd: float, age_sec: float, min_liq_usd: float, min_vol_usd: float) -> str:
    if chg_pct < ENTRY_THRESHOLD * 100: return "B"
    hard = (liq_usd >= min_liq_usd) and (vol_usd >= min_vol_usd) and (age_sec >= MIN_POOL_AGE_SEC)
    if hard: return "A+"
    soft = (liq_usd >= 0.9*min_liq_usd) and (vol_usd >= min_vol_usd) and (age_sec >= 0.5*MIN_POOL_AGE_SEC)
    return "A" if soft else "B"

def size_for_score(balance_sol: float, score: str) -> float:
    if score == "A+": pct = POSITION_SIZE_PCT
    elif score == "A" and ALLOW_A_TRADES: pct = float(A_SIZE_PCT_ENV)
    else: return 0.0
    size_sol = max(balance_sol * pct, MIN_TRADE_SOL)
    return min(size_sol, balance_sol * 0.99)

# ==========================
# Dynamic
# ==========================
def refresh_dynamic_tokens():
    global DYNAMIC_TOKENS
    try:
        sol_usd = get_sol_usd()
        min_liq_usd = MIN_LIQ_USD if MIN_LIQ_USD > 0 else (MIN_LIQ_SOL * sol_usd)
        min_vol_usd = MIN_VOL_SOL * sol_usd

        pairs = fetch_pairs()
        if not pairs:
            DYNAMIC_TOKENS = set(); save_dynamic_tokens()
            send("⚠️ dynamic=0 (source vide)"); return DYNAMIC_TOKENS

        pairs = rank_candidates(pairs, sol_usd)

        found = set()
        per_quote: Dict[str, int] = {}
        rej_liq = rej_vol = rej_age = rej_quote = rej_dupe = 0

        for p in pairs:
            if len(found) >= DYNAMIC_MAX_TOKENS: break
            if (p.get("chainId") or "").lower() != "solana": continue

            base_mint = (p.get("baseToken") or {}).get("address")
            base_sym  = (p.get("baseToken") or {}).get("symbol")
            quote_sym = ((p.get("quoteToken") or {}).get("symbol") or "").upper()
            if not base_mint: continue
            if base_mint in found: rej_dupe += 1; continue
            if quote_sym not in ALLOWED_QUOTES: rej_quote += 1; continue
            if per_quote.get(quote_sym, 0) >= MAX_PER_QUOTE: continue

            if not DYN_IGNORE_FILTERS:
                liq_usd = pair_liquidity_usd(p)
                vol_usd = pair_volume_h24_usd(p)
                age = pair_age_sec(p)
                if liq_usd < min_liq_usd: rej_liq += 1; continue
                if vol_usd < min_vol_usd: rej_vol += 1; continue
                if age < MIN_POOL_AGE_SEC: rej_age += 1; continue

            found.add(base_mint)
            per_quote[quote_sym] = per_quote.get(quote_sym, 0) + 1

        DYNAMIC_TOKENS = found
        save_dynamic_tokens()

        sample = list(DYNAMIC_TOKENS)[:LOG_SAMPLE_LIMIT]
        logger.info(f"[dyn] tokens={len(DYNAMIC_TOKENS)} sample={','.join([short_mint(x) for x in sample])}")
        send("✅ dynamic="+str(len(DYNAMIC_TOKENS))
             + f" (rejets liq={rej_liq}, vol={rej_vol}, age={rej_age}, quote={rej_quote}, dupe={rej_dupe})")
        return DYNAMIC_TOKENS
    except Exception as e:
        send("⚠️ dynamic=0 (erreur: "+str(e)+")"); return set()

def final_() -> set:
    # Whitelist finale désactivée : on ne filtre plus rien
    return set(DYNAMIC_TOKENS)

def is_in_final_(mint: str) -> bool:
    # Toujours vrai : tout token est autorisé
    return True
True

def is_in_final_(mint: str) -> bool:
    # Toujours vrai : tout token est autorisé
    return True

def is_in_final_(mint: str) -> bool:
    return True
    """Respect FINAL_WL_MODE if present. If off -> always True."""
    try:
        if 'FINAL_WL_MODE' in globals() and not FINAL_WL_MODE:
            return True
        wl = final_()
        return mint in wl
    except Exception:
        return ('FINAL_WL_MODE' in globals() and not FINAL_WL_MODE)


# ======================
# Trading
# ======================
def enter_trade(pair: dict, sol_usd: float, score: str):
    if not can_open_more(): return
    base_mint = (pair.get("baseToken") or {}).get("address")
    base_sym  = (pair.get("baseToken") or {}).get("symbol") or "TOKEN"
    pair_url  = pair.get("url") or "https://dexscreener.com/solana"
    wl = final_()
    if not base_mint or base_mint in positions or base_mint not in wl or is_blacklisted(base_mint): return
    balance = get_balance_sol()
    size_sol = size_for_score(balance, score)
    if size_sol <= 0: return
    lamports = int(size_sol * 1_000_000_000)
    if lamports <= 0:
        send("❌ Achat annulé: solde SOL insuffisant"); return
    trade_id = new_trade_id()

    probe_res = probe_trade(base_mint, str(kp.public_key))
    if probe_res is False:
        blacklist(base_mint, hours=24); send("🧪 Sonde KO → blacklist 24h : "+base_mint); return
    elif probe_res is None:
        send("🧪 Sonde skip (route/quote) pour "+base_sym+" — pas de blacklist"); return

    try:
        q = jup_quote(WSOL, base_mint, lamports, SLIPPAGE_BPS)
        ok_route, labels = route_is_ed_relaxed(q, return_labels=True)
        if not q or not ok_route:
            send("⛔ Route non  pour "+base_sym+" — labels="+", ".join([l for l in labels if l])+" — rejet"); return
        sig = sign_and_send(jup_swap_tx(q, str(kp.public_key), use_dynamic=True))
        send("📈 Achat "+base_sym+" ["+score+"]\nMontant: "+f"{size_sol:.4f}"+" SOL\nPair: "+pair_url+"\nID: "+trade_id+"\nTx: "+str(sig))
    except Exception as e:
        send("❌ Achat "+base_sym+" échoué: "+str(e)); return

    price_sol = pair_price_in_sol(pair, sol_usd)
    positions[base_mint] = {
        "symbol": base_sym, "entry_price_sol": price_sol, "peak_price_sol": price_sol,
        "pair_url": pair_url, "opened_at": now_str(), "score": score, "trade_id": trade_id,
    }
    save_positions()

def close_position(mint: str, symbol: str, reason: str) -> bool:
    try:
        bal_amount = get_token_balance(mint)
        if bal_amount <= 0:
            send(reason+" "+symbol+": aucun solde token détecté (déjà vendu ?)"); return True
        q = jup_quote(mint, WSOL, int(bal_amount * 0.99), SLIPPAGE_BPS)
        ok_route, labels = route_is_ed_relaxed(q, return_labels=True)
        if not q or not ok_route:
            send("⛔ Route non  à la vente pour "+symbol+" — labels="+", ".join([l for l in labels if l])+" — tentative annulée"); return False
        sig = sign_and_send(jup_swap_tx(q, str(kp.public_key), use_dynamic=True))
        send(reason+" "+symbol+"\nTx: "+str(sig))
        return True
    except Exception as e:
        send("❌ Vente "+symbol+" échouée: "+str(e)); return False

def check_positions(sol_usd: float):
    to_close = []
    for mint, pos in list(positions.items()):
        symbol = pos["symbol"]
        entry  = pos.get("entry_price_sol") or 0.0
        peak   = pos.get("peak_price_sol") or entry
        try:
            r = http_get(DEX_TOKENS_BY_MINT + "/" + mint, timeout=15)
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
    for m in to_close: positions.pop(m, None)
    if to_close: save_positions()

# ====================
# Market scan
# ====================
def scan_market():
    if HALT_TRADING: return
    try:
        sol_usd = get_sol_usd()
        min_liq_usd = MIN_LIQ_USD if MIN_LIQ_USD > 0 else (MIN_LIQ_SOL * sol_usd)
        min_vol_usd = MIN_VOL_SOL * sol_usd

        pairs = fetch_pairs()
        if not pairs: return
        pairs = rank_candidates(pairs, sol_usd)
        wl = final_()
        candidates = []
        debug_sent = 0

        for p in pairs:
            base_mint = (p.get("baseToken") or {}).get("address")
            base_sym  = (p.get("baseToken") or {}).get("symbol") or "?"
            if not base_mint: continue
            if base_mint not in wl:
                if DEBUG_REJECTIONS and debug_sent < MAX_DEBUG_SENDS_PER_SCAN:
                    msg = f"🔎 SKIP {base_sym} {short_mint(base_mint)}: hors  finale"; logger.info(msg); send(msg); debug_sent += 1
                continue

            liq_usd = pair_liquidity_usd(p)
            vol_usd = pair_volume_h24_usd(p)
            age = pair_age_sec(p)

            if not DYN_IGNORE_FILTERS:
                reasons = []
                if liq_usd < min_liq_usd: reasons.append(f"liq ${liq_usd:.0f}<{min_liq_usd:.0f}")
                if vol_usd < min_vol_usd: reasons.append(f"vol ${vol_usd:.0f}<{min_vol_usd:.0f}")
                if age < MIN_POOL_AGE_SEC: reasons.append(f"age {int(age)}<{MIN_POOL_AGE_SEC}s")
                if reasons:
                    if DEBUG_REJECTIONS and debug_sent < MAX_DEBUG_SENDS_PER_SCAN:
                        msg = f"🔎 SKIP {base_sym} {short_mint(base_mint)}: "+", ".join(reasons); logger.info(msg); send(msg); debug_sent += 1
                    continue

            chg = get_price_change_pct(p, PRICE_WINDOW)
            if math.isnan(chg): continue
            score = score_pair(chg, liq_usd, vol_usd, age, min_liq_usd, min_vol_usd)
            if score in ("A+","A"):
                candidates.append((chg, score, p))

        candidates.sort(key=lambda x: x[0], reverse=True)
        opened = 0
        for chg, score, p in candidates:
            if not can_open_more(): break
            base_mint = (p.get("baseToken") or {}).get("address")
            if not base_mint or base_mint in positions: continue
            enter_trade(p, sol_usd, score); opened += 1

        check_positions(sol_usd)

        if DEBUG_REJECTIONS and opened == 0:
            logger.info(f"[scan] aucun trade ouvert — candidats={len(candidates)} dyn={len(DYNAMIC_TOKENS)}")

    except Exception as e:
        send("⚠️ [scan error] "+type(e).__name__+": "+str(e))

# ==============================
# Diagnostics & résumés
# ==============================
def health_check():
    results = {}
    try:
        bal = get_balance_sol(); results["rpc"] = bal >= 0; results["balance"] = bal
    except Exception as e:
        results["rpc"] = False; results["balance"] = "err: "+str(e)
    try:
        p = get_sol_usd(); results["jup_price"] = p > 0; results["sol_usd"] = p
    except Exception as e:
        results["jup_price"] = False; results["sol_usd"] = "err: "+str(e)
    try:
        pairs = fetch_pairs(); results["dex_search"] = len(pairs) > 0; results["pairs_count"] = len(pairs)
    except Exception as e:
        results["dex_search"] = False; results["pairs_count"] = "err: "+str(e)
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
        "["+BOT_VERSION+"] 🩺 Self-check démarrage\n"
        + "RPC: "+ok(res.get("rpc", False))+" | Solde: "+str(res.get("balance"))+"\n"
        + "Jupiter Price: "+ok(res.get("jup_price", False))+" | SOL≈"+str(res.get("sol_usd"))+"\n"
        + "Source marché: "+ok(res.get("dex_search", False))+" | pairs="+str(res.get("pairs_count"))+"\n"
        + "Jupiter quote: "+ok(res.get("jup_quote", False))+"\n"
        + "Params ⇒ Seuil "+str(int(ENTRY_THRESHOLD*100))+"% | SL -"+str(int(STOP_LOSS_PCT*100))+"% | "
        + "Trailing +"+str(int(TRAILING_TRIGGER_PCT*100))+"% / -"+str(int(TRAILING_THROWBACK_PCT*100))+"% | "
        + "Max "+str(MAX_OPEN_TRADES)+" | Taille A+: "+str(int(POSITION_SIZE_PCT*100))+"% | A: "+str(int(float(A_SIZE_PCT_ENV)*100))+"%\n"
        + "Filtres: Liqu≥"+(str(MIN_LIQ_USD)+" USD" if MIN_LIQ_USD>0 else (str(MIN_LIQ_SOL)+" SOL"))
        + ", Vol≥"+str(MIN_VOL_SOL)+" SOL, Âge≥"+str(MIN_POOL_AGE_SEC//60)+"min | Fenêtre: "+PRICE_WINDOW+"\n"
        + "Quotes dyn: "+",".join(sorted(ALLOWED_QUOTES))+" | Prot: "+",".join(sorted(ALLOWED_PROTOCOLS))+" | WL-mode: "+_MODE
    )
    send(msg)

def heartbeat():
    send("⏱️ Heartbeat "+now_str()+" | positions: "+str(len(positions))+" | blacklist: "+str(len(BLACKLIST))+" | dyn: "+str(len(DYNAMIC_TOKENS))+" | halt="+str(HALT_TRADING))

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
    send("📰 Résumé quotidien "+now_str()+"\n"+body)

# ======================
# Telegram commands
# ======================
def handle_command(text: str, chat_id: str = None):
    global HALT_TRADING
    t = text.strip(); tl = t.lower()
    if tl.startswith("/start"):
        HALT_TRADING = False; send("▶️ Trading activé.")
    elif tl.startswith("/stop"):
        HALT_TRADING = True; send("⏸️ Trading en pause.")
    elif tl.startswith("/status"):
        send("ℹ️ Status "+now_str()+" | positions: "+str(len(positions))+" | blacklist: "+str(len(BLACKLIST))+" | dyn: "+str(len(DYNAMIC_TOKENS))+" | halt="+str(HALT_TRADING))
    elif tl.startswith("/testtrade"):
        try:
            amt = max(0.002, PROBE_SOL); lamports = int(amt * 1_000_000_000)
            q = jup_quote(WSOL, USDC, lamports, min(SLIPPAGE_BPS, 50))
            ok_route, labels = route_is_ed_relaxed(q, return_labels=True)
            if not q or not ok_route: send("🔍 TestTrade: route non  | labels="+", ".join([l for l in labels if l])); return
            sig1 = sign_and_send(jup_swap_tx(q, str(kp.public_key), use_dynamic=True))
            q2 = jup_quote(USDC, WSOL, int(float(q.get("outAmount","0"))*0.98), min(SLIPPAGE_BPS, 50))
            ok_route2, labels2 = route_is_ed_relaxed(q2, return_labels=True)
            if not q2 or not ok_route2: send("🔍 TestTrade SELL: route non  | labels="+", ".join([l for l in labels2 if l])); return
            sig2 = sign_and_send(jup_swap_tx(q2, str(kp.public_key), use_dynamic=True))
            send("✅ TestTrade OK\nBuy Tx: "+str(sig1)+"\nSell Tx: "+str(sig2))
        except Exception as e:
            send("❌ TestTrade error: "+str(e))
    elif tl.startswith("/refresh_tokens"):
        refresh_token_map(); refresh_dynamic_tokens()
    elif tl.startswith("/dyninfo"):
        try: refresh_dynamic_tokens()
        except Exception as e: send("/dyninfo erreur: "+str(e))
    elif tl.startswith("/forcebuy"):
        try:
            parts = t.split()
            if len(parts) < 3: send("Usage: /forcebuy <SYMBOL_ou_MINT> <montant_SOL>"); return
            token = parts[1]; size_sol = float(parts[2])
            mint, sym = resolve_symbol_or_mint(token)
            if not mint: send("Token introuvable: "+token); return
            if is_blacklisted(mint): send("Token blacklist: "+mint); return
            if not PROBE_ENABLED or probe_trade(mint, str(kp.public_key)):
                lamports = int(size_sol * 1_000_000_000)
                q = jup_quote(WSOL, mint, lamports, SLIPPAGE_BPS)
                ok_route, labels = route_is_ed_relaxed(q, return_labels=True)
                if not q or not ok_route:
                    send("Route non ée pour /forcebuy | labels="+", ".join([l for l in labels if l])); return
                sig = sign_and_send(jup_swap_tx(q, str(kp.public_key), use_dynamic=True))
                send(f"🚨 FORCE BUY {sym} ({mint})\nMontant: {size_sol:.4f} SOL\nTx: {sig}")
            else:
                send("Sonde anti-honeypot KO — /forcebuy annulé.")
        except Exception as e:
            send("/forcebuy erreur: "+str(e))
    elif tl.startswith("/reset_offset"):
        try:
            if os.path.exists(TG_OFFSET_PATH): os.remove(TG_OFFSET_PATH)
            send("♻️ Telegram offset reset. Réessayez vos commandes.")
        except Exception as e:
            send("reset_offset erreur: "+str(e))
    elif tl.startswith("/whoami"):
        if chat_id: send_to(chat_id, "Votre chat_id: "+chat_id)
        else: send("(whoami) chat_id indisponible")
    elif tl.startswith("/version"):
        send(BOT_VERSION+" | quotes="+",".join(sorted(ALLOWED_QUOTES))+" | protos="+",".join(sorted(ALLOWED_PROTOCOLS))+" | WL-mode="+_MODE)

def poll_telegram():
    if not TOKEN: return
    try:
        offset = _load_tg_offset()
        r = http_get("https://api.telegram.org/bot"+TOKEN+"/getUpdates",
                     params={"timeout": 0, "offset": offset+1, "allowed_updates": json.dumps(["message"])},
                     timeout=10)
        data = r.json() or {}; upd = data.get("result", []) or []; last = offset
        for u in upd:
            last = max(last, int(u.get("update_id", 0)))
            msg = u.get("message") or {}
            chat_id = str(((msg.get("chat") or {}).get("id")) or "")
            text = (msg.get("text") or "").strip()
            if CHAT and chat_id != str(CHAT):
                if text.lower().startswith("/whoami"): send_to(chat_id, "Votre chat_id: "+chat_id)
                continue
            if not text: continue
            handle_command(text, chat_id)
        if last != offset: _save_tg_offset(last)
    except Exception as e:
        logger.warning("poll_telegram: "+str(e))

# ======================
# Boot
# ======================
def boot_message():
    b = get_balance_sol()
    send("["+BOT_VERSION+"] 🚀 Bot prêt ✅\n"
         + "Seuil: "+str(int(ENTRY_THRESHOLD*100))+"% | SL: -"+str(int(STOP_LOSS_PCT*100))+"% | "
         + "Trailing: +"+str(int(TRAILING_TRIGGER_PCT*100))+"% / -"+str(int(TRAILING_THROWBACK_PCT*100))+"%\n"
         + "Max trades: "+str(MAX_OPEN_TRADES)+" | Taille A+: "+str(int(POSITION_SIZE_PCT*100))+"% | A: "+str(int(float(A_SIZE_PCT_ENV)*100))+"%\n"
         + "Filtres: Liqu≥"+(str(MIN_LIQ_USD)+" USD" if MIN_LIQ_USD>0 else (str(MIN_LIQ_SOL)+" SOL"))
         + ", Vol≥"+str(MIN_VOL_SOL)+" SOL, Âge≥"+str(MIN_POOL_AGE_SEC//60)+"min | Fenêtre: "+PRICE_WINDOW+"\n"
         + "DRY_RUN: "+str(DRY_RUN)+" | PROBE: "+str(PROBE_ENABLED)+" ("+str(PROBE_SOL)+" SOL; "+str(PROBE_SLIPPAGE_BPS)+"bps)\n"
         + "Quotes dyn: "+",".join(sorted(ALLOWED_QUOTES))+" | dynamique max: "+str(DYNAMIC_MAX_TOKENS)+"\n"
         + "Protocols: "+",".join(sorted(ALLOWED_PROTOCOLS))+" | WL-mode: "+_MODE
    )

def main():
    load_positions(); load_blacklist(); load_dynamic_tokens(); load_token_map()
    boot_message(); log_env_config(); refresh_token_map(); refresh_dynamic_tokens(); send_boot_diagnostics()

    scheduler = BackgroundScheduler(timezone=TZ)
    scheduler.add_job(scan_market, "interval", seconds=SCAN_INTERVAL_SEC, id="scan")
    scheduler.add_job(heartbeat, "interval", minutes=HEARTBEAT_MINUTES, id="heartbeat")
    scheduler.add_job(daily_summary, "cron", hour=21, minute=0, id="daily_summary")
    scheduler.add_job(poll_telegram, "interval", seconds=15, id="tg_poll")
    scheduler.add_job(refresh_dynamic_tokens, "interval", minutes=10, id="dyn_refresh")
    scheduler.start()

    running = True
    import signal
    def _stop(*_):
        nonlocal running; running = False
    signal.signal(signal.SIGTERM, _stop); signal.signal(signal.SIGINT, _stop)

    try:
        while running: time.sleep(1)
    finally:
        scheduler.shutdown(); logger.info("[exit] bye")

if __name__ == "__main__":
    main()


def _pair_name(p: dict) -> str:
    try:
        bs = (p.get("baseToken") or {}).get("symbol") or "TOKEN"
        qs = (p.get("quoteToken") or {}).get("symbol") or ""
        return f"{bs}/{qs}" if qs else bs
    except Exception:
        return "PAIR"

def _reject_log(p: dict, reason: str, detail: str = ""):
    if not ('DEBUG_REJECT' in globals() and DEBUG_REJECT):
        return
    try:
        nm = _pair_name(p)
        url = p.get("url") or ""
        if detail:
            logger.info(f"[reject][{reason}] {nm} {detail} {url}")
        else:
            logger.info(f"[reject][{reason}] {nm} {url}")
    except Exception as e:
        logger.debug("reject_log err: " + str(e))


# ====================
# Patched scan_market with explicit reject reasons
# ====================
def scan_market():
    if 'HALT_TRADING' in globals() and HALT_TRADING:
        return
    try:
        sol_usd = get_sol_usd()
        min_liq_usd = MIN_LIQ_SOL * sol_usd
        min_vol_usd = MIN_VOL_SOL * sol_usd

        pairs = fetch_pairs()
        if not pairs:
            logger.info("[scan] no pairs fetched")
            return

        pairs = rank_candidates(pairs, sol_usd)

        candidates = []
        seen_mints = set()

        for p in pairs:
            try:
                if (p.get("chainId") or "").lower() != "solana":
                    _reject_log(p, "chain", "not solana")
                    continue

                base_mint = (p.get("baseToken") or {}).get("address")
                quote_sym = ((p.get("quoteToken") or {}).get("symbol") or "").upper()

                if not base_mint:
                    _reject_log(p, "mint", "missing base mint")
                    continue

                if base_mint in seen_mints:
                    _reject_log(p, "dupe", "same base mint seen in this batch")
                    continue

                if not is_in_final_(base_mint):
                    _reject_log(p, "", "not in final ")
                    continue

                if 'ALLOWED_QUOTES' in globals() and ALLOWED_QUOTES:
                    if quote_sym and (quote_sym not in ALLOWED_QUOTES):
                        _reject_log(p, "quote", f"{quote_sym} not allowed")
                        continue

                liq_usd = pair_liquidity_usd(p)
                if liq_usd < min_liq_usd:
                    _reject_log(p, "liq", f"${liq_usd:,.0f} < ${min_liq_usd:,.0f}")
                    continue

                vol_usd = pair_volume_h24_usd(p)
                if vol_usd < min_vol_usd:
                    _reject_log(p, "vol", f"${vol_usd:,.0f} < ${min_vol_usd:,.0f}")
                    continue

                age = pair_age_sec(p)
                if age < MIN_POOL_AGE_SEC:
                    _reject_log(p, "age", f"{int(age)}s < {int(MIN_POOL_AGE_SEC)}s")
                    continue

                chg = get_price_change_pct(p, PRICE_WINDOW)
                if chg != chg:  # NaN
                    _reject_log(p, "price_change", "NaN")
                    continue

                score = score_pair(chg, liq_usd, vol_usd, age, min_liq_usd, min_vol_usd)
                if score not in ("A+","A") or (score == "A" and not ALLOW_A_TRADES):
                    _reject_log(p, "score", f"{score} filtered")
                    continue

                candidates.append((chg, score, p))
                seen_mints.add(base_mint)

            except Exception as e:
                logger.debug("[scan][pair] error: " + str(e))
                continue

        candidates.sort(key=lambda x: x[0], reverse=True)

        if not candidates:
            logger.info("[scan] aucun trade ouvert — candidats=0 dyn=" + str(len(DYNAMIC_TOKENS)))
        else:
            logger.info("[scan] candidats=" + str(len(candidates)) + " dyn=" + str(len(DYNAMIC_TOKENS)))

        for chg, score, p in candidates:
            try:
                if not can_open_more():
                    break
                base_mint = (p.get("baseToken") or {}).get("address")
                if not base_mint or base_mint in positions:
                    _reject_log(p, "pos", "already in positions or missing mint")
                    continue
                enter_trade(p, sol_usd, score)
            except Exception as e:
                logger.debug("[scan][enter] " + str(e))

        check_positions(sol_usd)

    except Exception as e:
        try:
            send("⚠️ [scan error] " + type(e).__name__ + ": " + str(e))
        except Exception:
            logger.warning("[scan error] " + type(e).__name__ + ": " + str(e))


# Whitelist finale totalement retirée
