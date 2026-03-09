"""
playlist_top_tracks.py — Top Brani (più ascoltati in assoluto)
===============================================================
Per ogni utente crea/aggiorna la playlist con i brani
più ascoltati in tutto lo storico (o negli ultimi N giorni).

La playlist è privata: creata nel contesto dell'utente,
visibile solo a lui (e agli admin).
"""

import logging
from config import TOP_TRACKS
from lib_jellyfin import JellyfinClient
from lib_jellystat import JellystatClient

log = logging.getLogger(__name__)


def generate(jellyfin_user_id: str, jellyfin_user_name: str) -> bool:
    """
    Genera la playlist Top Brani per un singolo utente.
    Ritorna True se completato senza errori.
    """
    cfg = TOP_TRACKS
    log.info(f"[top_tracks] Utente: {jellyfin_user_name}")

    jf = JellyfinClient()
    js = JellystatClient()

    # 1. Recupera top brani da Jellystat (dati affidabili per utente)
    top = js.get_top_tracks(
        jellyfin_user_id=jellyfin_user_id,
        days=cfg["days"],
        limit=cfg["count"],
    )

    if not top:
        log.warning(f"[top_tracks] Nessun dato per {jellyfin_user_name}, playlist saltata")
        return True  # non è un errore, l'utente non ha ancora ascoltato nulla

    # 2. Estrai gli ID e validali (verifica che esistano ancora in libreria)
    raw_ids = [t["itemId"] for t in top if t.get("itemId")]
    valid_ids = jf.validate_item_ids(jellyfin_user_id, raw_ids)

    if not valid_ids:
        log.warning(f"[top_tracks] Nessun brano valido per {jellyfin_user_name}")
        return True

    log.info(f"[top_tracks] {len(valid_ids)} brani validi per {jellyfin_user_name}")

    # 3. Aggiorna la playlist (ordinata per play count, dal più al meno ascoltato)
    success = jf.update_playlist(
        user_id=jellyfin_user_id,
        name=cfg["playlist_name"],
        item_ids=valid_ids,
        randomize=False,  # ordine decrescente per play count
    )

    if success:
        log.info(f"[top_tracks] ✓ '{cfg['playlist_name']}' aggiornata "
                 f"({len(valid_ids)} brani) per {jellyfin_user_name}")
    else:
        log.error(f"[top_tracks] ✗ Errore aggiornamento playlist per {jellyfin_user_name}")

    return success