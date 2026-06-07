# chesscom_repository.py

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterator, Optional
import time

import requests


@dataclass(frozen=True)
class ChessComGameArchive:
    year: int
    month: int
    url: str


class ChessComRepository:
    """
    Small read-only Chess.com PubAPI client for one username.

    Chess.com PubAPI is public, free, read-only, and requires no API key.
    It exposes public player data, stats, and game archives.
    """

    BASE_URL = "https://api.chess.com/pub"

    def __init__(
        self,
        username: str,
        *,
        timeout_seconds: float = 15.0,
        sleep_between_requests: float = 0.25,
        user_agent: str = "chess-insighter/0.1 contact: your-email@example.com",
    ):
        self.username = username.lower().strip()
        self.timeout_seconds = timeout_seconds
        self.sleep_between_requests = sleep_between_requests

        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": user_agent,
                "Accept": "application/json",
            }
        )

    def _get_json(self, path_or_url: str) -> dict[str, Any]:
        url = self._to_url(path_or_url)

        response = self.session.get(url, timeout=self.timeout_seconds)
        self._handle_response_error(response)

        time.sleep(self.sleep_between_requests)
        return response.json()

    def _get_text(self, path_or_url: str) -> str:
        url = self._to_url(path_or_url)

        response = self.session.get(url, timeout=self.timeout_seconds)
        self._handle_response_error(response)

        time.sleep(self.sleep_between_requests)
        return response.text

    def _to_url(self, path_or_url: str) -> str:
        if path_or_url.startswith("http://") or path_or_url.startswith("https://"):
            return path_or_url

        if not path_or_url.startswith("/"):
            path_or_url = "/" + path_or_url

        return self.BASE_URL + path_or_url

    @staticmethod
    def _handle_response_error(response: requests.Response) -> None:
        if response.status_code == 404:
            raise ValueError("Resource not found. Check username or archive date.")

        if response.status_code == 429:
            raise RuntimeError("Rate limited by Chess.com API. Retry later or slow down requests.")

        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise RuntimeError(
                f"Chess.com API error {response.status_code}: {response.text[:500]}"
            ) from exc

    # ---------------------------------------------------------------------
    # Player profile / stats
    # ---------------------------------------------------------------------

    def get_profile(self) -> dict[str, Any]:
        return self._get_json(f"/player/{self.username}")

    def get_stats(self) -> dict[str, Any]:
        return self._get_json(f"/player/{self.username}/stats")

    def get_clubs(self) -> dict[str, Any]:
        return self._get_json(f"/player/{self.username}/clubs")

    def get_tournaments(self) -> dict[str, Any]:
        return self._get_json(f"/player/{self.username}/tournaments")

    # ---------------------------------------------------------------------
    # Game archives
    # ---------------------------------------------------------------------

    def get_archive_urls(self) -> list[str]:
        data = self._get_json(f"/player/{self.username}/games/archives")
        return data.get("archives", [])

    def get_archives(self) -> list[ChessComGameArchive]:
        archives: list[ChessComGameArchive] = []

        for url in self.get_archive_urls():
            # Example:
            # https://api.chess.com/pub/player/erik/games/2024/06
            parts = url.rstrip("/").split("/")
            year = int(parts[-2])
            month = int(parts[-1])

            archives.append(
                ChessComGameArchive(
                    year=year,
                    month=month,
                    url=url,
                )
            )

        return archives

    def get_month_games(self, year: int, month: int) -> list[dict[str, Any]]:
        data = self._get_json(
            f"/player/{self.username}/games/{year:04d}/{month:02d}"
        )
        return data.get("games", [])

    def get_month_pgn(self, year: int, month: int) -> str:
        return self._get_text(
            f"/player/{self.username}/games/{year:04d}/{month:02d}/pgn"
        )

    def iter_all_games(
        self,
        *,
        since_year: Optional[int] = None,
        since_month: Optional[int] = None,
        until_year: Optional[int] = None,
        until_month: Optional[int] = None,
    ) -> Iterator[dict[str, Any]]:
        for archive in self.get_archives():
            if not self._archive_in_range(
                archive,
                since_year=since_year,
                since_month=since_month,
                until_year=until_year,
                until_month=until_month,
            ):
                continue

            yield from self.get_month_games(archive.year, archive.month)

    def iter_all_month_pgns(
        self,
        *,
        since_year: Optional[int] = None,
        since_month: Optional[int] = None,
        until_year: Optional[int] = None,
        until_month: Optional[int] = None,
    ) -> Iterator[tuple[ChessComGameArchive, str]]:
        for archive in self.get_archives():
            if not self._archive_in_range(
                archive,
                since_year=since_year,
                since_month=since_month,
                until_year=until_year,
                until_month=until_month,
            ):
                continue

            yield archive, self.get_month_pgn(archive.year, archive.month)

    @staticmethod
    def _archive_in_range(
        archive: ChessComGameArchive,
        *,
        since_year: Optional[int],
        since_month: Optional[int],
        until_year: Optional[int],
        until_month: Optional[int],
    ) -> bool:
        archive_key = archive.year * 100 + archive.month

        if since_year is not None:
            if since_month is None:
                since_month = 1
            since_key = since_year * 100 + since_month

            if archive_key < since_key:
                return False

        if until_year is not None:
            if until_month is None:
                until_month = 12
            until_key = until_year * 100 + until_month

            if archive_key > until_key:
                return False

        return True