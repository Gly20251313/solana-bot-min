# main.py - Version finale corrigée avec Gecko comme source unique
import os
import logging
import time

# --- Configuration par variables d'environnement ---
MIN_LIQUIDITY = float(os.getenv("MIN_LIQUIDITY", 5000))
MIN_M5_CHANGE = float(os.getenv("MIN_M5_CHANGE", 50))
MIN_VOL_SOL   = float(os.getenv("MIN_VOL_SOL", 100))
THRESHOLD_PCT = float(os.getenv("THRESHOLD_PCT", 0.02))
MAX_OPEN_TRADES = int(os.getenv("MAX_OPEN_TRADES", 4))
POSITION_SIZE_PCT = float(os.getenv("POSITION_SIZE_PCT", 0.25))
STOP_LOSS_PCT = float(os.getenv("STOP_LOSS_PCT", 0.10))
TRAILING_TP_PCT = float(os.getenv("TRAILING_TP_PCT", 0.30))
TRAILING_TP_THROWBACK_PCT = float(os.getenv("TRAILING_TP_THROWBACK_PCT", 0.20))

# --- Logging ---
logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# --- Simulation fetch Gecko ---
def fetch_pairs_from_gecko():
    logger.info("[fetch] source=Gecko ...")
    # simulation d'un fetch
    pairs = [
        {"symbol": "TEST1/SOL", "liq": 12000, "vol": 900, "m5": 120.5},
        {"symbol": "TEST2/SOL", "liq": 4000, "vol": 500, "m5": 40.2},  # rejetée car < MIN_LIQUIDITY
    ]
    logger.info(f"[debug] fetch done: pairs={len(pairs)} seuils: liq>={MIN_LIQUIDITY}, m5>={MIN_M5_CHANGE}, vol>={MIN_VOL_SOL}")
    return pairs

# --- Scan ---
def scan_market():
    pairs = fetch_pairs_from_gecko()
    candidates = []
    for p in pairs:
        if p["liq"] < MIN_LIQUIDITY:
            logger.info(f"[skip] {p['symbol']} liq trop faible ({p['liq']})")
            continue
        if p["m5"] < MIN_M5_CHANGE:
            logger.info(f"[skip] {p['symbol']} m5 trop faible ({p['m5']})")
            continue
        if p["vol"] < MIN_VOL_SOL:
            logger.info(f"[skip] {p['symbol']} vol trop faible ({p['vol']})")
            continue
        candidates.append(p)
    logger.info(f"[scan] candidats valides: {len(candidates)}")
    return candidates

# --- Boucle principale ---
if __name__ == "__main__":
    logger.info("🚀 Bot démarré (Gecko only)")
    while True:
        try:
            scan_market()
        except Exception as e:
            logger.error(f"[scan error] {e}")
        time.sleep(30)
# main.py - Version finale corrigée avec Gecko comme source unique
import os
import logging
import time

# --- Configuration par variables d'environnement ---
MIN_LIQUIDITY = float(os.getenv("MIN_LIQUIDITY", 5000))
MIN_M5_CHANGE = float(os.getenv("MIN_M5_CHANGE", 50))
MIN_VOL_SOL   = float(os.getenv("MIN_VOL_SOL", 100))
THRESHOLD_PCT = float(os.getenv("THRESHOLD_PCT", 0.02))
MAX_OPEN_TRADES = int(os.getenv("MAX_OPEN_TRADES", 4))
POSITION_SIZE_PCT = float(os.getenv("POSITION_SIZE_PCT", 0.25))
STOP_LOSS_PCT = float(os.getenv("STOP_LOSS_PCT", 0.10))
TRAILING_TP_PCT = float(os.getenv("TRAILING_TP_PCT", 0.30))
TRAILING_TP_THROWBACK_PCT = float(os.getenv("TRAILING_TP_THROWBACK_PCT", 0.20))

# --- Logging ---
logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# --- Simulation fetch Gecko ---
def fetch_pairs_from_gecko():
    logger.info("[fetch] source=Gecko ...")
    # simulation d'un fetch
    pairs = [
        {"symbol": "TEST1/SOL", "liq": 12000, "vol": 900, "m5": 120.5},
        {"symbol": "TEST2/SOL", "liq": 4000, "vol": 500, "m5": 40.2},  # rejetée car < MIN_LIQUIDITY
    ]
    logger.info(f"[debug] fetch done: pairs={len(pairs)} seuils: liq>={MIN_LIQUIDITY}, m5>={MIN_M5_CHANGE}, vol>={MIN_VOL_SOL}")
    return pairs

# --- Scan ---
def scan_market():
    pairs = fetch_pairs_from_gecko()
    candidates = []
    for p in pairs:
        if p["liq"] < MIN_LIQUIDITY:
            logger.info(f"[skip] {p['symbol']} liq trop faible ({p['liq']})")
            continue
        if p["m5"] < MIN_M5_CHANGE:
            logger.info(f"[skip] {p['symbol']} m5 trop faible ({p['m5']})")
            continue
        if p["vol"] < MIN_VOL_SOL:
            logger.info(f"[skip] {p['symbol']} vol trop faible ({p['vol']})")
            continue
        candidates.append(p)
    logger.info(f"[scan] candidats valides: {len(candidates)}")
    return candidates

# --- Boucle principale ---
if __name__ == "__main__":
    logger.info("🚀 Bot démarré (Gecko only)")
    while True:
        try:
            scan_market()
        except Exception as e:
            logger.error(f"[scan error] {e}")
        time.sleep(30)
# main.py - Version finale corrigée avec Gecko comme source unique
import os
import logging
import time

# --- Configuration par variables d'environnement ---
MIN_LIQUIDITY = float(os.getenv("MIN_LIQUIDITY", 5000))
MIN_M5_CHANGE = float(os.getenv("MIN_M5_CHANGE", 50))
MIN_VOL_SOL   = float(os.getenv("MIN_VOL_SOL", 100))
THRESHOLD_PCT = float(os.getenv("THRESHOLD_PCT", 0.02))
MAX_OPEN_TRADES = int(os.getenv("MAX_OPEN_TRADES", 4))
POSITION_SIZE_PCT = float(os.getenv("POSITION_SIZE_PCT", 0.25))
STOP_LOSS_PCT = float(os.getenv("STOP_LOSS_PCT", 0.10))
TRAILING_TP_PCT = float(os.getenv("TRAILING_TP_PCT", 0.30))
TRAILING_TP_THROWBACK_PCT = float(os.getenv("TRAILING_TP_THROWBACK_PCT", 0.20))

# --- Logging ---
logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# --- Simulation fetch Gecko ---
def fetch_pairs_from_gecko():
    logger.info("[fetch] source=Gecko ...")
    # simulation d'un fetch
    pairs = [
        {"symbol": "TEST1/SOL", "liq": 12000, "vol": 900, "m5": 120.5},
        {"symbol": "TEST2/SOL", "liq": 4000, "vol": 500, "m5": 40.2},  # rejetée car < MIN_LIQUIDITY
    ]
    logger.info(f"[debug] fetch done: pairs={len(pairs)} seuils: liq>={MIN_LIQUIDITY}, m5>={MIN_M5_CHANGE}, vol>={MIN_VOL_SOL}")
    return pairs

# --- Scan ---
def scan_market():
    pairs = fetch_pairs_from_gecko()
    candidates = []
    for p in pairs:
        if p["liq"] < MIN_LIQUIDITY:
            logger.info(f"[skip] {p['symbol']} liq trop faible ({p['liq']})")
            continue
        if p["m5"] < MIN_M5_CHANGE:
            logger.info(f"[skip] {p['symbol']} m5 trop faible ({p['m5']})")
            continue
        if p["vol"] < MIN_VOL_SOL:
            logger.info(f"[skip] {p['symbol']} vol trop faible ({p['vol']})")
            continue
        candidates.append(p)
    logger.info(f"[scan] candidats valides: {len(candidates)}")
    return candidates

# --- Boucle principale ---
if __name__ == "__main__":
    logger.info("🚀 Bot démarré (Gecko only)")
    while True:
        try:
            scan_market()
        except Exception as e:
            logger.error(f"[scan error] {e}")
        time.sleep(30)
# main.py - Version finale corrigée avec Gecko comme source unique
import os
import logging
import time

# --- Configuration par variables d'environnement ---
MIN_LIQUIDITY = float(os.getenv("MIN_LIQUIDITY", 5000))
MIN_M5_CHANGE = float(os.getenv("MIN_M5_CHANGE", 50))
MIN_VOL_SOL   = float(os.getenv("MIN_VOL_SOL", 100))
THRESHOLD_PCT = float(os.getenv("THRESHOLD_PCT", 0.02))
MAX_OPEN_TRADES = int(os.getenv("MAX_OPEN_TRADES", 4))
POSITION_SIZE_PCT = float(os.getenv("POSITION_SIZE_PCT", 0.25))
STOP_LOSS_PCT = float(os.getenv("STOP_LOSS_PCT", 0.10))
TRAILING_TP_PCT = float(os.getenv("TRAILING_TP_PCT", 0.30))
TRAILING_TP_THROWBACK_PCT = float(os.getenv("TRAILING_TP_THROWBACK_PCT", 0.20))

# --- Logging ---
logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# --- Simulation fetch Gecko ---
def fetch_pairs_from_gecko():
    logger.info("[fetch] source=Gecko ...")
    # simulation d'un fetch
    pairs = [
        {"symbol": "TEST1/SOL", "liq": 12000, "vol": 900, "m5": 120.5},
        {"symbol": "TEST2/SOL", "liq": 4000, "vol": 500, "m5": 40.2},  # rejetée car < MIN_LIQUIDITY
    ]
    logger.info(f"[debug] fetch done: pairs={len(pairs)} seuils: liq>={MIN_LIQUIDITY}, m5>={MIN_M5_CHANGE}, vol>={MIN_VOL_SOL}")
    return pairs

# --- Scan ---
def scan_market():
    pairs = fetch_pairs_from_gecko()
    candidates = []
    for p in pairs:
        if p["liq"] < MIN_LIQUIDITY:
            logger.info(f"[skip] {p['symbol']} liq trop faible ({p['liq']})")
            continue
        if p["m5"] < MIN_M5_CHANGE:
            logger.info(f"[skip] {p['symbol']} m5 trop faible ({p['m5']})")
            continue
        if p["vol"] < MIN_VOL_SOL:
            logger.info(f"[skip] {p['symbol']} vol trop faible ({p['vol']})")
            continue
        candidates.append(p)
    logger.info(f"[scan] candidats valides: {len(candidates)}")
    return candidates

# --- Boucle principale ---
if __name__ == "__main__":
    logger.info("🚀 Bot démarré (Gecko only)")
    while True:
        try:
            scan_market()
        except Exception as e:
            logger.error(f"[scan error] {e}")
        time.sleep(30)
# main.py - Version finale corrigée avec Gecko comme source unique
import os
import logging
import time

# --- Configuration par variables d'environnement ---
MIN_LIQUIDITY = float(os.getenv("MIN_LIQUIDITY", 5000))
MIN_M5_CHANGE = float(os.getenv("MIN_M5_CHANGE", 50))
MIN_VOL_SOL   = float(os.getenv("MIN_VOL_SOL", 100))
THRESHOLD_PCT = float(os.getenv("THRESHOLD_PCT", 0.02))
MAX_OPEN_TRADES = int(os.getenv("MAX_OPEN_TRADES", 4))
POSITION_SIZE_PCT = float(os.getenv("POSITION_SIZE_PCT", 0.25))
STOP_LOSS_PCT = float(os.getenv("STOP_LOSS_PCT", 0.10))
TRAILING_TP_PCT = float(os.getenv("TRAILING_TP_PCT", 0.30))
TRAILING_TP_THROWBACK_PCT = float(os.getenv("TRAILING_TP_THROWBACK_PCT", 0.20))

# --- Logging ---
logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# --- Simulation fetch Gecko ---
def fetch_pairs_from_gecko():
    logger.info("[fetch] source=Gecko ...")
    # simulation d'un fetch
    pairs = [
        {"symbol": "TEST1/SOL", "liq": 12000, "vol": 900, "m5": 120.5},
        {"symbol": "TEST2/SOL", "liq": 4000, "vol": 500, "m5": 40.2},  # rejetée car < MIN_LIQUIDITY
    ]
    logger.info(f"[debug] fetch done: pairs={len(pairs)} seuils: liq>={MIN_LIQUIDITY}, m5>={MIN_M5_CHANGE}, vol>={MIN_VOL_SOL}")
    return pairs

# --- Scan ---
def scan_market():
    pairs = fetch_pairs_from_gecko()
    candidates = []
    for p in pairs:
        if p["liq"] < MIN_LIQUIDITY:
            logger.info(f"[skip] {p['symbol']} liq trop faible ({p['liq']})")
            continue
        if p["m5"] < MIN_M5_CHANGE:
            logger.info(f"[skip] {p['symbol']} m5 trop faible ({p['m5']})")
            continue
        if p["vol"] < MIN_VOL_SOL:
            logger.info(f"[skip] {p['symbol']} vol trop faible ({p['vol']})")
            continue
        candidates.append(p)
    logger.info(f"[scan] candidats valides: {len(candidates)}")
    return candidates

# --- Boucle principale ---
if __name__ == "__main__":
    logger.info("🚀 Bot démarré (Gecko only)")
    while True:
        try:
            scan_market()
        except Exception as e:
            logger.error(f"[scan error] {e}")
        time.sleep(30)
# main.py - Version finale corrigée avec Gecko comme source unique
import os
import logging
import time

# --- Configuration par variables d'environnement ---
MIN_LIQUIDITY = float(os.getenv("MIN_LIQUIDITY", 5000))
MIN_M5_CHANGE = float(os.getenv("MIN_M5_CHANGE", 50))
MIN_VOL_SOL   = float(os.getenv("MIN_VOL_SOL", 100))
THRESHOLD_PCT = float(os.getenv("THRESHOLD_PCT", 0.02))
MAX_OPEN_TRADES = int(os.getenv("MAX_OPEN_TRADES", 4))
POSITION_SIZE_PCT = float(os.getenv("POSITION_SIZE_PCT", 0.25))
STOP_LOSS_PCT = float(os.getenv("STOP_LOSS_PCT", 0.10))
TRAILING_TP_PCT = float(os.getenv("TRAILING_TP_PCT", 0.30))
TRAILING_TP_THROWBACK_PCT = float(os.getenv("TRAILING_TP_THROWBACK_PCT", 0.20))

# --- Logging ---
logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# --- Simulation fetch Gecko ---
def fetch_pairs_from_gecko():
    logger.info("[fetch] source=Gecko ...")
    # simulation d'un fetch
    pairs = [
        {"symbol": "TEST1/SOL", "liq": 12000, "vol": 900, "m5": 120.5},
        {"symbol": "TEST2/SOL", "liq": 4000, "vol": 500, "m5": 40.2},  # rejetée car < MIN_LIQUIDITY
    ]
    logger.info(f"[debug] fetch done: pairs={len(pairs)} seuils: liq>={MIN_LIQUIDITY}, m5>={MIN_M5_CHANGE}, vol>={MIN_VOL_SOL}")
    return pairs

# --- Scan ---
def scan_market():
    pairs = fetch_pairs_from_gecko()
    candidates = []
    for p in pairs:
        if p["liq"] < MIN_LIQUIDITY:
            logger.info(f"[skip] {p['symbol']} liq trop faible ({p['liq']})")
            continue
        if p["m5"] < MIN_M5_CHANGE:
            logger.info(f"[skip] {p['symbol']} m5 trop faible ({p['m5']})")
            continue
        if p["vol"] < MIN_VOL_SOL:
            logger.info(f"[skip] {p['symbol']} vol trop faible ({p['vol']})")
            continue
        candidates.append(p)
    logger.info(f"[scan] candidats valides: {len(candidates)}")
    return candidates

# --- Boucle principale ---
if __name__ == "__main__":
    logger.info("🚀 Bot démarré (Gecko only)")
    while True:
        try:
            scan_market()
        except Exception as e:
            logger.error(f"[scan error] {e}")
        time.sleep(30)
# main.py - Version finale corrigée avec Gecko comme source unique
import os
import logging
import time

# --- Configuration par variables d'environnement ---
MIN_LIQUIDITY = float(os.getenv("MIN_LIQUIDITY", 5000))
MIN_M5_CHANGE = float(os.getenv("MIN_M5_CHANGE", 50))
MIN_VOL_SOL   = float(os.getenv("MIN_VOL_SOL", 100))
THRESHOLD_PCT = float(os.getenv("THRESHOLD_PCT", 0.02))
MAX_OPEN_TRADES = int(os.getenv("MAX_OPEN_TRADES", 4))
POSITION_SIZE_PCT = float(os.getenv("POSITION_SIZE_PCT", 0.25))
STOP_LOSS_PCT = float(os.getenv("STOP_LOSS_PCT", 0.10))
TRAILING_TP_PCT = float(os.getenv("TRAILING_TP_PCT", 0.30))
TRAILING_TP_THROWBACK_PCT = float(os.getenv("TRAILING_TP_THROWBACK_PCT", 0.20))

# --- Logging ---
logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# --- Simulation fetch Gecko ---
def fetch_pairs_from_gecko():
    logger.info("[fetch] source=Gecko ...")
    # simulation d'un fetch
    pairs = [
        {"symbol": "TEST1/SOL", "liq": 12000, "vol": 900, "m5": 120.5},
        {"symbol": "TEST2/SOL", "liq": 4000, "vol": 500, "m5": 40.2},  # rejetée car < MIN_LIQUIDITY
    ]
    logger.info(f"[debug] fetch done: pairs={len(pairs)} seuils: liq>={MIN_LIQUIDITY}, m5>={MIN_M5_CHANGE}, vol>={MIN_VOL_SOL}")
    return pairs

# --- Scan ---
def scan_market():
    pairs = fetch_pairs_from_gecko()
    candidates = []
    for p in pairs:
        if p["liq"] < MIN_LIQUIDITY:
            logger.info(f"[skip] {p['symbol']} liq trop faible ({p['liq']})")
            continue
        if p["m5"] < MIN_M5_CHANGE:
            logger.info(f"[skip] {p['symbol']} m5 trop faible ({p['m5']})")
            continue
        if p["vol"] < MIN_VOL_SOL:
            logger.info(f"[skip] {p['symbol']} vol trop faible ({p['vol']})")
            continue
        candidates.append(p)
    logger.info(f"[scan] candidats valides: {len(candidates)}")
    return candidates

# --- Boucle principale ---
if __name__ == "__main__":
    logger.info("🚀 Bot démarré (Gecko only)")
    while True:
        try:
            scan_market()
        except Exception as e:
            logger.error(f"[scan error] {e}")
        time.sleep(30)
# main.py - Version finale corrigée avec Gecko comme source unique
import os
import logging
import time

# --- Configuration par variables d'environnement ---
MIN_LIQUIDITY = float(os.getenv("MIN_LIQUIDITY", 5000))
MIN_M5_CHANGE = float(os.getenv("MIN_M5_CHANGE", 50))
MIN_VOL_SOL   = float(os.getenv("MIN_VOL_SOL", 100))
THRESHOLD_PCT = float(os.getenv("THRESHOLD_PCT", 0.02))
MAX_OPEN_TRADES = int(os.getenv("MAX_OPEN_TRADES", 4))
POSITION_SIZE_PCT = float(os.getenv("POSITION_SIZE_PCT", 0.25))
STOP_LOSS_PCT = float(os.getenv("STOP_LOSS_PCT", 0.10))
TRAILING_TP_PCT = float(os.getenv("TRAILING_TP_PCT", 0.30))
TRAILING_TP_THROWBACK_PCT = float(os.getenv("TRAILING_TP_THROWBACK_PCT", 0.20))

# --- Logging ---
logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# --- Simulation fetch Gecko ---
def fetch_pairs_from_gecko():
    logger.info("[fetch] source=Gecko ...")
    # simulation d'un fetch
    pairs = [
        {"symbol": "TEST1/SOL", "liq": 12000, "vol": 900, "m5": 120.5},
        {"symbol": "TEST2/SOL", "liq": 4000, "vol": 500, "m5": 40.2},  # rejetée car < MIN_LIQUIDITY
    ]
    logger.info(f"[debug] fetch done: pairs={len(pairs)} seuils: liq>={MIN_LIQUIDITY}, m5>={MIN_M5_CHANGE}, vol>={MIN_VOL_SOL}")
    return pairs

# --- Scan ---
def scan_market():
    pairs = fetch_pairs_from_gecko()
    candidates = []
    for p in pairs:
        if p["liq"] < MIN_LIQUIDITY:
            logger.info(f"[skip] {p['symbol']} liq trop faible ({p['liq']})")
            continue
        if p["m5"] < MIN_M5_CHANGE:
            logger.info(f"[skip] {p['symbol']} m5 trop faible ({p['m5']})")
            continue
        if p["vol"] < MIN_VOL_SOL:
            logger.info(f"[skip] {p['symbol']} vol trop faible ({p['vol']})")
            continue
        candidates.append(p)
    logger.info(f"[scan] candidats valides: {len(candidates)}")
    return candidates

# --- Boucle principale ---
if __name__ == "__main__":
    logger.info("🚀 Bot démarré (Gecko only)")
    while True:
        try:
            scan_market()
        except Exception as e:
            logger.error(f"[scan error] {e}")
        time.sleep(30)
# main.py - Version finale corrigée avec Gecko comme source unique
import os
import logging
import time

# --- Configuration par variables d'environnement ---
MIN_LIQUIDITY = float(os.getenv("MIN_LIQUIDITY", 5000))
MIN_M5_CHANGE = float(os.getenv("MIN_M5_CHANGE", 50))
MIN_VOL_SOL   = float(os.getenv("MIN_VOL_SOL", 100))
THRESHOLD_PCT = float(os.getenv("THRESHOLD_PCT", 0.02))
MAX_OPEN_TRADES = int(os.getenv("MAX_OPEN_TRADES", 4))
POSITION_SIZE_PCT = float(os.getenv("POSITION_SIZE_PCT", 0.25))
STOP_LOSS_PCT = float(os.getenv("STOP_LOSS_PCT", 0.10))
TRAILING_TP_PCT = float(os.getenv("TRAILING_TP_PCT", 0.30))
TRAILING_TP_THROWBACK_PCT = float(os.getenv("TRAILING_TP_THROWBACK_PCT", 0.20))

# --- Logging ---
logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# --- Simulation fetch Gecko ---
def fetch_pairs_from_gecko():
    logger.info("[fetch] source=Gecko ...")
    # simulation d'un fetch
    pairs = [
        {"symbol": "TEST1/SOL", "liq": 12000, "vol": 900, "m5": 120.5},
        {"symbol": "TEST2/SOL", "liq": 4000, "vol": 500, "m5": 40.2},  # rejetée car < MIN_LIQUIDITY
    ]
    logger.info(f"[debug] fetch done: pairs={len(pairs)} seuils: liq>={MIN_LIQUIDITY}, m5>={MIN_M5_CHANGE}, vol>={MIN_VOL_SOL}")
    return pairs

# --- Scan ---
def scan_market():
    pairs = fetch_pairs_from_gecko()
    candidates = []
    for p in pairs:
        if p["liq"] < MIN_LIQUIDITY:
            logger.info(f"[skip] {p['symbol']} liq trop faible ({p['liq']})")
            continue
        if p["m5"] < MIN_M5_CHANGE:
            logger.info(f"[skip] {p['symbol']} m5 trop faible ({p['m5']})")
            continue
        if p["vol"] < MIN_VOL_SOL:
            logger.info(f"[skip] {p['symbol']} vol trop faible ({p['vol']})")
            continue
        candidates.append(p)
    logger.info(f"[scan] candidats valides: {len(candidates)}")
    return candidates

# --- Boucle principale ---
if __name__ == "__main__":
    logger.info("🚀 Bot démarré (Gecko only)")
    while True:
        try:
            scan_market()
        except Exception as e:
            logger.error(f"[scan error] {e}")
        time.sleep(30)
# main.py - Version finale corrigée avec Gecko comme source unique
import os
import logging
import time

# --- Configuration par variables d'environnement ---
MIN_LIQUIDITY = float(os.getenv("MIN_LIQUIDITY", 5000))
MIN_M5_CHANGE = float(os.getenv("MIN_M5_CHANGE", 50))
MIN_VOL_SOL   = float(os.getenv("MIN_VOL_SOL", 100))
THRESHOLD_PCT = float(os.getenv("THRESHOLD_PCT", 0.02))
MAX_OPEN_TRADES = int(os.getenv("MAX_OPEN_TRADES", 4))
POSITION_SIZE_PCT = float(os.getenv("POSITION_SIZE_PCT", 0.25))
STOP_LOSS_PCT = float(os.getenv("STOP_LOSS_PCT", 0.10))
TRAILING_TP_PCT = float(os.getenv("TRAILING_TP_PCT", 0.30))
TRAILING_TP_THROWBACK_PCT = float(os.getenv("TRAILING_TP_THROWBACK_PCT", 0.20))

# --- Logging ---
logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# --- Simulation fetch Gecko ---
def fetch_pairs_from_gecko():
    logger.info("[fetch] source=Gecko ...")
    # simulation d'un fetch
    pairs = [
        {"symbol": "TEST1/SOL", "liq": 12000, "vol": 900, "m5": 120.5},
        {"symbol": "TEST2/SOL", "liq": 4000, "vol": 500, "m5": 40.2},  # rejetée car < MIN_LIQUIDITY
    ]
    logger.info(f"[debug] fetch done: pairs={len(pairs)} seuils: liq>={MIN_LIQUIDITY}, m5>={MIN_M5_CHANGE}, vol>={MIN_VOL_SOL}")
    return pairs

# --- Scan ---
def scan_market():
    pairs = fetch_pairs_from_gecko()
    candidates = []
    for p in pairs:
        if p["liq"] < MIN_LIQUIDITY:
            logger.info(f"[skip] {p['symbol']} liq trop faible ({p['liq']})")
            continue
        if p["m5"] < MIN_M5_CHANGE:
            logger.info(f"[skip] {p['symbol']} m5 trop faible ({p['m5']})")
            continue
        if p["vol"] < MIN_VOL_SOL:
            logger.info(f"[skip] {p['symbol']} vol trop faible ({p['vol']})")
            continue
        candidates.append(p)
    logger.info(f"[scan] candidats valides: {len(candidates)}")
    return candidates

# --- Boucle principale ---
if __name__ == "__main__":
    logger.info("🚀 Bot démarré (Gecko only)")
    while True:
        try:
            scan_market()
        except Exception as e:
            logger.error(f"[scan error] {e}")
        time.sleep(30)
# main.py - Version finale corrigée avec Gecko comme source unique
import os
import logging
import time

# --- Configuration par variables d'environnement ---
MIN_LIQUIDITY = float(os.getenv("MIN_LIQUIDITY", 5000))
MIN_M5_CHANGE = float(os.getenv("MIN_M5_CHANGE", 50))
MIN_VOL_SOL   = float(os.getenv("MIN_VOL_SOL", 100))
THRESHOLD_PCT = float(os.getenv("THRESHOLD_PCT", 0.02))
MAX_OPEN_TRADES = int(os.getenv("MAX_OPEN_TRADES", 4))
POSITION_SIZE_PCT = float(os.getenv("POSITION_SIZE_PCT", 0.25))
STOP_LOSS_PCT = float(os.getenv("STOP_LOSS_PCT", 0.10))
TRAILING_TP_PCT = float(os.getenv("TRAILING_TP_PCT", 0.30))
TRAILING_TP_THROWBACK_PCT = float(os.getenv("TRAILING_TP_THROWBACK_PCT", 0.20))

# --- Logging ---
logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# --- Simulation fetch Gecko ---
def fetch_pairs_from_gecko():
    logger.info("[fetch] source=Gecko ...")
    # simulation d'un fetch
    pairs = [
        {"symbol": "TEST1/SOL", "liq": 12000, "vol": 900, "m5": 120.5},
        {"symbol": "TEST2/SOL", "liq": 4000, "vol": 500, "m5": 40.2},  # rejetée car < MIN_LIQUIDITY
    ]
    logger.info(f"[debug] fetch done: pairs={len(pairs)} seuils: liq>={MIN_LIQUIDITY}, m5>={MIN_M5_CHANGE}, vol>={MIN_VOL_SOL}")
    return pairs

# --- Scan ---
def scan_market():
    pairs = fetch_pairs_from_gecko()
    candidates = []
    for p in pairs:
        if p["liq"] < MIN_LIQUIDITY:
            logger.info(f"[skip] {p['symbol']} liq trop faible ({p['liq']})")
            continue
        if p["m5"] < MIN_M5_CHANGE:
            logger.info(f"[skip] {p['symbol']} m5 trop faible ({p['m5']})")
            continue
        if p["vol"] < MIN_VOL_SOL:
            logger.info(f"[skip] {p['symbol']} vol trop faible ({p['vol']})")
            continue
        candidates.append(p)
    logger.info(f"[scan] candidats valides: {len(candidates)}")
    return candidates

# --- Boucle principale ---
if __name__ == "__main__":
    logger.info("🚀 Bot démarré (Gecko only)")
    while True:
        try:
            scan_market()
        except Exception as e:
            logger.error(f"[scan error] {e}")
        time.sleep(30)
# main.py - Version finale corrigée avec Gecko comme source unique
import os
import logging
import time

# --- Configuration par variables d'environnement ---
MIN_LIQUIDITY = float(os.getenv("MIN_LIQUIDITY", 5000))
MIN_M5_CHANGE = float(os.getenv("MIN_M5_CHANGE", 50))
MIN_VOL_SOL   = float(os.getenv("MIN_VOL_SOL", 100))
THRESHOLD_PCT = float(os.getenv("THRESHOLD_PCT", 0.02))
MAX_OPEN_TRADES = int(os.getenv("MAX_OPEN_TRADES", 4))
POSITION_SIZE_PCT = float(os.getenv("POSITION_SIZE_PCT", 0.25))
STOP_LOSS_PCT = float(os.getenv("STOP_LOSS_PCT", 0.10))
TRAILING_TP_PCT = float(os.getenv("TRAILING_TP_PCT", 0.30))
TRAILING_TP_THROWBACK_PCT = float(os.getenv("TRAILING_TP_THROWBACK_PCT", 0.20))

# --- Logging ---
logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# --- Simulation fetch Gecko ---
def fetch_pairs_from_gecko():
    logger.info("[fetch] source=Gecko ...")
    # simulation d'un fetch
    pairs = [
        {"symbol": "TEST1/SOL", "liq": 12000, "vol": 900, "m5": 120.5},
        {"symbol": "TEST2/SOL", "liq": 4000, "vol": 500, "m5": 40.2},  # rejetée car < MIN_LIQUIDITY
    ]
    logger.info(f"[debug] fetch done: pairs={len(pairs)} seuils: liq>={MIN_LIQUIDITY}, m5>={MIN_M5_CHANGE}, vol>={MIN_VOL_SOL}")
    return pairs

# --- Scan ---
def scan_market():
    pairs = fetch_pairs_from_gecko()
    candidates = []
    for p in pairs:
        if p["liq"] < MIN_LIQUIDITY:
            logger.info(f"[skip] {p['symbol']} liq trop faible ({p['liq']})")
            continue
        if p["m5"] < MIN_M5_CHANGE:
            logger.info(f"[skip] {p['symbol']} m5 trop faible ({p['m5']})")
            continue
        if p["vol"] < MIN_VOL_SOL:
            logger.info(f"[skip] {p['symbol']} vol trop faible ({p['vol']})")
            continue
        candidates.append(p)
    logger.info(f"[scan] candidats valides: {len(candidates)}")
    return candidates

# --- Boucle principale ---
if __name__ == "__main__":
    logger.info("🚀 Bot démarré (Gecko only)")
    while True:
        try:
            scan_market()
        except Exception as e:
            logger.error(f"[scan error] {e}")
        time.sleep(30)
# main.py - Version finale corrigée avec Gecko comme source unique
import os
import logging
import time

# --- Configuration par variables d'environnement ---
MIN_LIQUIDITY = float(os.getenv("MIN_LIQUIDITY", 5000))
MIN_M5_CHANGE = float(os.getenv("MIN_M5_CHANGE", 50))
MIN_VOL_SOL   = float(os.getenv("MIN_VOL_SOL", 100))
THRESHOLD_PCT = float(os.getenv("THRESHOLD_PCT", 0.02))
MAX_OPEN_TRADES = int(os.getenv("MAX_OPEN_TRADES", 4))
POSITION_SIZE_PCT = float(os.getenv("POSITION_SIZE_PCT", 0.25))
STOP_LOSS_PCT = float(os.getenv("STOP_LOSS_PCT", 0.10))
TRAILING_TP_PCT = float(os.getenv("TRAILING_TP_PCT", 0.30))
TRAILING_TP_THROWBACK_PCT = float(os.getenv("TRAILING_TP_THROWBACK_PCT", 0.20))

# --- Logging ---
logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# --- Simulation fetch Gecko ---
def fetch_pairs_from_gecko():
    logger.info("[fetch] source=Gecko ...")
    # simulation d'un fetch
    pairs = [
        {"symbol": "TEST1/SOL", "liq": 12000, "vol": 900, "m5": 120.5},
        {"symbol": "TEST2/SOL", "liq": 4000, "vol": 500, "m5": 40.2},  # rejetée car < MIN_LIQUIDITY
    ]
    logger.info(f"[debug] fetch done: pairs={len(pairs)} seuils: liq>={MIN_LIQUIDITY}, m5>={MIN_M5_CHANGE}, vol>={MIN_VOL_SOL}")
    return pairs

# --- Scan ---
def scan_market():
    pairs = fetch_pairs_from_gecko()
    candidates = []
    for p in pairs:
        if p["liq"] < MIN_LIQUIDITY:
            logger.info(f"[skip] {p['symbol']} liq trop faible ({p['liq']})")
            continue
        if p["m5"] < MIN_M5_CHANGE:
            logger.info(f"[skip] {p['symbol']} m5 trop faible ({p['m5']})")
            continue
        if p["vol"] < MIN_VOL_SOL:
            logger.info(f"[skip] {p['symbol']} vol trop faible ({p['vol']})")
            continue
        candidates.append(p)
    logger.info(f"[scan] candidats valides: {len(candidates)}")
    return candidates

# --- Boucle principale ---
if __name__ == "__main__":
    logger.info("🚀 Bot démarré (Gecko only)")
    while True:
        try:
            scan_market()
        except Exception as e:
            logger.error(f"[scan error] {e}")
        time.sleep(30)
# main.py - Version finale corrigée avec Gecko comme source unique
import os
import logging
import time

# --- Configuration par variables d'environnement ---
MIN_LIQUIDITY = float(os.getenv("MIN_LIQUIDITY", 5000))
MIN_M5_CHANGE = float(os.getenv("MIN_M5_CHANGE", 50))
MIN_VOL_SOL   = float(os.getenv("MIN_VOL_SOL", 100))
THRESHOLD_PCT = float(os.getenv("THRESHOLD_PCT", 0.02))
MAX_OPEN_TRADES = int(os.getenv("MAX_OPEN_TRADES", 4))
POSITION_SIZE_PCT = float(os.getenv("POSITION_SIZE_PCT", 0.25))
STOP_LOSS_PCT = float(os.getenv("STOP_LOSS_PCT", 0.10))
TRAILING_TP_PCT = float(os.getenv("TRAILING_TP_PCT", 0.30))
TRAILING_TP_THROWBACK_PCT = float(os.getenv("TRAILING_TP_THROWBACK_PCT", 0.20))

# --- Logging ---
logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# --- Simulation fetch Gecko ---
def fetch_pairs_from_gecko():
    logger.info("[fetch] source=Gecko ...")
    # simulation d'un fetch
    pairs = [
        {"symbol": "TEST1/SOL", "liq": 12000, "vol": 900, "m5": 120.5},
        {"symbol": "TEST2/SOL", "liq": 4000, "vol": 500, "m5": 40.2},  # rejetée car < MIN_LIQUIDITY
    ]
    logger.info(f"[debug] fetch done: pairs={len(pairs)} seuils: liq>={MIN_LIQUIDITY}, m5>={MIN_M5_CHANGE}, vol>={MIN_VOL_SOL}")
    return pairs

# --- Scan ---
def scan_market():
    pairs = fetch_pairs_from_gecko()
    candidates = []
    for p in pairs:
        if p["liq"] < MIN_LIQUIDITY:
            logger.info(f"[skip] {p['symbol']} liq trop faible ({p['liq']})")
            continue
        if p["m5"] < MIN_M5_CHANGE:
            logger.info(f"[skip] {p['symbol']} m5 trop faible ({p['m5']})")
            continue
        if p["vol"] < MIN_VOL_SOL:
            logger.info(f"[skip] {p['symbol']} vol trop faible ({p['vol']})")
            continue
        candidates.append(p)
    logger.info(f"[scan] candidats valides: {len(candidates)}")
    return candidates

# --- Boucle principale ---
if __name__ == "__main__":
    logger.info("🚀 Bot démarré (Gecko only)")
    while True:
        try:
            scan_market()
        except Exception as e:
            logger.error(f"[scan error] {e}")
        time.sleep(30)
# main.py - Version finale corrigée avec Gecko comme source unique
import os
import logging
import time

# --- Configuration par variables d'environnement ---
MIN_LIQUIDITY = float(os.getenv("MIN_LIQUIDITY", 5000))
MIN_M5_CHANGE = float(os.getenv("MIN_M5_CHANGE", 50))
MIN_VOL_SOL   = float(os.getenv("MIN_VOL_SOL", 100))
THRESHOLD_PCT = float(os.getenv("THRESHOLD_PCT", 0.02))
MAX_OPEN_TRADES = int(os.getenv("MAX_OPEN_TRADES", 4))
POSITION_SIZE_PCT = float(os.getenv("POSITION_SIZE_PCT", 0.25))
STOP_LOSS_PCT = float(os.getenv("STOP_LOSS_PCT", 0.10))
TRAILING_TP_PCT = float(os.getenv("TRAILING_TP_PCT", 0.30))
TRAILING_TP_THROWBACK_PCT = float(os.getenv("TRAILING_TP_THROWBACK_PCT", 0.20))

# --- Logging ---
logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# --- Simulation fetch Gecko ---
def fetch_pairs_from_gecko():
    logger.info("[fetch] source=Gecko ...")
    # simulation d'un fetch
    pairs = [
        {"symbol": "TEST1/SOL", "liq": 12000, "vol": 900, "m5": 120.5},
        {"symbol": "TEST2/SOL", "liq": 4000, "vol": 500, "m5": 40.2},  # rejetée car < MIN_LIQUIDITY
    ]
    logger.info(f"[debug] fetch done: pairs={len(pairs)} seuils: liq>={MIN_LIQUIDITY}, m5>={MIN_M5_CHANGE}, vol>={MIN_VOL_SOL}")
    return pairs

# --- Scan ---
def scan_market():
    pairs = fetch_pairs_from_gecko()
    candidates = []
    for p in pairs:
        if p["liq"] < MIN_LIQUIDITY:
            logger.info(f"[skip] {p['symbol']} liq trop faible ({p['liq']})")
            continue
        if p["m5"] < MIN_M5_CHANGE:
            logger.info(f"[skip] {p['symbol']} m5 trop faible ({p['m5']})")
            continue
        if p["vol"] < MIN_VOL_SOL:
            logger.info(f"[skip] {p['symbol']} vol trop faible ({p['vol']})")
            continue
        candidates.append(p)
    logger.info(f"[scan] candidats valides: {len(candidates)}")
    return candidates

# --- Boucle principale ---
if __name__ == "__main__":
    logger.info("🚀 Bot démarré (Gecko only)")
    while True:
        try:
            scan_market()
        except Exception as e:
            logger.error(f"[scan error] {e}")
        time.sleep(30)
# main.py - Version finale corrigée avec Gecko comme source unique
import os
import logging
import time

# --- Configuration par variables d'environnement ---
MIN_LIQUIDITY = float(os.getenv("MIN_LIQUIDITY", 5000))
MIN_M5_CHANGE = float(os.getenv("MIN_M5_CHANGE", 50))
MIN_VOL_SOL   = float(os.getenv("MIN_VOL_SOL", 100))
THRESHOLD_PCT = float(os.getenv("THRESHOLD_PCT", 0.02))
MAX_OPEN_TRADES = int(os.getenv("MAX_OPEN_TRADES", 4))
POSITION_SIZE_PCT = float(os.getenv("POSITION_SIZE_PCT", 0.25))
STOP_LOSS_PCT = float(os.getenv("STOP_LOSS_PCT", 0.10))
TRAILING_TP_PCT = float(os.getenv("TRAILING_TP_PCT", 0.30))
TRAILING_TP_THROWBACK_PCT = float(os.getenv("TRAILING_TP_THROWBACK_PCT", 0.20))

# --- Logging ---
logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# --- Simulation fetch Gecko ---
def fetch_pairs_from_gecko():
    logger.info("[fetch] source=Gecko ...")
    # simulation d'un fetch
    pairs = [
        {"symbol": "TEST1/SOL", "liq": 12000, "vol": 900, "m5": 120.5},
        {"symbol": "TEST2/SOL", "liq": 4000, "vol": 500, "m5": 40.2},  # rejetée car < MIN_LIQUIDITY
    ]
    logger.info(f"[debug] fetch done: pairs={len(pairs)} seuils: liq>={MIN_LIQUIDITY}, m5>={MIN_M5_CHANGE}, vol>={MIN_VOL_SOL}")
    return pairs

# --- Scan ---
def scan_market():
    pairs = fetch_pairs_from_gecko()
    candidates = []
    for p in pairs:
        if p["liq"] < MIN_LIQUIDITY:
            logger.info(f"[skip] {p['symbol']} liq trop faible ({p['liq']})")
            continue
        if p["m5"] < MIN_M5_CHANGE:
            logger.info(f"[skip] {p['symbol']} m5 trop faible ({p['m5']})")
            continue
        if p["vol"] < MIN_VOL_SOL:
            logger.info(f"[skip] {p['symbol']} vol trop faible ({p['vol']})")
            continue
        candidates.append(p)
    logger.info(f"[scan] candidats valides: {len(candidates)}")
    return candidates

# --- Boucle principale ---
if __name__ == "__main__":
    logger.info("🚀 Bot démarré (Gecko only)")
    while True:
        try:
            scan_market()
        except Exception as e:
            logger.error(f"[scan error] {e}")
        time.sleep(30)
# main.py - Version finale corrigée avec Gecko comme source unique
import os
import logging
import time

# --- Configuration par variables d'environnement ---
MIN_LIQUIDITY = float(os.getenv("MIN_LIQUIDITY", 5000))
MIN_M5_CHANGE = float(os.getenv("MIN_M5_CHANGE", 50))
MIN_VOL_SOL   = float(os.getenv("MIN_VOL_SOL", 100))
THRESHOLD_PCT = float(os.getenv("THRESHOLD_PCT", 0.02))
MAX_OPEN_TRADES = int(os.getenv("MAX_OPEN_TRADES", 4))
POSITION_SIZE_PCT = float(os.getenv("POSITION_SIZE_PCT", 0.25))
STOP_LOSS_PCT = float(os.getenv("STOP_LOSS_PCT", 0.10))
TRAILING_TP_PCT = float(os.getenv("TRAILING_TP_PCT", 0.30))
TRAILING_TP_THROWBACK_PCT = float(os.getenv("TRAILING_TP_THROWBACK_PCT", 0.20))

# --- Logging ---
logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# --- Simulation fetch Gecko ---
def fetch_pairs_from_gecko():
    logger.info("[fetch] source=Gecko ...")
    # simulation d'un fetch
    pairs = [
        {"symbol": "TEST1/SOL", "liq": 12000, "vol": 900, "m5": 120.5},
        {"symbol": "TEST2/SOL", "liq": 4000, "vol": 500, "m5": 40.2},  # rejetée car < MIN_LIQUIDITY
    ]
    logger.info(f"[debug] fetch done: pairs={len(pairs)} seuils: liq>={MIN_LIQUIDITY}, m5>={MIN_M5_CHANGE}, vol>={MIN_VOL_SOL}")
    return pairs

# --- Scan ---
def scan_market():
    pairs = fetch_pairs_from_gecko()
    candidates = []
    for p in pairs:
        if p["liq"] < MIN_LIQUIDITY:
            logger.info(f"[skip] {p['symbol']} liq trop faible ({p['liq']})")
            continue
        if p["m5"] < MIN_M5_CHANGE:
            logger.info(f"[skip] {p['symbol']} m5 trop faible ({p['m5']})")
            continue
        if p["vol"] < MIN_VOL_SOL:
            logger.info(f"[skip] {p['symbol']} vol trop faible ({p['vol']})")
            continue
        candidates.append(p)
    logger.info(f"[scan] candidats valides: {len(candidates)}")
    return candidates

# --- Boucle principale ---
if __name__ == "__main__":
    logger.info("🚀 Bot démarré (Gecko only)")
    while True:
        try:
            scan_market()
        except Exception as e:
            logger.error(f"[scan error] {e}")
        time.sleep(30)
# main.py - Version finale corrigée avec Gecko comme source unique
import os
import logging
import time

# --- Configuration par variables d'environnement ---
MIN_LIQUIDITY = float(os.getenv("MIN_LIQUIDITY", 5000))
MIN_M5_CHANGE = float(os.getenv("MIN_M5_CHANGE", 50))
MIN_VOL_SOL   = float(os.getenv("MIN_VOL_SOL", 100))
THRESHOLD_PCT = float(os.getenv("THRESHOLD_PCT", 0.02))
MAX_OPEN_TRADES = int(os.getenv("MAX_OPEN_TRADES", 4))
POSITION_SIZE_PCT = float(os.getenv("POSITION_SIZE_PCT", 0.25))
STOP_LOSS_PCT = float(os.getenv("STOP_LOSS_PCT", 0.10))
TRAILING_TP_PCT = float(os.getenv("TRAILING_TP_PCT", 0.30))
TRAILING_TP_THROWBACK_PCT = float(os.getenv("TRAILING_TP_THROWBACK_PCT", 0.20))

# --- Logging ---
logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# --- Simulation fetch Gecko ---
def fetch_pairs_from_gecko():
    logger.info("[fetch] source=Gecko ...")
    # simulation d'un fetch
    pairs = [
        {"symbol": "TEST1/SOL", "liq": 12000, "vol": 900, "m5": 120.5},
        {"symbol": "TEST2/SOL", "liq": 4000, "vol": 500, "m5": 40.2},  # rejetée car < MIN_LIQUIDITY
    ]
    logger.info(f"[debug] fetch done: pairs={len(pairs)} seuils: liq>={MIN_LIQUIDITY}, m5>={MIN_M5_CHANGE}, vol>={MIN_VOL_SOL}")
    return pairs

# --- Scan ---
def scan_market():
    pairs = fetch_pairs_from_gecko()
    candidates = []
    for p in pairs:
        if p["liq"] < MIN_LIQUIDITY:
            logger.info(f"[skip] {p['symbol']} liq trop faible ({p['liq']})")
            continue
        if p["m5"] < MIN_M5_CHANGE:
            logger.info(f"[skip] {p['symbol']} m5 trop faible ({p['m5']})")
            continue
        if p["vol"] < MIN_VOL_SOL:
            logger.info(f"[skip] {p['symbol']} vol trop faible ({p['vol']})")
            continue
        candidates.append(p)
    logger.info(f"[scan] candidats valides: {len(candidates)}")
    return candidates

# --- Boucle principale ---
if __name__ == "__main__":
    logger.info("🚀 Bot démarré (Gecko only)")
    while True:
        try:
            scan_market()
        except Exception as e:
            logger.error(f"[scan error] {e}")
        time.sleep(30)
# main.py - Version finale corrigée avec Gecko comme source unique
import os
import logging
import time

# --- Configuration par variables d'environnement ---
MIN_LIQUIDITY = float(os.getenv("MIN_LIQUIDITY", 5000))
MIN_M5_CHANGE = float(os.getenv("MIN_M5_CHANGE", 50))
MIN_VOL_SOL   = float(os.getenv("MIN_VOL_SOL", 100))
THRESHOLD_PCT = float(os.getenv("THRESHOLD_PCT", 0.02))
MAX_OPEN_TRADES = int(os.getenv("MAX_OPEN_TRADES", 4))
POSITION_SIZE_PCT = float(os.getenv("POSITION_SIZE_PCT", 0.25))
STOP_LOSS_PCT = float(os.getenv("STOP_LOSS_PCT", 0.10))
TRAILING_TP_PCT = float(os.getenv("TRAILING_TP_PCT", 0.30))
TRAILING_TP_THROWBACK_PCT = float(os.getenv("TRAILING_TP_THROWBACK_PCT", 0.20))

# --- Logging ---
logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# --- Simulation fetch Gecko ---
def fetch_pairs_from_gecko():
    logger.info("[fetch] source=Gecko ...")
    # simulation d'un fetch
    pairs = [
        {"symbol": "TEST1/SOL", "liq": 12000, "vol": 900, "m5": 120.5},
        {"symbol": "TEST2/SOL", "liq": 4000, "vol": 500, "m5": 40.2},  # rejetée car < MIN_LIQUIDITY
    ]
    logger.info(f"[debug] fetch done: pairs={len(pairs)} seuils: liq>={MIN_LIQUIDITY}, m5>={MIN_M5_CHANGE}, vol>={MIN_VOL_SOL}")
    return pairs

# --- Scan ---
def scan_market():
    pairs = fetch_pairs_from_gecko()
    candidates = []
    for p in pairs:
        if p["liq"] < MIN_LIQUIDITY:
            logger.info(f"[skip] {p['symbol']} liq trop faible ({p['liq']})")
            continue
        if p["m5"] < MIN_M5_CHANGE:
            logger.info(f"[skip] {p['symbol']} m5 trop faible ({p['m5']})")
            continue
        if p["vol"] < MIN_VOL_SOL:
            logger.info(f"[skip] {p['symbol']} vol trop faible ({p['vol']})")
            continue
        candidates.append(p)
    logger.info(f"[scan] candidats valides: {len(candidates)}")
    return candidates

# --- Boucle principale ---
if __name__ == "__main__":
    logger.info("🚀 Bot démarré (Gecko only)")
    while True:
        try:
            scan_market()
        except Exception as e:
            logger.error(f"[scan error] {e}")
        time.sleep(30)
# main.py - Version finale corrigée avec Gecko comme source unique
import os
import logging
import time

# --- Configuration par variables d'environnement ---
MIN_LIQUIDITY = float(os.getenv("MIN_LIQUIDITY", 5000))
MIN_M5_CHANGE = float(os.getenv("MIN_M5_CHANGE", 50))
MIN_VOL_SOL   = float(os.getenv("MIN_VOL_SOL", 100))
THRESHOLD_PCT = float(os.getenv("THRESHOLD_PCT", 0.02))
MAX_OPEN_TRADES = int(os.getenv("MAX_OPEN_TRADES", 4))
POSITION_SIZE_PCT = float(os.getenv("POSITION_SIZE_PCT", 0.25))
STOP_LOSS_PCT = float(os.getenv("STOP_LOSS_PCT", 0.10))
TRAILING_TP_PCT = float(os.getenv("TRAILING_TP_PCT", 0.30))
TRAILING_TP_THROWBACK_PCT = float(os.getenv("TRAILING_TP_THROWBACK_PCT", 0.20))

# --- Logging ---
logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# --- Simulation fetch Gecko ---
def fetch_pairs_from_gecko():
    logger.info("[fetch] source=Gecko ...")
    # simulation d'un fetch
    pairs = [
        {"symbol": "TEST1/SOL", "liq": 12000, "vol": 900, "m5": 120.5},
        {"symbol": "TEST2/SOL", "liq": 4000, "vol": 500, "m5": 40.2},  # rejetée car < MIN_LIQUIDITY
    ]
    logger.info(f"[debug] fetch done: pairs={len(pairs)} seuils: liq>={MIN_LIQUIDITY}, m5>={MIN_M5_CHANGE}, vol>={MIN_VOL_SOL}")
    return pairs

# --- Scan ---
def scan_market():
    pairs = fetch_pairs_from_gecko()
    candidates = []
    for p in pairs:
        if p["liq"] < MIN_LIQUIDITY:
            logger.info(f"[skip] {p['symbol']} liq trop faible ({p['liq']})")
            continue
        if p["m5"] < MIN_M5_CHANGE:
            logger.info(f"[skip] {p['symbol']} m5 trop faible ({p['m5']})")
            continue
        if p["vol"] < MIN_VOL_SOL:
            logger.info(f"[skip] {p['symbol']} vol trop faible ({p['vol']})")
            continue
        candidates.append(p)
    logger.info(f"[scan] candidats valides: {len(candidates)}")
    return candidates

# --- Boucle principale ---
if __name__ == "__main__":
    logger.info("🚀 Bot démarré (Gecko only)")
    while True:
        try:
            scan_market()
        except Exception as e:
            logger.error(f"[scan error] {e}")
        time.sleep(30)
