"""
lib_jellyfin.py — Client Jellyfin API
======================================
Gestisce utenti, brani per genere e operazioni sulle playlist.

Gli ID delle playlist vengono salvati in un file JSON locale
(/var/lib/smartplaylists/playlist_ids.json) mappati per user_id.

STRATEGIA AGGIORNAMENTO PLAYLIST (delete + recreate)
─────────────────────────────────────────────────────
Jellyfin applica ownership strict sulle playlist private:
  POST /Playlists/{id}/Items   → 403 con token admin
  DELETE /Playlists/{id}/Items → 403 con token admin
Funzionano invece con token admin:
  POST /Playlists              → creazione con Ids nel body
  DELETE /Items/{id}           → eliminazione intera playlist

Ogni aggiornamento quindi elimina la playlist esistente e ne crea
una nuova con i brani già inclusi nel body di creazione.

Le playlist vengono create come PRIVATE (IsPublic: false) in modo
che ogni utente veda solo le proprie.
"""

import json
import logging
import os
import random
import requests
from config import JELLYFIN_URL, JELLYFIN_API_KEY

log = logging.getLogger(__name__)

PLAYLIST_IDS_FILE = "/var/lib/smartplaylists/playlist_ids.json"


def _load_registry() -> dict:
    try:
        with open(PLAYLIST_IDS_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_registry(data: dict):
    os.makedirs(os.path.dirname(PLAYLIST_IDS_FILE), exist_ok=True)
    with open(PLAYLIST_IDS_FILE, "w") as f:
        json.dump(data, f, indent=2)


def _get_registered_id(user_id: str, name: str) -> str | None:
    return _load_registry().get(user_id, {}).get(name)


def _register_id(user_id: str, name: str, playlist_id: str):
    registry = _load_registry()
    registry.setdefault(user_id, {})[name] = playlist_id
    _save_registry(registry)


def _unregister_id(user_id: str, name: str):
    registry = _load_registry()
    if user_id in registry:
        registry[user_id].pop(name, None)
        _save_registry(registry)


class JellyfinClient:

    def __init__(self):
        self.base = JELLYFIN_URL.rstrip("/")
        self.headers = {
            "X-Emby-Token": JELLYFIN_API_KEY,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    # ── HTTP helpers ──────────────────────────────────────────────────────────

    def _get(self, path, params=None):
        try:
            r = requests.get(f"{self.base}{path}", headers=self.headers,
                             params=params, timeout=30)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            log.error(f"GET {path} -> {e}")
            return None

    def _post(self, path, data=None, params=None):
        try:
            r = requests.post(f"{self.base}{path}", headers=self.headers,
                              json=data, params=params, timeout=30)
            r.raise_for_status()
            return r.json() if r.text else {}
        except Exception as e:
            log.error(f"POST {path} -> {e}")
            return None

    def _delete(self, path, params=None):
        try:
            r = requests.delete(f"{self.base}{path}", headers=self.headers,
                                params=params, timeout=30)
            r.raise_for_status()
            return True
        except Exception as e:
            log.error(f"DELETE {path} -> {e}")
            return False

    def _post_raw(self, path, data=None, params=None):
        """Come _post ma ritorna anche il response object per controllare lo status."""
        try:
            r = requests.post(f"{self.base}{path}", headers=self.headers,
                              json=data, params=params, timeout=30)
            return r
        except Exception as e:
            log.error(f"POST_RAW {path} -> {e}")
            return None

    # ── Utenti ────────────────────────────────────────────────────────────────

    def get_all_users(self) -> list[dict]:
        result = self._get("/Users")
        if not result:
            return []
        return [{"id": u["Id"], "name": u["Name"]} for u in result]

    # ── Libreria musicale ─────────────────────────────────────────────────────

    def get_genres_for_items(self, user_id: str,
                             item_ids: list[str]) -> dict[str, list[str]]:
        result = {}
        for i in range(0, len(item_ids), 100):
            chunk = item_ids[i:i+100]
            data = self._get("/Items", params={
                "UserId": user_id,
                "Ids": ",".join(chunk),
                "IncludeItemTypes": "Audio",
                "Recursive": True,
                "Fields": "Genres,Tags",
                "Limit": len(chunk),
            })
            if not data or "Items" not in data:
                continue
            for item in data["Items"]:
                iid = item.get("Id")
                if iid:
                    result[iid] = item.get("Genres") or []
        return result

    def get_audio_items_by_genre(self, user_id: str, genre: str,
                                  limit: int = 500) -> list[dict]:
        result = self._get("/Items", params={
            "UserId": user_id,
            "IncludeItemTypes": "Audio",
            "Recursive": True,
            "Genres": genre,
            "Fields": "Genres",
            "Limit": limit,
        })
        return result["Items"] if result and "Items" in result else []

    def get_all_audio_items(self, user_id: str, limit: int = 200) -> list[dict]:
        result = self._get("/Items", params={
            "UserId": user_id,
            "IncludeItemTypes": "Audio",
            "Recursive": True,
            "Fields": "Genres",
            "SortBy": "Random",
            "Limit": limit,
        })
        return result["Items"] if result and "Items" in result else []

    def validate_item_ids(self, user_id: str, item_ids: list[str]) -> list[str]:
        if not item_ids:
            return []
        valid = []
        for i in range(0, len(item_ids), 200):
            chunk = item_ids[i:i+200]
            result = self._get("/Items", params={
                "UserId": user_id,
                "Ids": ",".join(chunk),
                "IncludeItemTypes": "Audio",
                "Recursive": True,
                "Limit": len(chunk),
            })
            if result and "Items" in result:
                valid.extend([it["Id"] for it in result["Items"]])
        return valid

    # ── Playlist ──────────────────────────────────────────────────────────────
    #
    # STRATEGIA: delete + recreate
    # ─────────────────────────────
    # Jellyfin applica ownership strict sulle playlist private:
    #   • POST /Playlists/{id}/Items  → 403 con token admin
    #   • DELETE /Playlists/{id}/Items → 403 con token admin
    # Gli unici endpoint che funzionano con il token admin sono:
    #   • POST /Playlists  (creazione, con Ids nel body)
    #   • DELETE /Playlists/{id}  (cancellazione intera playlist)
    # Quindi ogni aggiornamento = elimina vecchia + crea nuova con i brani.

    def _delete_playlist(self, playlist_id: str) -> bool:
        """Elimina fisicamente la playlist. L'admin può sempre farlo."""
        ok = self._delete(f"/Items/{playlist_id}")
        if ok:
            log.debug(f"  Playlist {playlist_id} eliminata")
        else:
            log.warning(f"  Impossibile eliminare playlist {playlist_id} (già rimossa?)")
        return ok

    def _create_playlist_with_items(self, user_id: str, name: str,
                                     item_ids: list[str]) -> str | None:
        """
        Crea una playlist PRIVATA con i brani già inclusi nel body.
        Usa POST /Playlists con Ids=[...] — funziona con token admin.
        Registra l'ID risultante.
        """
        result = self._post("/Playlists", data={
            "Name": name,
            "UserId": user_id,
            "MediaType": "Audio",
            "IsPublic": False,
            "Ids": item_ids,
        })
        if result:
            pid = result.get("Id") or result.get("id")
            if pid:
                _register_id(user_id, name, pid)
                log.info(f"  Playlist '{name}' creata con {len(item_ids)} brani (ID: {pid})")
                return pid
        log.error(f"  Impossibile creare playlist '{name}'")
        return None

    def update_playlist(self, user_id: str, name: str,
                        item_ids: list[str], randomize: bool = False) -> bool:
        """
        Aggiorna una playlist con la strategia delete+recreate:
        1. Se esiste nel registro, la elimina fisicamente
        2. Crea una nuova playlist con tutti i brani nel body di creazione
        3. Salva il nuovo ID nel registro
        """
        ids = list(item_ids)
        if randomize:
            random.shuffle(ids)

        # 1. Elimina la vecchia se esiste
        old_pid = _get_registered_id(user_id, name)
        if old_pid:
            self._delete_playlist(old_pid)
            _unregister_id(user_id, name)

        # 2. Crea con i brani già inclusi
        new_pid = self._create_playlist_with_items(user_id, name, ids)
        return new_pid is not None