"""
config.py — Configurazione centralizzata Smart Playlists
=========================================================
Modifica solo questo file per adattare tutto il sistema al tuo setup.
"""

# ── Jellyfin ──────────────────────────────────────────────────────────────────
JELLYFIN_URL     = "http://192.168.1.15:8096/jellyfin"
JELLYFIN_API_KEY = "6baa16817c7a44289583cef33cdae375"   # Dashboard → Avanzate → Chiavi API

# ── Jellystat ─────────────────────────────────────────────────────────────────
JELLYSTAT_URL     = "http://192.168.1.15:3000"
JELLYSTAT_API_KEY = "5e2b91b6-7ac2-4c04-9127-310ae8f9499d"  # Jellystat → Settings → API Key

# ── Utenti da escludere (es. account admin di servizio) ───────────────────────
# Metti qui i nomi utente Jellyfin che NON devono ricevere playlist
EXCLUDED_USERS = ["Marco"]

# ── Log ───────────────────────────────────────────────────────────────────────
LOG_DIR  = "/var/log/smartplaylists"
LOG_FILE = f"{LOG_DIR}/orchestrator.log"   # log orchestratore
# ogni script scrive anche il proprio log: /var/log/smartplaylists/<script>.log

# ── Notifiche mail (usa msmtp già configurato sul server) ─────────────────────
NOTIFY_EMAIL          = "ludovicoborro@gmail.com"      # es. "tuamail@gmail.com" — lascia vuoto per disabilitare
NOTIFY_ON_ERROR_ONLY  = True    # True = mail solo su errore

# ══════════════════════════════════════════════════════════════════════════════
#  PARAMETRI PLAYLIST — modifica a piacere
# ══════════════════════════════════════════════════════════════════════════════

# ── 1. Top Brani (più ascoltati in assoluto) ──────────────────────────────────
TOP_TRACKS = {
    "playlist_name": "⭐ I Tuoi Top Brani",
    "count":  50,          # numero di brani nella playlist
    "days":   365,         # periodo di analisi (0 = tutto lo storico)
}

# ── 2. Ascoltati di Recente ───────────────────────────────────────────────────
RECENT = {
    "playlist_name": "🕐 Ascoltati di Recente",
    "count": 50,           # numero di brani
    "days":  30,           # quanti giorni indietro guardare
}

# ── 3. Daily Mix ──────────────────────────────────────────────────────────────
DAILY_MIX = {
    "playlist_name":    "🎵 Daily Mix",
    "count":            40,   # brani totali nel mix
    "top_genres":        3,   # quanti generi principali considerare
    "analysis_days":    90,   # giorni di storico per rilevare i tuoi generi
    "recent_boost_days": 30,  # brani ascoltati in questo periodo hanno priorità
    "recent_boost_weight": 2, # moltiplicatore di priorità per i brani recenti
    "randomize":       True,  # mescola i brani nel mix finale
}

# ── 4. Preferiti del Periodo ──────────────────────────────────────────────────
TOP_PERIOD = {
    "playlist_name": "📅 Top del Mese",
    "count": 30,           # numero di brani
    "days":  30,           # durata del periodo (30 = ultimo mese, 7 = ultima settimana)
}