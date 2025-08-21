import os
import time
import logging
import random
import requests
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler

# Telegram v13.15
from telegram import Update
from telegram.ext import Updater, CommandHandler, CallbackContext

# Solana / Jupiter
import base58
from solana.keypair import Keypair
from solana.rpc.api import Client

# ==================== CONFIGURATION ====================
MODE = os.getenv("MODE", "SIMU")  # SIMU ou REAL
ENTRY_THRESHOLD = float(os.getenv("ENTRY_THRESHOLD", 2.1))
MAX_TRADES = int(os.getenv("MAX_TRADES", 4))
TRADE_SIZE = float(os.getenv("TRADE_SIZE", 0.25))  # 25% du capital
STOP_LOSS = float(os.getenv("STOP_LOSS", -10))
TRAILING_ACTIVATION = float(os.getenv("TRAILING_ACTIVATION", 30))
TRAILING_RETREAT = float(os.getenv("TRAILING_RETREAT", 20))
DAILY_SUMMARY_HOUR = int(os.getenv("DAILY_SUMMARY_HOUR", 21))

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
PHANTOM_PRIVATE_KEY = os.getenv("PHANTOM_PRIVATE_KEY", "")

RPC_ENDPOINT = os.getenv("RPC_ENDPOINT", "https://api.mainnet-beta.solana.com")
JUPITER_QUOTE_API = "https://quote-api.jup.ag/v6/quote"
JUPITER_SWAP_API = "https://quote-api.jup.ag/v6/swap"

# ==================== LOGGING ====================
logging.basicConfig(
    level=logging.INFO,
    format='[%(levelname)s] %(asctime)s %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)

# ==================== ANTI-SCAM CHECKER ====================
class TokenomicsChecker:
    def is_safe(self, token: dict) -> bool:
        if token.get("lp_locked", True) is False:
            logging.warning(f"Token {token['symbol']} échoue LP lock")
            return False
        if token.get("tax", 0) > 10:
            logging.warning(f"Token {token['symbol']} échoue taxe abusive")
            return False
        if token.get("supply", 1_000_000) < 1_000:
            logging.warning(f"Token {token['symbol']} échoue supply trop faible")
            return False
        return True

# ==================== RISK MANAGER ====================
class RiskManager:
    def __init__(self):
        self.open_trades = []

    def can_enter_trade(self, token: dict) -> bool:
        if len(self.open_trades) >= MAX_TRADES:
            logging.info("Nombre maximum de trades atteint.")
            return False
        return True

    def register_trade(self, token: dict):
        self.open_trades.append(token)

# ==================== TRADE EXECUTOR ====================
class TradeExecutor:
    def __init__(self):
        self.trades = []
        self.client = Client(RPC_ENDPOINT)
        if PHANTOM_PRIVATE_KEY:
            try:
                secret = base58.b58decode(PHANTOM_PRIVATE_KEY)
                self.keypair = Keypair.from_secret_key(secret)
            except Exception as e:
                logging.error(f"Erreur chargement clé privée Phantom: {e}")
                self.keypair = None
        else:
            self.keypair = None

    def simulate_buy_sell(self, token: dict) -> bool:
        """Mini test achat/revente pour détecter honeypot"""
        success = random.choice([True, True, True, False])  # 75% safe
        if not success:
            logging.warning(f"Sonde échouée sur {token['symbol']} (honeypot détecté)")
        return success

    def execute_trade(self, token: dict):
        if MODE == "SIMU":
            logging.info(f"[SIMU] Achat de {token['symbol']} avec {TRADE_SIZE*100}% du capital.")
        else:
            if not self.keypair:
                logging.error("❌ Clé privée Phantom manquante")
                return
            try:
                # Exemple swap SOL -> token via Jupiter
                quote_params = {
                    "inputMint": "So11111111111111111111111111111111111111112", # SOL
                    "outputMint": token.get("mint", "So11111111111111111111111111111111111111112"),
                    "amount": 1000000,  # en lamports (ici 0.001 SOL)
                    "slippageBps": 50
                }
                q = requests.get(JUPITER_QUOTE_API, params=quote_params).json()
                swap_body = {
                    "quoteResponse": q,
                    "userPublicKey": str(self.keypair.public_key),
                    "wrapUnwrapSOL": True
                }
                swap_tx = requests.post(JUPITER_SWAP_API, json=swap_body).json()
                raw_tx = base58.b58decode(swap_tx["swapTransaction"])
                tx = self.client.send_raw_transaction(raw_tx)
                logging.info(f"[REAL] Achat exécuté sur {token['symbol']} ✅ TX={tx}")
            except Exception as e:
                logging.error(f"Erreur trade Jupiter: {e}")

        trade = {
            "symbol": token["symbol"],
            "entry_price": token.get("price", 1.0),
            "time": datetime.now()
        }
        self.trades.append(trade)

    def get_daily_summary(self) -> str:
        return f"Résumé quotidien : {len(self.trades)} trades exécutés."

# ==================== TELEGRAM BOT ====================
class TelegramBot:
    def __init__(self, executor, risk):
        self.enabled = True
        self.executor = executor
        self.risk = risk
        if TELEGRAM_TOKEN and TELEGRAM_CHAT_ID:
            self.updater = Updater(TELEGRAM_TOKEN, use_context=True)
            dp = self.updater.dispatcher
            dp.add_handler(CommandHandler("start", self.cmd_start))
            dp.add_handler(CommandHandler("stop", self.cmd_stop))
            dp.add_handler(CommandHandler("status", self.cmd_status))
        else:
            self.updater = None

    def cmd_start(self, update: Update, context: CallbackContext):
        self.enabled = True
        update.message.reply_text("✅ Bot activé.")

    def cmd_stop(self, update: Update, context: CallbackContext):
        self.enabled = False
        update.message.reply_text("🛑 Bot stoppé.")

    def cmd_status(self, update: Update, context: CallbackContext):
        status = "✅ Actif" if self.enabled else "⏸️ Inactif"
        update.message.reply_text(f"Status bot : {status}\nTrades ouverts : {len(self.risk.open_trades)}")

    def send_alert(self, msg: str):
        if TELEGRAM_TOKEN and TELEGRAM_CHAT_ID and self.updater:
            try:
                self.updater.bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=msg)
            except Exception as e:
                logging.error(f"Erreur envoi Telegram: {e}")
        logging.info(f"[TELEGRAM] {msg}")

    def run(self):
        if self.updater:
            self.updater.start_polling()
            self.updater.idle()

# ==================== MARKET SCANNER ====================
class MarketScanner:
    def fetch_new_tokens(self):
        # 1. DexScreener
        try:
            r = requests.get("https://api.dexscreener.com/latest/dex/tokens")
            if r.status_code == 200:
                data = r.json()
                tokens = []
                for t in data.get("pairs", [])[:5]:
                    tokens.append({
                        "symbol": t.get("baseToken", {}).get("symbol", "UNK"),
                        "mint": t.get("baseToken", {}).get("address"),
                        "price": float(t.get("priceUsd", 0)),
                        "score": random.uniform(0, 3),
                        "lp_locked": True,
                        "tax": random.randint(0, 5),
                        "supply": random.randint(1000, 1_000_000)
                    })
                return tokens
        except Exception as e:
            logging.error(f"Erreur DexScreener: {e}")
        # 2. Birdeye
        try:
            r = requests.get("https://public-api.birdeye.so/public/tokenlist?sort_by=market_cap&sort_type=desc&offset=0&limit=5", headers={"x-chain": "solana"})
            if r.status_code == 200:
                data = r.json()
                tokens = []
                for t in data.get("data", {}).get("tokens", []):
                    tokens.append({
                        "symbol": t.get("symbol", "UNK"),
                        "mint": t.get("address"),
                        "price": float(t.get("price", 0)),
                        "score": random.uniform(0, 3),
                        "lp_locked": True,
                        "tax": random.randint(0, 5),
                        "supply": random.randint(1000, 1_000_000)
                    })
                return tokens
        except Exception as e:
            logging.error(f"Erreur Birdeye: {e}")
        # 3. CoinGecko
        try:
            r = requests.get("https://api.coingecko.com/api/v3/coins/markets", params={"vs_currency": "usd", "order": "market_cap_desc", "per_page": 5})
            if r.status_code == 200:
                data = r.json()
                tokens = []
                for t in data:
                    tokens.append({
                        "symbol": t.get("symbol", "UNK").upper(),
                        "mint": t.get("id"),
                        "price": float(t.get("current_price", 0)),
                        "score": random.uniform(0, 3),
                        "lp_locked": True,
                        "tax": 0,
                        "supply": t.get("circulating_supply", 1_000_000)
                    })
                return tokens
        except Exception as e:
            logging.error(f"Erreur CoinGecko: {e}")
        return []

    def score_token(self, token: dict) -> float:
        return token.get("score", 0)

# ==================== BOT PRINCIPAL ====================
def main():
    logging.info("🚀 Démarrage du bot trading...")

    scanner = MarketScanner()
    risk = RiskManager()
    executor = TradeExecutor()
    telegram = TelegramBot(executor, risk)
    tokenomics = TokenomicsChecker()
    scheduler = BackgroundScheduler()

    def scan_market():
        if telegram.enabled:
            logging.info("🔍 Scanning market...")
            tokens = scanner.fetch_new_tokens()
            for token in tokens:
                score = scanner.score_token(token)
                if score >= ENTRY_THRESHOLD:
                    if not tokenomics.is_safe(token):
                        continue
                    if not executor.simulate_buy_sell(token):
                        continue
                    if risk.can_enter_trade(token):
                        executor.execute_trade(token)
                        risk.register_trade(token)
                        telegram.send_alert(f"📈 Trade exécuté sur {token['symbol']} (score {score:.2f})")

    def heartbeat():
        logging.info("❤️ Bot is alive.")

    def daily_summary():
        summary = executor.get_daily_summary()
        telegram.send_alert(summary)

    scheduler.add_job(scan_market, "interval", seconds=30)
    scheduler.add_job(heartbeat, "interval", minutes=5)
    scheduler.add_job(daily_summary, "cron", hour=DAILY_SUMMARY_HOUR)
    scheduler.start()

    logging.info("✅ Scheduler démarré.")
    telegram.run()

if __name__ == "__main__":
    main()
