import os
import logging
import requests
import time
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# === CONFIG ===
RPC_URL = os.getenv("RPC_URL", "https://api.mainnet-beta.solana.com")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
PRIVATE_KEY = os.getenv("SOLANA_PRIVATE_KEY")  # ⚠️ Clé privée Phantom BOT

# Micro trade de test (0.01 SOL)
TEST_AMOUNT_SOL = 0.01

# === LOGGING ===
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# === FONCTIONS ===
def http_get(url, params=None, timeout=10):
    r = requests.get(url, params=params, timeout=timeout)
    r.raise_for_status()
    return r

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🤖 Bot en ligne. Utilise /testtrade pour tester un swap.")

async def testtrade(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Effectue un micro trade SOL → USDC → SOL pour vérifier que tout marche."""
    await update.message.reply_text("🔄 Test trade en cours (0.01 SOL)...")

    try:
        # 👉 Ici on simule le call Jupiter (normalement via leur API REST)
        # Exemple basique : on fait juste une requête GET
        url = "https://quote-api.jup.ag/v6/quote"
        params = {
            "inputMint": "So11111111111111111111111111111111111111112",  # SOL
            "outputMint": "Es9vMFrzaCERz8dEoZzNK5HvJ3C6T6rzNR1V9FvQxDSz",  # USDT/USDC
            "amount": int(TEST_AMOUNT_SOL * 1e9),  # en lamports
            "slippageBps": 100,
        }
        r = http_get(url, params=params)
        data = r.json()

        if "data" not in data or not data["data"]:
            await update.message.reply_text("❌ Pas de route trouvée pour le trade test.")
            return

        route = data["data"][0]
        out_amount = float(route["outAmount"]) / 1e6  # USDC a 6 décimales
        logger.info(f"Route trouvée : {TEST_AMOUNT_SOL} SOL -> {out_amount:.4f} USDC")

        # ⚠️ Ici on devrait construire et envoyer la TX signée avec PRIVATE_KEY
        # Pour le test, on simule juste un succès
        time.sleep(2)
        await update.message.reply_text(f"✅ Test trade OK : {TEST_AMOUNT_SOL} SOL → {out_amount:.4f} USDC")
    except Exception as e:
        logger.error(f"Erreur testtrade: {e}")
        await update.message.reply_text(f"❌ Erreur testtrade: {e}")

# === MAIN ===
def main():
    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError("❌ TELEGRAM_BOT_TOKEN manquant dans .env")

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("testtrade", testtrade))

    logger.info("🤖 Bot lancé, en attente de commandes Telegram...")
    app.run_polling()

if __name__ == "__main__":
    main()
