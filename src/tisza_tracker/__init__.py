from __future__ import annotations

import logging
from importlib.metadata import version as _get_version, PackageNotFoundError
from typing import Optional

try:
    __version__ = _get_version("tisza_tracker")
except PackageNotFoundError:
    __version__ = "0.0.0.dev"

from .commands import filter as filter_cmd
from .commands import rank as rank_cmd
from .commands import export_recent as export_recent_cmd
from .commands import query as query_cmd
from .core.config import DEFAULT_CONFIG_PATH

logger = logging.getLogger(__name__)

_DEFAULT_CONFIG = str(DEFAULT_CONFIG_PATH)

__all__ = [
    '__version__',
    'filter',
    'rank',
    'purge',
    'export_recent',
    'query',
]


def filter(topic: Optional[str] = None, config_path: Optional[str] = None) -> None:
    """Run the filter step programmatically."""
    cfg_path = config_path or _DEFAULT_CONFIG
    filter_cmd.run(cfg_path, topic)


def rank(topic: Optional[str] = None, config_path: Optional[str] = None) -> None:
    """Compute and write rank scores into papers.db for the given topic (or all)."""
    cfg_path = config_path or _DEFAULT_CONFIG
    rank_cmd.run(cfg_path, topic)


def export_recent(days: int = 60, output_name: Optional[str] = None, config_path: Optional[str] = None) -> None:
    """Export recent entries from matched_entries_history.db to a smaller database."""
    cfg_path = config_path or _DEFAULT_CONFIG
    export_recent_cmd.run(cfg_path, days, output_name)


def query(
    *,
    history: bool = False,
    all_feeds: bool = False,
    topic: Optional[str] = None,
    min_rank: Optional[float] = None,
    since: Optional[str] = None,
    until: Optional[str] = None,
    search: Optional[str] = None,
    status: Optional[str] = None,
    has_abstract: bool = False,
    sort: str = 'rank',
    limit: int = 20,
    offset: int = 0,
    json: bool = False,
    count: bool = False,
    fields: Optional[str] = None,
    config_path: Optional[str] = None,
) -> None:
    """Query article databases and print results."""
    if history and all_feeds:
        raise ValueError("Cannot use both history and all_feeds")
    db_key = 'history' if history else ('all_feeds' if all_feeds else 'current')
    cfg_path = config_path or _DEFAULT_CONFIG
    query_cmd.run(cfg_path, db_key=db_key, topic=topic, min_rank=min_rank, status=status,
                  has_doi=False, has_abstract=has_abstract, since=since, until=until,
                  search=search, sort=sort, limit=limit, offset=offset,
                  output_json=json, count_only=count, fields=fields)


def purge(days: Optional[int] = None, all_data: bool = False, config_path: Optional[str] = None) -> None:
    """Purge entries from databases."""
    if days is None and not all_data:
        raise ValueError("Specify days or all_data=True")
    cfg_path = config_path or _DEFAULT_CONFIG
    filter_cmd.purge(cfg_path, days, all_data)
