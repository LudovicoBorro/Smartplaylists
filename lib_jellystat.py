"""
lib_jellystat.py — Client Jellystat API
=========================================
Interroga Jellystat per ottenere statistiche di riproduzione
affidabili per singolo utente.

Formato corretto dell'endpoint /api/getUserHistory (da sorgente):
  - Method:  POST
  - Body:    {"userid": "<jellyfin_user_id>"}   ← minuscolo, nel body
  - Query:   ?size=<N>&page=<N>&sort=ActivityDateInserted&desc=true
             &filters=[{"field":"ActivityDateInserted","min":"..."}]
  - Auth:    header "x-api-token: <api_key>"

Campi restituiti per ogni record:
  NowPlayingItemId, NowPlayingItemName, ActivityDateInserted,
  PlaybackDuration, UserName, Client, DeviceName, ItemType
"""

import json
import logging
import requests
from datetime import datetime, timedelta
from collections import Counter
from config import JELLYSTAT_URL, JELLYSTAT_API_KEY

log = logging.getLogger(__name__)

# Dimensione pagina per le richieste paginate
_PAGE_SIZE = 1000


class JellystatClient:

    def __init__(self):
        self.base = JELLYSTAT_URL.rstrip("/")
        self.headers = {
            "x-api-token": JELLYSTAT_API_KEY,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    # ── HTTP helper ───────────────────────────────────────────────────────────

    def _post_paged(self, path: str, userid: str,
                    query_params: dict) -> list[dict]:
        """
        Esegue POST con userid nel body e parametri in query string.
        Gestisce la paginazione automaticamente e ritorna tutti i record.
        """
        all_results = []
        page = 1

        while True:
            params = {**query_params, "page": page, "size": _PAGE_SIZE}
            try:
                r = requests.post(
                    f"{self.base}{path}",
                    headers=self.headers,
                    params=params,
                    json={"userid": userid},   # ← 'userid' minuscolo nel body
                    timeout=60,
                )
                r.raise_for_status()
                data = r.json()
            except Exception as e:
                log.error(f"Jellystat POST {path} (page {page}) -> {e}")
                break

            # La risposta puo essere lista diretta o dict con chiave "results"
            if isinstance(data, list):
                all_results.extend(data)
                break  # lista diretta = risposta completa
            elif isinstance(data, dict):
                rows = data.get("results") or data.get("data") or []
                all_results.extend(rows)
                total = data.get("total") or data.get("count") or 0
                if not rows or len(all_results) >= int(total) or len(rows) < _PAGE_SIZE:
                    break
                page += 1
            else:
                log.warning(f"Jellystat: risposta inattesa da {path}: {type(data)}")
                break

        return all_results

    # ── Utilita ───────────────────────────────────────────────────────────────

    def _date_iso(self, days: int) -> str:
        return (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%dT00:00:00.000Z")

    def _build_date_filter(self, days: int):
        if days <= 0:
            return None
        filters = [{"field": "ActivityDateInserted", "min": self._date_iso(days)}]
        return json.dumps(filters)

    def _is_audio(self, record: dict) -> bool:
        item_type = (record.get("ItemType") or record.get("itemType") or "")
        return item_type.lower() in ("audio", "musictrack", "")

    def _extract_item_id(self, record: dict):
        return (record.get("NowPlayingItemId") or
                record.get("itemId") or record.get("ItemId"))

    def _extract_item_name(self, record: dict) -> str:
        return (record.get("NowPlayingItemName") or
                record.get("itemName") or record.get("ItemName") or "")

    def _extract_date(self, record: dict) -> str:
        return (record.get("ActivityDateInserted") or
                record.get("datePlayed") or record.get("DatePlayed") or "")

    # ── API pubblica ──────────────────────────────────────────────────────────

    def get_user_history(self, jellyfin_user_id: str, days: int = 0) -> list[dict]:
        """Storico completo riproduzioni per utente. days=0 = tutto lo storico."""
        params = {"sort": "ActivityDateInserted", "desc": "true"}
        date_filter = self._build_date_filter(days)
        if date_filter:
            params["filters"] = date_filter
        records = self._post_paged("/api/getUserHistory", jellyfin_user_id, params)
        log.debug(f"  Jellystat: {len(records)} record totali (days={days})")
        return records

    def get_top_tracks(self, jellyfin_user_id: str, days: int = 0,
                       limit: int = 50) -> list[dict]:
        """Brani piu riprodotti. Ritorna lista [{itemId, playCount, itemName}]."""
        history = self.get_user_history(jellyfin_user_id, days)
        if not history:
            return []
        counts: Counter = Counter()
        names: dict = {}
        for record in history:
            if not self._is_audio(record):
                continue
            iid = self._extract_item_id(record)
            if iid:
                counts[iid] += 1
                if iid not in names:
                    names[iid] = self._extract_item_name(record)
        result = [
            {"itemId": iid, "playCount": cnt, "itemName": names.get(iid, "")}
            for iid, cnt in counts.most_common(limit)
        ]
        log.info(f"  Jellystat top_tracks: {len(result)} brani")
        return result

    def get_recent_tracks(self, jellyfin_user_id: str, days: int = 30,
                          limit: int = 50) -> list[dict]:
        """Brani recenti deduplicati, piu recente prima. Ritorna [{itemId, lastPlayed, itemName}]."""
        history = self.get_user_history(jellyfin_user_id, days)
        if not history:
            return []
        last_played: dict = {}
        for record in history:
            if not self._is_audio(record):
                continue
            iid = self._extract_item_id(record)
            if not iid:
                continue
            date_str = self._extract_date(record)
            if iid not in last_played or date_str > last_played[iid]["lastPlayed"]:
                last_played[iid] = {"itemId": iid, "lastPlayed": date_str,
                                    "itemName": self._extract_item_name(record)}
        sorted_items = sorted(last_played.values(),
                              key=lambda x: x["lastPlayed"], reverse=True)
        result = sorted_items[:limit]
        log.info(f"  Jellystat recent_tracks: {len(result)} brani (days={days})")
        return result

    def get_play_counts_in_period(self, jellyfin_user_id: str,
                                  days: int) -> dict:
        """Dict {itemId: playCount} per gli ultimi N giorni."""
        history = self.get_user_history(jellyfin_user_id, days)
        counts: Counter = Counter()
        for record in history:
            if not self._is_audio(record):
                continue
            iid = self._extract_item_id(record)
            if iid:
                counts[iid] += 1
        log.info(f"  Jellystat play_counts: {len(counts)} brani unici (days={days})")
        return dict(counts)