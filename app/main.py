"""
Bot de trading automatique sur Solana (Railway-ready, sandbox-safe)
- Modes: SIMU ou REAL (via var d'environnement MODE)
- Scanner concurrentiel multi-sources: DexScreener (principal), Birdeye (optionnel), GeckoTerminal (fallback)
- Exécution: SIMU (mock) ou REAL via Jupiter v6 + signature Phantom (PRIVATE_KEY base58)
- Gestion du risque: sizing, max trades, stop-loss, trailing stop (activation/retreat)
- Alerte/commandes Telegram: /start /summary /stop (facultatif si lib non installée)
- Sans multiprocessing ni APScheduler: boucles asyncio pures
- ✅ Import Solana/Jupiter **à la demande** (évite l'erreur `ModuleNotFoundError: solana` en sandbox)
- ✅ Tests unitaires intégrés (RUN_TESTS=1) pour la logique trailing & stop-loss

Dépendances (pour le mode REAL en production/Railway):
    aiohttp
    python-telegram-bot>=20
    solana>=0.30
    solders>=0.18
    base58
"""

import os
import asyncio
import aiohttp
import logging
import base64
import base58
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from datetime import datetime

# ==================== CONFIG ====================
MODE = os.getenv("MODE", "SIMU").upper()              # SIMU | REAL
# Scanner
SCAN_INTERVAL_SEC = int(os.getenv("SCAN_INTERVAL_SEC", 30))
SOURCES = [s.strip() for s in os.getenv("SOURCES", "dexscreener,gecko,birdeye").split(",") if s.strip()]
BIRDEYE_API_KEY = os.getenv("BIRDEYE_API_KEY", "")
# Risk & Strategy
ENTRY_THRESHOLD = float(os.getenv("ENTRY_THRESHOLD", 2.1))       # % m5 min
MAX_TRADES = int(os.getenv("MAX_TRADES", 4))
TRADE_SIZE = float(os.getenv("TRADE_SIZE", 0.25))                 # fraction du SOL dispo
STOP_LOSS = float(os.getenv("STOP_LOSS", -10))                    # % vs entrée
TRAILING_ACTIVATION = float(os.getenv("TRAILING_ACTIVATION", 30)) # % gain pour armer trailing
TRAILING_RETREAT = float(os.getenv("TRAILING_RETREAT", 20))       # % repli depuis le pic
SELL_PERCENT = float(os.getenv("SELL_PERCENT", 1.0))              # 1.0 = 100% du token détenu
SLIPPAGE_BPS = int(os.getenv("SLIPPAGE_BPS", 300))                # 3%
# Wallet / Network
PRIVATE_KEY = os.getenv("PRIVATE_KEY", "")                          # base58 (Phantom)
RPC_ENDPOINT = os.getenv("RPC_ENDPOINT", "https://api.mainnet-beta.solana.com")
# Telegram
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
DAILY_SUMMARY_HOUR = int(os.getenv("DAILY_SUMMARY_HOUR", 21))     # heure locale

# Jupiter endpoints
WSOL_MINT = "So11111111111111111111111111111111111111112"
TOKEN_PROGRAM_ID = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
JUP_QUOTE = "https://quote-api.jup.ag/v6/quote"
JUP_SWAP = "https://quote-api.jup.ag/v6/swap"

# ==================== LOGGING ====================
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
log = logging.getLogger("bot")

# ==================== TELEGRAM (facultatif) ====================
try:
    from telegram import Update  # type: ignore
    from telegram.ext import Application, CommandHandler, ContextTypes  # type: ignore
    _TELEGRAM_OK = True
except Exception:
    Update = object  # type: ignore
    Application = None  # type: ignore
    CommandHandler = object  # type: ignore
    ContextTypes = object  # type: ignore
    _TELEGRAM_OK = False

class TelegramBot:
    def __init__(self):
        self.enabled = _TELEGRAM_OK and bool(TELEGRAM_TOKEN)
        if self.enabled:
            self.application = Application.builder().token(TELEGRAM_TOKEN).build()
            self.application.add_handler(CommandHandler("start", self.cmd_start))
            self.application.add_handler(CommandHandler("summary", self.cmd_summary))
            self.application.add_handler(CommandHandler("stop", self.cmd_stop))
        else:
            self.application = None

    async def send_alert(self, msg: str):
        if not (self.enabled and TELEGRAM_CHAT_ID):
            log.info(f"[ALERT] {msg}")
            return
        try:
            await self.application.bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=msg)  # type: ignore
        except Exception as e:
            log.warning(f"Telegram send fail: {e}")

    async def cmd_start(self, update: Update, context: 'ContextTypes.DEFAULT_TYPE'):  # type: ignore
        await update.message.reply_text(f"Bot actif. Mode: {MODE}")  # type: ignore

    async def cmd_summary(self, update: Update, context: 'ContextTypes.DEFAULT_TYPE'):  # type: ignore
        await update.message.reply_text(get_daily_summary())  # type: ignore

    async def cmd_stop(self, update: Update, context: 'ContextTypes.DEFAULT_TYPE'):  # type: ignore
        await update.message.reply_text("Arrêt demandé.")  # type: ignore
        os._exit(0)

# ==================== DOMAIN MODELS ====================
@dataclass
class Token:
    address: str
    name: str
    price_usd: Optional[float] = None
    liquidity_usd: Optional[float] = None
    change_m5: Optional[float] = None
    source: str = ""

@dataclass
class Position:
    token: Token
    entry_price: float
    entry_change_m5: float
    entry_time: datetime = field(default_factory=datetime.now)
    peak_change_m5: float = field(default=0.0)
    trailing_active: bool = field(default=False)

# ==================== ANTI-SCAM CHECKER ====================
class TokenomicsChecker:
    def is_safe(self, t: Token) -> bool:
        return (t.liquidity_usd or 0) >= 5_000 and t.change_m5 is not None

# ==================== SCANNER MULTI-SOURCES ====================
class MarketScanner:
    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None

    async def _ensure_session(self):
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10))

    async def fetch_from_dexscreener(self) -> List[Token]:
        await self._ensure_session()
        url = "https://api.dexscreener.com/latest/dex/pairs/solana"
        try:
            async with self.session.get(url) as r:
                data = await r.json()
                out: List[Token] = []
                for p in data.get("pairs", [])[:100]:
                    base = p.get("baseToken", {})
                    change = (p.get("priceChange") or {}).get("m5")
                    t = Token(
                        address=base.get("address") or p.get("pairAddress", ""),
                        name=base.get("symbol", "UNK"),
                        price_usd=float(p.get("priceUsd") or 0) if p.get("priceUsd") else None,
                        liquidity_usd=float((p.get("liquidity") or {}).get("usd", 0)),
                        change_m5=float(change) if change is not None else None,
                        source="dexscreener",
                    )
                    out.append(t)
                return out
        except Exception as e:
            log.warning(f"DexScreener fail: {e}")
            return []

    async def fetch_from_birdeye(self) -> List[Token]:
        if not BIRDEYE_API_KEY:
            return []
        await self._ensure_session()
        url = "https://public-api.birdeye.so/public/market/top_gainers?chain=solana&interval=5m&offset=0&limit=50"
        headers = {"x-api-key": BIRDEYE_API_KEY}
        try:
            async with self.session.get(url, headers=headers) as r:
                data = await r.json()
                items = (data.get("data") or {}).get("items", [])
                out: List[Token] = []
                for it in items:
                    ch = None
                    if isinstance(it.get("priceChange"), dict):
                        ch = it.get("priceChange", {}).get("m5")
                    t = Token(
                        address=it.get("address", ""),
                        name=it.get("symbol") or "UNK",
                        price_usd=it.get("price"),
                        liquidity_usd=it.get("liquidity", 0),
                        change_m5=float(ch) if ch is not None else None,
                        source="birdeye",
                    )
                    out.append(t)
                return out
        except Exception as e:
            log.warning(f"Birdeye fail: {e}")
            return []

    async def fetch_from_gecko(self) -> List[Token]:
        await self._ensure_session()
        url = "https://api.geckoterminal.com/api/v2/networks/solana/trending_pools"
        try:
            async with self.session.get(url) as r:
                data = await r.json()
                pools = data.get("data", [])
                out: List[Token] = []
                for p in pools[:50]:
                    attr = p.get("attributes", {})
                    base_token = (attr.get("base_token")) or {}
                    t = Token(
                        address=base_token.get("address", ""),
                        name=base_token.get("symbol", "UNK"),
                        source="gecko",
                    )
                    out.append(t)
                return out
        except Exception as e:
            log.warning(f"Gecko fail: {e}")
            return []

    async def fetch_all(self) -> List[Token]:
        calls = []
        if "dexscreener" in SOURCES:
            calls.append(self.fetch_from_dexscreener())
        if "birdeye" in SOURCES:
            calls.append(self.fetch_from_birdeye())
        if "gecko" in SOURCES:
            calls.append(self.fetch_from_gecko())
        if not calls:
            return []
        results = await asyncio.gather(*calls, return_exceptions=True)
        tokens: List[Token] = []
        for res in results:
            if isinstance(res, Exception):
                log.warning(f"Source error: {res}")
                continue
            tokens.extend(res)
        # Dédupliquer & fusionner
        merged: Dict[str, Token] = {}
        for t in tokens:
            if not t.address:
                continue
            if t.address not in merged:
                merged[t.address] = t
            else:
                m = merged[t.address]
                m.price_usd = m.price_usd or t.price_usd
                m.liquidity_usd = m.liquidity_usd or t.liquidity_usd
                m.change_m5 = m.change_m5 if m.change_m5 is not None else t.change_m5
        return list(merged.values())

# ==================== RISK & TRAILING ====================
class RiskManager:
    def __init__(self):
        self.positions: Dict[str, Position] = {}

    def can_enter(self, t: Token) -> bool:
        if t.change_m5 is None:
            return False
        return len(self.positions) < MAX_TRADES and t.change_m5 >= ENTRY_THRESHOLD

    def on_buy(self, t: Token) -> Position:
        pos = Position(
            token=t,
            entry_price=t.price_usd or 0,
            entry_change_m5=t.change_m5 or 0,
            peak_change_m5=t.change_m5 or 0,
        )
        self.positions[t.address] = pos
        return pos

    def should_sell(self, t: Token) -> Tuple[bool, str]:
        pos = self.positions.get(t.address)
        if not pos or t.change_m5 is None:
            return False, "no-pos-or-metric"
        pnl = (t.change_m5 - pos.entry_change_m5)
        if pnl <= STOP_LOSS:
            return True, "stop-loss"
        if not pos.trailing_active and pnl >= TRAILING_ACTIVATION:
            pos.trailing_active = True
            pos.peak_change_m5 = t.change_m5
            return False, "trailing-armed"
        if pos.trailing_active:
            if t.change_m5 > pos.peak_change_m5:
                pos.peak_change_m5 = t.change_m5
            retreat = pos.peak_change_m5 - t.change_m5
            if retreat >= TRAILING_RETREAT:
                return True, "trailing-retreat"
        return False, "hold"

    def on_sell(self, t: Token):
        if t.address in self.positions:
            del self.positions[t.address]

# ==================== EXECUTION (SIMU / REAL avec imports différés) ====================
class TradeExecutor:
    def __init__(self):
        self.mode = MODE
        self.client = None  # AsyncClient
        self.wallet = None  # Keypair
        self._solana_mods_loaded = False
        self._PublicKey = None
        self._AsyncClient = None
        self._Keypair = None
        self._TxOpts = None
        self._VersionedTransaction = None

    async def init(self):
        if self.mode != "REAL":
            return
        # Imports différés pour éviter l'erreur en sandbox
        try:
            from solana.publickey import PublicKey as _PublicKey
            from solana.rpc.async_api import AsyncClient as _AsyncClient
            from solana.keypair import Keypair as _Keypair
            from solana.rpc.types import TxOpts as _TxOpts
            from solders.transaction import VersionedTransaction as _VersionedTransaction
        except Exception as e:
            raise RuntimeError("Modules Solana manquants. Installe: solana, solders.\n" \
                               "Sur Railway, ajoute-les dans requirements.txt.") from e
        self._PublicKey = _PublicKey
        self._AsyncClient = _AsyncClient
        self._Keypair = _Keypair
        self._TxOpts = _TxOpts
        self._VersionedTransaction = _VersionedTransaction

        if not PRIVATE_KEY:
            raise RuntimeError("PRIVATE_KEY manquant pour le mode REAL")
        secret = base58.b58decode(PRIVATE_KEY)
        self.wallet = self._Keypair.from_secret_key(secret)
        self.client = self._AsyncClient(RPC_ENDPOINT)
        self._solana_mods_loaded = True
        log.info(f"Wallet: {self.wallet.public_key}")

    async def _get_sol_balance_lamports(self) -> int:
        if self.mode != "REAL":
            return int(10 * 1e9)
        assert self.client and self.wallet
        resp = await self.client.get_balance(self.wallet.public_key)
        try:
            return int(resp.value)
        except Exception:
            return int(resp["result"]["value"])  # fallback dict

    async def _get_spl_ui_amount_and_decimals(self, mint: str) -> Tuple[float, int]:
        """Retourne (uiAmount, decimals) pour le token mint détenu par le wallet."""
        assert self.client and self.wallet and self._PublicKey
        owner = self.wallet.public_key
        resp = await self.client.get_token_accounts_by_owner(owner, mint=self._PublicKey(mint))
        ui_amount = 0.0
        decimals = 9
        try:
            for acc in resp.value:
                parsed = acc.account.data.parsed  # type: ignore
                amt = parsed["info"]["tokenAmount"]
                ui_amount += float(amt.get("uiAmount", 0))
                decimals = int(amt.get("decimals", 9))
        except Exception:
            # fallback format
            for acc in resp["result"]["value"]:
                amt = acc["account"]["data"]["parsed"]["info"]["tokenAmount"]
                ui_amount += float(amt.get("uiAmount", 0))
                decimals = int(amt.get("decimals", 9))
        return ui_amount, decimals

    async def _jup_quote(self, input_mint: str, output_mint: str, amount: int) -> Optional[dict]:
        params = {
            "inputMint": input_mint,
            "outputMint": output_mint,
            "amount": str(amount),
            "slippageBps": str(SLIPPAGE_BPS),
            "onlyDirectRoutes": "false",
        }
        async with aiohttp.ClientSession() as s:
            async with s.get(JUP_QUOTE, params=params) as r:
                if r.status != 200:
                    txt = await r.text()
                    log.warning(f"quote fail {r.status}: {txt}")
                    return None
                return await r.json()

    async def _jup_swap_tx(self, quote: dict) -> Optional[str]:
        assert self.wallet is not None
        body = {
            "quoteResponse": quote,
            "userPublicKey": str(self.wallet.public_key),
            "wrapAndUnwrapSol": True,
            "dynamicComputeUnitLimit": True,
            "useSharedAccounts": True,
        }
        async with aiohttp.ClientSession() as s:
            async with s.post(JUP_SWAP, json=body) as r:
                if r.status != 200:
                    txt = await r.text()
                    log.warning(f"swap fail {r.status}: {txt}")
                    return None
                data = await r.json()
                return data.get("swapTransaction")

    async def _sign_and_send(self, swap_tx_b64: str) -> str:
        assert self.client and self.wallet and self._VersionedTransaction and self._TxOpts
        raw = base64.b64decode(swap_tx_b64)
        tx = self._VersionedTransaction.from_bytes(raw)
        tx.sign([self.wallet])
        sig = await self.client.send_raw_transaction(bytes(tx), opts=self._TxOpts(skip_preflight=True, preflight_commitment="confirmed"))
        try:
            return str(sig.value)
        except Exception:
            return str(sig["result"])  # fallback dict

    async def buy(self, t: Token) -> Tuple[bool, str]:
        if self.mode != "REAL":
            log.info(f"[SIMU] BUY {t.name} {t.address}")
            return True, "simu"
        lamports = await self._get_sol_balance_lamports()
        to_spend = int(lamports * TRADE_SIZE)
        if to_spend <= 0:
            return False, "no-balance"
        quote = await self._jup_quote(WSOL_MINT, t.address, to_spend)
        if not quote:
            return False, "no-quote"
        swap_b64 = await self._jup_swap_tx(quote)
        if not swap_b64:
            return False, "no-swap"
        sig = await self._sign_and_send(swap_b64)
        log.info(f"BUY SIG: {sig}")
        return True, sig

    async def sell(self, t: Token) -> Tuple[bool, str]:
        if self.mode != "REAL":
            log.info(f"[SIMU] SELL {t.name} {t.address}")
            return True, "simu"
        ui_amount, decimals = await self._get_spl_ui_amount_and_decimals(t.address)
        sell_ui = ui_amount * max(0.0, min(1.0, SELL_PERCENT))
        if sell_ui <= 0:
            return False, "no-balance"
        amount_atoms = int(sell_ui * (10 ** decimals))
        quote = await self._jup_quote(t.address, WSOL_MINT, amount_atoms)
        if not quote:
            return False, "no-quote"
        swap_b64 = await self._jup_swap_tx(quote)
        if not swap_b64:
            return False, "no-swap"
        sig = await self._sign_and_send(swap_b64)
        log.info(f"SELL SIG: {sig}")
        return True, sig

# ==================== APP STATE ====================
checker = TokenomicsChecker()
scanner = MarketScanner()
risk = RiskManager()
executor = TradeExecutor()
telegram = TelegramBot()

# ==================== LOGIC ====================
async def scan_once():
    tokens = await scanner.fetch_all()
    if not tokens:
        return
    by_addr: Dict[str, Token] = {t.address: t for t in tokens if t.address}

    # sorties (stop-loss / trailing)
    to_close: List[Tuple[Token, str]] = []
    for addr, pos in list(risk.positions.items()):
        t = by_addr.get(addr)
        if not t or t.change_m5 is None:
            continue
        sell, reason = risk.should_sell(t)
        if sell:
            to_close.append((t, reason))
    for t, reason in to_close:
        ok, sig = await executor.sell(t)
        if ok:
            risk.on_sell(t)
            await telegram.send_alert(f"❗ SELL {t.name} ({reason})")
        else:
            await telegram.send_alert(f"⛔ SELL FAIL {t.name}: {sig}")

    # entrées
    for t in tokens:
        if not checker.is_safe(t):
            continue
        if not risk.can_enter(t):
            continue
        ok, sig = await executor.buy(t)
        if ok:
            risk.on_buy(t)
            await telegram.send_alert(f"✅ BUY {t.name} +{t.change_m5}% (sig: {sig})")
        await asyncio.sleep(0)

async def heartbeat_loop():
    while True:
        log.info("heartbeat alive")
        await asyncio.sleep(300)

async def daily_summary_loop():
    last_sent: Optional[datetime] = None
    while True:
        now = datetime.now()
        if now.hour == DAILY_SUMMARY_HOUR and (not last_sent or last_sent.date() < now.date()):
            await telegram.send_alert(get_daily_summary())
            last_sent = now
        await asyncio.sleep(60)

def get_daily_summary() -> str:
    n = len(risk.positions)
    names = ", ".join([p.token.name for p in risk.positions.values()][:10])
    return f"Positions ouvertes: {n} | {names}"

async def scan_loop():
    while True:
        try:
            await scan_once()
        except Exception as e:
            log.exception(f"scan_once error: {e}")
        await asyncio.sleep(SCAN_INTERVAL_SEC)

# ==================== TESTS ====================
def _test_trailing_and_stop():
    rm = RiskManager()
    t = Token(address="X", name="TEST", price_usd=1.0, liquidity_usd=10_000, change_m5=5)
    assert rm.can_enter(t)
    rm.on_buy(t)
    # activate trailing
    t.change_m5 = TRAILING_ACTIVATION + 5
    sell, reason = rm.should_sell(t)
    assert not sell and reason == "trailing-armed"
    # new peak then retreat
    t.change_m5 = t.change_m5 + 10
    sell, reason = rm.should_sell(t)
    assert not sell
    t.change_m5 = t.change_m5 - (TRAILING_RETREAT + 1)
    sell, reason = rm.should_sell(t)
    assert sell and reason == "trailing-retreat"
    # stop-loss
    rm = RiskManager()
    t = Token(address="Y", name="TEST2", price_usd=1.0, liquidity_usd=10_000, change_m5=ENTRY_THRESHOLD+0.1)
    rm.on_buy(t)
    t.change_m5 = (rm.positions[t.address].entry_change_m5 + STOP_LOSS - 1)
    sell, reason = rm.should_sell(t)
    assert sell and reason == "stop-loss"

def _test_checker_and_enter():
    chk = TokenomicsChecker()
    safe = Token(address="A", name="OK", price_usd=1.0, liquidity_usd=6000, change_m5=ENTRY_THRESHOLD)
    unsafe = Token(address="B", name="NO", price_usd=1.0, liquidity_usd=100, change_m5=ENTRY_THRESHOLD)
    assert chk.is_safe(safe) and not chk.is_safe(unsafe)
    rm = RiskManager()
    assert rm.can_enter(safe) and not rm.can_enter(Token(address="C", name="X", liquidity_usd=6000, change_m5=None))

# ==================== MAIN ====================
async def main():
    if os.getenv("RUN_TESTS") == "1":
        _test_trailing_and_stop()
        _test_checker_and_enter()
        print("TESTS OK")
        return

    await executor.init()

    tg_task = None
    if telegram.application:
        tg_task = asyncio.create_task(telegram.application.run_polling())

    loops = [
        asyncio.create_task(scan_loop()),
        asyncio.create_task(heartbeat_loop()),
        asyncio.create_task(daily_summary_loop()),
    ]

    if tg_task:
        await asyncio.gather(tg_task, *loops)
    else:
        await asyncio.gather(*loops)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
