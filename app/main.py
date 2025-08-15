# main.py — Bot Solana (DexScreener + Jupiter Lite) prêt Railway
# - Endpoints corrigés (DexScreener /search & tokens/v1 ; Jupiter Price v3 + swap/quote Lite)
# - Price API v3: requête par mint WSOL et lecture de usdPrice
# - Self-check au démarrage (Telegram)
# - Heartbeat par défaut toutes les 30 min (HEARTBEAT_MINUTES)
# - Résumé quotidien à 21:00 Europe/Paris
# - Retries réseau
# - Persistance des positions (positions.json) + anti-réachat
# - DRY_RUN=1 pour tester sans envoyer les transactions

import os, time, json, base64, requests, base58, math, tempfile, shutil
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
HEARTBEAT_MINUTES        = int(os.getenv("HEARTBEAT_MINUTES", "30"))     # demi-heure
DRY_RUN                  = os.getenv("DRY_RUN", "0") == "1"
POSITIONS_PATH           = os.getenv("POSITIONS_PATH", "./positions.json")

# Filtres sécurité, définis en SOL puis convertis en USD via prix SOL live
MIN_LIQ_SOL              = float(os.getenv("MIN_LIQ_SOL", "10.0"))
MIN_VOL_SOL              = float(os.getenv("MIN_VOL_SOL", "5.0"))

# ==== Mints / Endpoints ====
WSOL = "So11111111111111111111111111111111111111112"

# Jupiter Lite (public, stable)
JUP_QUOTE_URL = "https://lite-api.jup.ag/swap/v1/quote"
JUP_SWAP_URL  = "https://lite-api.jup.ag/swap/v1/swap"
# Price API v3: on interroge par mint WSOL et on lit "usdPrice"
PRICE_API     = f"https://lite-api.jup.ag/price/v3?ids={WSOL}"

# DexScreener
DEX_SCREENER_SEARCH = "https://api.dexscreener.com/latest/dex/search"
DEX_TOKENS_BY_MINT  = "https://api.dexscreener.com/tokens/v1/solana"  # + /{mint}

# ==== Utilitaires HTTP (retries) ====
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

# ==== Telegram ====
def send(msg: str):
    if not TOKEN or not CHAT:
        print("[warn] Telegram non configuré"); return
    try:
        requests.get(
            f"https://api.telegram.org/bot{TOKEN}/sendMessage",
            params={"chat_id": CHAT, "text": msg},
            timeout=10
        )
    except Exception as e:
        print("[error] telegram:", e)

# ==== Clé / Client ====
def load_keypair() -> Keypair:
    pk_str = os.getenv("SOLANA_PRIVATE_KEY")
    if not pk_str:
        raise ValueError("Variable SOLANA_PRIVATE_KEY manquante")
    secret = base58.b58decode(pk_str.strip())
    if len(secret) != 64:
        raise ValueError(f"Clé invalide: {len(secret)} octets — attendu 64 (après décodage base58)")
    kp = Keypair.from_secret_key(secret)
    print(f"[boot] Public key: {kp.public_key}")
    return kp

kp = load_keypair()
client = Client(RPC_URL)
TZ = pytz.timezone(TZ_NAME)

# ==== Persistance positions ====
positions = {}  # mint -> dict

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
        print("[warn] save_positions:", e)

def load_positions():
    global positions
    try:
        if not os.path.exists(POSITIONS_PATH):
            positions = {}
            return
        with open(POSITIONS_PATH, "r") as f:
            data = json.load(f) or {}
            positions = data.get("positions") or {}
        print(f"[boot] positions restaurées: {len(positions)}")
    except Exception as e:
        print("[warn] load_positions:", e)
        positions = {}

# ==== Prix SOL (USD) via Jupiter v3 ====
def get_sol_usd() -> float:
    try:
        # V3: mapping { <mint>: { usdPrice, ... } }
        r = http_get(PRICE_API, timeout=10)
        data = r.json() or {}

        entry = None
        if isinstance(data, dict) and WSOL in data:
            entry = data.get(WSOL)
        # tolérance si un wrapper "data" est renvoyé par un proxy
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
        print("[warn] prix SOL indisponible, fallback 150 USD", e)
        return 150.0

# ==== DexScreener ====
def fetch_pairs() -> list:
    """Récupère ~30 paires via /search, puis filtre chainId='solana'."""
    try:
        r = http_get(DEX_SCREENER_SEARCH, params={"q": "solana"}, timeout=20)
        data = r.json() or {}
        pairs = data.get("pairs", []) or []
        return [p for p in pairs if (p.get("chainId") or "").lower() == "solana"]
    except Exception as e:
        print("[fetch_pairs error]", e)
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

def sign_and_send(serialized_b64: str):
    if DRY_RUN:
        return {"dry_run": True, "note": "swap non envoyé (DRY_RUN=1)"}
    tx_bytes = base64.b64decode(serialized_b64)
    tx = Transaction.deserialize(tx_bytes)
    tx.sign(kp)
    resp = client.send_raw_transaction(
        tx.serialize(),
        opts=TxOpts(skip_preflight=True, preflight_commitment="processed")
    )
    return resp.get("result", resp) if isinstance(resp, dict) else resp

# ==== Solde SOL ====
def get_balance_sol() -> float:
    resp = client.get_balance(kp.public_key)
    lamports = (resp.get("result") or {}).get("value", 0)
    return lamports / 1_000_000_000

# ==== Balance token SPL ====
def get_token_balance(mint: str) -> int:
    """Retourne la balance 'amount' (entiers) pour le mint donné."""
    try:
        if hasattr(client, "get_token_accounts_by_owner_json_parsed"):
            resp = client.get_token_accounts_by_owner_json_parsed(
                kp.public_key, {"mint": mint}, commitment="confirmed"
            )
        else:
            resp = client.get_token_accounts_by_owner(
                kp.public_key, {"mint": mint}, commitment="confirmed", encoding="jsonParsed"
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
        try:
            resp = client._provider.make_request(
                "getTokenAccountsByOwner",
                str(kp.public_key),
                {"mint": mint},
                {"encoding": "jsonParsed"}
            )
            vals = (resp.get("result") or {}).get("value") or []
            total = 0
            for v in vals:
                info = (((v or {}).get("account") or {}).get("data") or {}).get("parsed", {})
                amt = (((info.get("info") or {}).get("tokenAmount")) or {}).get("amount")
                if amt is not None:
                    total += int(amt)
            return total
        except Exception as e2:
            print("[warn] get_token_balance fallback:", e2)
            return 0

# ==== Helpers ====
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

    balance = get_balance_sol()
    size_sol = max(balance * POSITION_SIZE_PCT, MIN_TRADE_SOL)
    if size_sol > balance * 0.99:
        size_sol = balance * 0.99
    lamports = int(size_sol * 1_000_000_000)
    if lamports <= 0:
        send("❌ Achat annulé: solde SOL insuffisant"); return

    base_mint = (pair.get("baseToken") or {}).get("address")
    base_sym  = (pair.get("baseToken") or {}).get("symbol") or "TOKEN"
    pair_url  = pair.get("url") or "https://dexscreener.com/solana"

    if not base_mint or base_mint in positions:
        return  # anti-réachat

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

    price_sol = pair_price_in_sol(pair, sol_usd)
    positions[base_mint] = {
        "symbol": base_sym,
        "entry_price_sol": price_sol,
        "peak_price_sol": price_sol,
        "pair_url": pair_url,
        "opened_at": now_str(),
    }
    save_positions()

def close_position(mint: str, symbol: str, reason: str) -> bool:
    try:
        bal_amount = get_token_balance(mint)
        if bal_amount <= 0:
            send(f"{reason} {symbol}: aucun solde token détecté (déjà vendu ?)")
            return True

        q = jup_quote(mint, WSOL, int(bal_amount * 0.99), SLIPPAGE_BPS)
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
        entry  = pos["entry_price_sol"]
        peak   = pos["peak_price_sol"]

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
            print("[warn] check_positions fetch:", e)
            continue

        if price > peak:
            pos["peak_price_sol"] = price
            peak = price
            save_positions()

        draw_from_entry = (entry - price) / entry if entry else 0.0
        if draw_from_entry >= STOP_LOSS_PCT:
            if close_position(mint, symbol, "🛑 Stop-loss"):
                to_close.append(mint)
            continue

        drop_from_peak = (peak - price) / peak if peak else 0.0
        gain_from_entry = (price - entry) / entry if entry else 0.0

        if gain_from_entry >= TRAILING_TRIGGER_PCT and drop_from_peak >= TRAILING_THROWBACK_PCT:
            if close_position(mint, symbol, "✅ Trailing take-profit"):
                to_close.append(mint)
            continue

    for m in to_close:
        positions.pop(m, None)
    if to_close:
        save_positions()

# ==== Scan de marché ====
def scan_market():
    try:
        sol_usd = get_sol_usd()
        min_liq_usd = MIN_LIQ_SOL * sol_usd
        min_vol_usd = MIN_VOL_SOL * sol_usd

        pairs = fetch_pairs()
        if not pairs:
            return

        candidates = []
        for p in pairs:
            liq_usd = pair_liquidity_usd(p)
            vol_usd = pair_volume_h24_usd(p)
            if liq_usd < min_liq_usd or vol_usd < min_vol_usd:
                continue
            chg = get_price_change_pct(p, PRICE_WINDOW)
            if math.isnan(chg):
                continue
            if chg >= ENTRY_THRESHOLD * 100:
                candidates.append((chg, p))

        candidates.sort(key=lambda x: x[0], reverse=True)

        for chg, p in candidates:
            if not can_open_more():
                break
            base_mint = (p.get("baseToken") or {}).get("address")
            if not base_mint or base_mint in positions:
                continue
            enter_trade(p, sol_usd)

        check_positions(sol_usd)

    except Exception as e:
        err = f"[scan error] {type(e).__name__}: {e}"
        print(err)
        send(f"⚠️ {err}")

# ==== Boot self-check & monitoring ====
def ok(b: bool) -> str:
    return "✅" if b else "❌"

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
        test_amt = int(0.01 * 1_000_000_000)
        q = jup_quote(WSOL, WSOL, test_amt, SLIPPAGE_BPS)
        results["jup_quote"] = "outAmount" in json.dumps(q)
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
        f"Max {MAX_OPEN_TRADES} | Taille {int(POSITION_SIZE_PCT*100)}%\n"
        f"Filtres: Liqu≥{MIN_LIQ_SOL} SOL, Vol≥{MIN_VOL_SOL} SOL | Fenêtre: {PRICE_WINDOW}"
    )
    send(msg)

def heartbeat():
    send(f"⏱️ Heartbeat {now_str()} | positions ouvertes: {len(positions)}")

def daily_summary():
    if positions:
        lines = []
        for m, p in positions.items():
            ep = p.get('entry_price_sol') or 0.0
            pk = p.get('peak_price_sol') or 0.0
            lines.append(f"- {p['symbol']} | entry {ep:.6f} SOL | peak {pk:.6f} SOL")
        body = "\n".join(lines)
    else:
        body = "Aucune position ouverte."
    send(f"📰 Résumé quotidien {now_str()}\n{body}")

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

load_positions()
boot_message()
send_boot_diagnostics()

# ==== Scheduler ====
scheduler = BackgroundScheduler(timezone=TZ)
scheduler.add_job(scan_market, "interval", seconds=SCAN_INTERVAL_SEC, id="scan")
scheduler.add_job(heartbeat, "interval", minutes=HEARTBEAT_MINUTES, id="heartbeat")
scheduler.add_job(daily_summary, "cron", hour=21, minute=0, id="daily_summary")
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
