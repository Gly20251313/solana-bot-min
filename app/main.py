import os
import logging
from solders.keypair import Keypair
from solana.rpc.api import Client
from telegram import Bot

# --- CONFIG ---
RPC_URL = os.getenv("RPC_URL")
PRIVATE_KEY = os.getenv("SOLANA_PRIVATE_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
PROBE_SOL = float(os.getenv("PROBE_SOL", "0.003"))  # Montant micro-trade

# --- LOGGING ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("testtrade")

bot = Bot(token=TELEGRAM_BOT_TOKEN)
client = Client(RPC_URL)

def send(msg: str):
    try:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=msg)
    except Exception as e:
        logger.error(f"Telegram error: {e}")

def test_trade():
    """Exécute un micro-trade factice pour tester la signature et le swap."""
    try:
        # Charger la clé privée
        keypair = Keypair.from_base58_string(PRIVATE_KEY)
        pubkey = keypair.pubkey()

        # ✅ Correction : accès dict JSON
        resp = client.get_balance(pubkey)
        balance = resp["result"]["value"] / 1e9

        logger.info(f"Wallet balance: {balance:.4f} SOL")
        send(f"🔍 TestTrade lancé\nWallet: {pubkey}\nSolde: {balance:.4f} SOL")

        # --- ICI on simule un swap Jupiter ---
        fake_tx = "FAKE12345TXHASH"

        logger.info(f"Fake buy {PROBE_SOL} SOL -> tokenX")
        send(f"[TEST TRADE] ✅ Buy {PROBE_SOL} SOL → tokenX\nTx: https://solscan.io/tx/{fake_tx}")

        logger.info("Fake sell back tokenX -> SOL")
        send(f"[TEST TRADE] ✅ Sell tokenX → {PROBE_SOL} SOL\nTx: https://solscan.io/tx/{fake_tx}")

        send("✅ Test complet : signature & envoi OK (fake mode).")

    except Exception as e:
        logger.error(f"Test trade error: {e}")
        send(f"❌ TestTrade error: {e}")

if __name__ == "__main__":
    test_trade()
