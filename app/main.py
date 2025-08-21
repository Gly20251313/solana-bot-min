import os
import time
import logging
import random
import requests
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler

# ==================== CONFIGURATION ====================
MODE = os.getenv("MODE", "SIMU")  # "SIMU" ou "REAL"

ENTRY_THRESHOLD = float(os.getenv("ENTRY_THRESHOLD", 2.1))
MAX_TRADES = int(os.getenv("MAX_TRADES", 4))
TRADE_SIZE = float(os.getenv("TRADE_SIZE", 0.25))  # 25% du capital
STOP_LOSS = float(os.getenv("STOP_LOSS", -10))     # -10%
TRAILING_ACTIVATION = float(os.getenv("TRAILING_ACTIVATION", 30))
TRAILING_RETREAT = float(os.getenv("TRAILING_RETREAT", 20))

DAILY_SUMMARY_HOUR = int(os.getenv("DAILY_SUMMARY_HOUR", 21))

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

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

    def execute_trade(self, token: dict):
        if MODE == "SIMU":
            logging.info(f"[SIMU] Achat de {token['symbol']} avec {TRADE_SIZE*100}% du capital.")
        else:
            logging.info(f"[REAL] Envoi ordre blockchain pour {token['symbol']}...")
            # Ici tu intègres Solana/Web3 + wallet Phantom si besoin
        trade = {
            "symbol": token["symbol"],
            "entry_price": token.get("price", 1.0),
            "time": datetime.now()
        }
        self.trades.append(trade)

    def get_daily_summary(self) -> str:
        return f"Résumé quotidien : {len(self.trades)} trades exécutés."

# ==================== TELEGRAM ====================
class TelegramBot:
    def send_alert(self, msg: str):
        if TELEGRAM_TOKEN and TELEGRAM_CHAT_ID:
            try:
                url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
                data = {"chat_id": TELEGRAM_CHAT_ID, "text": msg}
                requests.post(url, data=data, timeout=10)
            except Exception as e:
                logging.error(f"Erreur envoi Telegram : {e}")
        else:
            logging.info(f"[TELEGRAM SIMU] {msg}")

# ==================== MARKET SCANNER ====================
class MarketScanner:
    def fetch_from_gecko(self):
        try:
            url = "https://api.coingecko.com/api/v3/coins/markets"
            params = {"vs_currency": "usd", "order": "volume_desc", "per_page": 5, "page": 1}
            r = requests.get(url, params=params, timeout=10)
            data = r.json()
            tokens = []
            for d in data:
                tokens.append({
                    "symbol": d["symbol"].upper(),
                    "score": random.uniform(0, 3),  # placeholder
                    "price": d["current_price"],
                    "lp_locked": True,
                    "tax": 5,
                    "supply": d.get("circulating_supply", 1_000_000)
                })
            return tokens
        except Exception as e:
            logging.error(f"Erreur Coingecko: {e}")
            return []

    def fetch_from_dexscreener(self):
        try:
            url = "https://api.dexscreener.com/latest/dex/tokens/solana"
            r = requests.get(url, timeout=10)
            data = r.json().get("pairs", [])
            tokens = []
            for d in data[:5]:
                tokens.append({
                    "symbol": d.get("baseToken", {}).get("symbol", "UNK"),
                    "score": random.uniform(0, 3),
                    "price": float(d.get("priceUsd", 1)),
                    "lp_locked": True,
                    "tax": 5,
                    "supply": 1_000_000
                })
            return tokens
        except Exception as e:
            logging.error(f"Erreur DexScreener: {e}")
            return []

    def fetch_from_birdeye(self):
        # Simulation simple (API payante sinon)
        return [
            {"symbol": "BIRD", "score": random.uniform(0, 3), "price": 0.1, "lp_locked": True, "tax": 3, "supply": 500_000}
        ]

    def fetch_from_jupiter(self):
        # Simulation simple
        return [
            {"symbol": "JUP", "score": random.uniform(0, 3), "price": 0.8, "lp_locked": True, "tax": 2, "supply": 2_000_000}
        ]

    def fetch_new_tokens(self):
        tokens = []
        tokens.extend(self.fetch_from_gecko())
        tokens.extend(self.fetch_from_dexscreener())
        tokens.extend(self.fetch_from_birdeye())
        tokens.extend(self.fetch_from_jupiter())
        return tokens

    def score_token(self, token: dict) -> float:
        return token.get("score", 0)

# ==================== BOT PRINCIPAL ====================
def main():
    logging.info("Démarrage du bot trading complet...")

    scanner = MarketScanner()
    risk = RiskManager()
    executor = TradeExecutor()
    telegram = TelegramBot()
    tokenomics = TokenomicsChecker()

    scheduler = BackgroundScheduler()

    def scan_market():
        logging.info("Scanning market...")
        tokens = scanner.fetch_new_tokens()
        for token in tokens:
            score = scanner.score_token(token)
            if score >= ENTRY_THRESHOLD:
                if not tokenomics.is_safe(token):
                    continue
                if risk.can_enter_trade(token):
                    executor.execute_trade(token)
                    risk.register_trade(token)
                    telegram.send_alert(f"Trade exécuté sur {token['symbol']} (score {score:.2f})")

    def heartbeat():
        logging.info("Bot is alive.")

    def daily_summary():
        summary = executor.get_daily_summary()
        telegram.send_alert(summary)

    scheduler.add_job(scan_market, "interval", seconds=30)
    scheduler.add_job(heartbeat, "interval", minutes=5)
    scheduler.add_job(daily_summary, "cron", hour=DAILY_SUMMARY_HOUR)

    scheduler.start()

    logging.info("Scheduler démarré.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logging.info("Arrêt du bot...")
        scheduler.shutdown()

if __name__ == "__main__":
    main()
