import os, time, requests, signal
from datetime import datetime
import pytz
from apscheduler.schedulers.background import BackgroundScheduler

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT  = os.getenv("TELEGRAM_CHAT_ID")
TZ    = os.getenv("TZ", "Europe/Paris")

def send(msg: str):
    if not TOKEN or not CHAT:
        print("[warn] Telegram not configured")
        return
    try:
        requests.get(
            f"https://api.telegram.org/bot{TOKEN}/sendMessage",
            params={"chat_id": CHAT, "text": msg}, timeout=10
        )
    except Exception as e:
        print("[error] telegram:", e)

# Message de démarrage
send("🚀 Bot prêt ✅ (Railway)")

# Scheduler: heartbeat + résumé 21:00
scheduler = BackgroundScheduler(timezone=TZ)

def heartbeat():
    now = datetime.now(pytz.timezone(TZ)).strftime("%Y-%m-%d %H:%M:%S")
    print(f"[hb] {now}")

scheduler.add_job(heartbeat, "interval", minutes=30, id="hb")
scheduler.add_job(lambda: send("📝 Résumé quotidien (placeholder)"), "cron", hour=21, minute=0, id="daily")
scheduler.start()

_running = True
def handle_stop(signum, frame):
    global _running
    _running = False

signal.signal(signal.SIGTERM, handle_stop)
signal.signal(signal.SIGINT, handle_stop)

while _running:
    time.sleep(1)

scheduler.shutdown()
print("[exit] bye")
