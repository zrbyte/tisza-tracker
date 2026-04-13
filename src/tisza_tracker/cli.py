"""Command-line entry point for Tisza Tracker."""

from __future__ import annotations

import json
import logging
import os
import sys

import click

from . import __version__
from .commands import config_cmd
from .commands import email_list as email_cmd
from .commands import promise_cmd
from .commands import export_recent as export_recent_cmd
from .commands import filter as filter_cmd
from .commands import generate_html as html_cmd
from .commands import match as match_cmd
from .commands import query as query_cmd
from .commands import rank as rank_cmd
from .commands import status as status_cmd
from .commands import topic_cmd
from .core.config import ConfigManager, DEFAULT_CONFIG_PATH
from .core.exit_codes import ERR_CONFIG, ERR_RUNTIME, ERR_USAGE
from .core.paths import get_data_dir

# Setup logging early so submodules inherit sane defaults
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)


@click.group()
@click.version_option(version=__version__, prog_name="tisza-tracker")
@click.option(
    "--config",
    default=str(DEFAULT_CONFIG_PATH),
    show_default=True,
    help="Path to config file (defaults to data_dir/config/config.yaml)",
)
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose logging")
@click.pass_context
def cli(ctx: click.Context, config: str, verbose: bool) -> None:
    """Tisza Tracker - Hungarian government promise tracker via RSS media monitoring."""
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    ctx.ensure_object(dict)
    ctx.obj["config_path"] = config


@cli.command("filter")
@click.option("--topic", help="Filter specific topic only")
@click.option("--json", "output_json", is_flag=True, help="Output results as JSON")
@click.pass_context
def filter_feeds(ctx: click.Context, topic: str | None, output_json: bool) -> None:
    """Fetch RSS feeds and filter entries by regex patterns."""
    try:
        result = filter_cmd.run(ctx.obj["config_path"], topic, output_json=output_json)
        if output_json and result:
            click.echo(json.dumps(result, indent=2, default=str))
        else:
            click.echo("Filter command completed successfully")
    except ValueError as exc:
        click.echo(f"Filter command failed: {exc}", err=True)
        sys.exit(ERR_CONFIG)
    except Exception as exc:  # pragma: no cover
        click.echo(f"Filter command failed: {exc}", err=True)
        sys.exit(ERR_RUNTIME)


@cli.command("html")
@click.option("--topic", help="Generate HTML for a specific topic only")
@click.pass_context
def generate_html(ctx: click.Context, topic: str | None) -> None:
    """Generate topic HTML(s) directly from papers.db (no fetching)."""
    try:
        html_cmd.run(ctx.obj["config_path"], topic)
        if topic:
            click.echo(f"HTML generated for topic '{topic}'")
        else:
            click.echo("HTML generated for all topics")
    except Exception as exc:  # pragma: no cover
        click.echo(f"HTML generation failed: {exc}", err=True)
        sys.exit(ERR_RUNTIME)


@cli.command("export-recent")
@click.option("--days", default=60, type=click.IntRange(min=1), help="Number of days to include (default: 60)")
@click.option("--output", default=None, help="Output filename (default: matched_entries_history.recent.db)")
@click.pass_context
def export_recent(ctx: click.Context, days: int, output: str | None) -> None:
    """Export recent entries to a smaller database file for faster web loading."""
    try:
        export_recent_cmd.run(ctx.obj["config_path"], days, output)
        click.echo(f"Exported entries from last {days} days successfully")
    except Exception as exc:  # pragma: no cover
        click.echo(f"Export-recent command failed: {exc}", err=True)
        sys.exit(ERR_RUNTIME)


@cli.command("rank")
@click.option("--topic", help="Rank a specific topic only")
@click.option("--json", "output_json", is_flag=True, help="Output results as JSON")
@click.pass_context
def rank(ctx: click.Context, topic: str | None, output_json: bool) -> None:
    """Compute and write rank scores into papers.db (rank_score only)."""
    try:
        result = rank_cmd.run(ctx.obj["config_path"], topic, output_json=output_json)
        if output_json and result:
            click.echo(json.dumps(result, indent=2, default=str))
        else:
            if topic:
                click.echo(f"Ranking completed for topic '{topic}'")
            else:
                click.echo("Ranking completed for all topics")
    except ValueError as exc:
        click.echo(f"Rank command failed: {exc}", err=True)
        sys.exit(ERR_CONFIG)
    except Exception as exc:  # pragma: no cover
        click.echo(f"Rank command failed: {exc}", err=True)
        sys.exit(ERR_RUNTIME)


@cli.command("match")
@click.option("--topic", help="Match a specific topic only")
@click.option("--threshold", default=0.3, type=float, help="Minimum relevance score (default: 0.3)")
@click.option("--json", "output_json", is_flag=True, help="Output results as JSON")
@click.pass_context
def match(ctx: click.Context, topic: str | None, threshold: float, output_json: bool) -> None:
    """Match filtered articles to government promises by semantic similarity."""
    try:
        result = match_cmd.run(ctx.obj["config_path"], topic, threshold=threshold, output_json=output_json)
        if output_json and result:
            import json as _json
            click.echo(_json.dumps(result, indent=2, default=str))
        else:
            click.echo("Promise matching completed")
    except Exception as exc:
        click.echo(f"Promise matching failed: {exc}", err=True)
        sys.exit(ERR_RUNTIME)


@cli.command("email")
@click.option("--topic", help="Send for a specific topic only (default: all topics)")
@click.option(
    "--mode",
    type=click.Choice(["auto", "ranked"]),
    default="auto",
    help="Content mode: auto (from DB) or ranked (embed ranked HTML if available)",
)
@click.option("--limit", type=click.IntRange(min=1), help="Limit number of entries per topic")
@click.option(
    "--recipients",
    "recipients_file",
    type=str,
    help="Path to recipients YAML (overrides config.email.recipients_file)",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Do not send; write preview HTML under the runtime data directory",
)
@click.pass_context
def email(
    ctx: click.Context,
    topic: str | None,
    mode: str,
    limit: int | None,
    recipients_file: str | None,
    dry_run: bool,
) -> None:
    """Send an HTML digest email generated from papers.db via SMTP."""
    try:
        email_cmd.run(
            ctx.obj["config_path"],
            topic,
            mode=mode,
            limit=limit,
            dry_run=dry_run,
            recipients_file=recipients_file,
        )
        if dry_run:
            click.echo(f"Email dry-run completed (preview written under {get_data_dir()})")
        else:
            click.echo("Email sent successfully")
    except Exception as exc:  # pragma: no cover
        click.echo(f"Email send failed: {exc}", err=True)
        sys.exit(ERR_RUNTIME)


@cli.command("purge")
@click.option("--days", type=click.IntRange(min=1), help="Remove entries from the most recent DAYS days (including today)")
@click.option("--all", "all_data", is_flag=True, help="Clear all databases")
@click.pass_context
def purge(ctx: click.Context, days: int | None, all_data: bool) -> None:
    """Remove entries from databases based on publication date."""
    if not days and not all_data:
        click.echo("Error: Must specify either --days X or --all", err=True)
        sys.exit(ERR_USAGE)

    try:
        filter_cmd.purge(ctx.obj["config_path"], days, all_data)
        if all_data:
            click.echo("All data purged successfully")
        else:
            click.echo(f"Entries from the most recent {days} days purged successfully")
    except Exception as exc:  # pragma: no cover
        click.echo(f"Purge command failed: {exc}", err=True)
        sys.exit(ERR_RUNTIME)


@cli.command("query")
@click.option("--history", "db_key", flag_value="history", help="Query history database")
@click.option("--all-feeds", "db_key", flag_value="all_feeds", help="Query all-feeds database")
@click.option("--topic", help="Filter by topic")
@click.option("--min-rank", type=float, help="Minimum rank score")
@click.option("--since", help="Published on or after date (YYYY-MM-DD)")
@click.option("--until", help="Published on or before date (YYYY-MM-DD)")
@click.option("--search", help="Keyword search (supports phrases \"...\", prefix*, AND/OR/NOT)")
@click.option("--fuzzy", help="Fuzzy text search (trigram matching, min 3 chars)")
@click.option("--rerank", help="Rerank results by semantic similarity to this query")
@click.option("--status", "status_filter", help="Filter by status (current DB only)")
@click.option("--has-abstract", is_flag=True, help="Only entries with body text")
@click.option("--sort", default="rank", type=click.Choice(["rank", "date", "title"]),
              help="Sort order (default: rank)")
@click.option("--limit", default=20, type=int, help="Max results (0=unlimited)")
@click.option("--offset", default=0, type=int, help="Skip first N results")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
@click.option("--count", "count_only", is_flag=True, help="Print count only")
@click.option("--fields", help="Comma-separated field names to include")
@click.pass_context
def query(ctx: click.Context, db_key: str, topic: str, min_rank: float,
          since: str, until: str, search: str, fuzzy: str, rerank: str,
          status_filter: str,
          has_abstract: bool, sort: str, limit: int,
          offset: int, output_json: bool, count_only: bool, fields: str) -> None:
    """Query article databases for entries.

    Examples:

    \\b
      # Search history for healthcare articles
      tt query --history --search "korhaz" --rerank "egeszsegugyi reform"

    \\b
      # Top 10 from today's run
      tt query --limit 10

    \\b
      # Fuzzy search (typo-tolerant)
      tt query --history --fuzzy "korrupcio"

    \\b
      # JSON output for scripting
      tt query --history --search "Magyar Peter" --json --fields title,link,rank_score
    """
    try:
        query_cmd.run(
            ctx.obj["config_path"],
            db_key=db_key or "current",
            topic=topic,
            min_rank=min_rank,
            status=status_filter,
            has_doi=False,
            has_abstract=has_abstract,
            since=since,
            until=until,
            search=search,
            fuzzy=fuzzy,
            rerank=rerank,
            sort=sort,
            limit=limit,
            offset=offset,
            output_json=output_json,
            count_only=count_only,
            fields=fields,
        )
    except ValueError as exc:
        click.echo(f"{exc}", err=True)
        sys.exit(ERR_USAGE)
    except Exception as exc:  # pragma: no cover
        click.echo(f"Error: {exc}", err=True)
        sys.exit(ERR_RUNTIME)


@cli.command("status")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON.")
@click.pass_context
def status(ctx: click.Context, output_json: bool) -> None:
    """Show system status, configuration, and database freshness."""
    try:
        status_cmd.run(ctx.obj["config_path"], output_json=output_json)
    except Exception as exc:  # pragma: no cover
        click.echo(f"Error checking status: {exc}", err=True)
        sys.exit(ERR_RUNTIME)


# --- Config management ---

@cli.group("config")
def config_group() -> None:
    """View and modify Tisza Tracker configuration."""


@config_group.command("show")
@click.pass_context
def config_show(ctx: click.Context) -> None:
    """Pretty-print the main configuration."""
    try:
        click.echo(config_cmd.show(ctx.obj["config_path"]))
    except Exception as exc:
        click.echo(f"{exc}", err=True)
        sys.exit(ERR_RUNTIME)


@config_group.command("get")
@click.argument("key")
@click.pass_context
def config_get(ctx: click.Context, key: str) -> None:
    """Get a config value by dot-notation key (e.g. defaults.rank_threshold)."""
    try:
        value = config_cmd.get_value(ctx.obj["config_path"], key)
        click.echo(value)
    except KeyError as exc:
        click.echo(f"{exc}", err=True)
        sys.exit(ERR_USAGE)
    except Exception as exc:
        click.echo(f"{exc}", err=True)
        sys.exit(ERR_RUNTIME)


@config_group.command("set")
@click.argument("key")
@click.argument("value")
@click.pass_context
def config_set(ctx: click.Context, key: str, value: str) -> None:
    """Set a config value by dot-notation key (e.g. defaults.rank_threshold 0.25)."""
    try:
        config_cmd.set_value(ctx.obj["config_path"], key, value)
        click.echo(f"Set {key} = {config_cmd.get_value(ctx.obj['config_path'], key)}")
    except Exception as exc:
        click.echo(f"{exc}", err=True)
        sys.exit(ERR_RUNTIME)


@config_group.command("validate")
@click.pass_context
def config_validate(ctx: click.Context) -> None:
    """Run full configuration validation."""
    try:
        valid, unknown = config_cmd.validate(ctx.obj["config_path"])
        if valid:
            click.echo("Configuration is valid")
        else:
            click.echo("Configuration validation failed")
        if unknown:
            click.echo(f"Unknown keys: {', '.join(unknown)}")
        if not valid:
            sys.exit(ERR_CONFIG)
    except Exception as exc:
        click.echo(f"{exc}", err=True)
        sys.exit(ERR_RUNTIME)


# --- Topic management ---

@cli.group("topic")
def topic_group() -> None:
    """View and manage topic configurations."""


@topic_group.command("list")
@click.pass_context
def topic_list(ctx: click.Context) -> None:
    """List available topics."""
    try:
        topics = topic_cmd.list_topics(ctx.obj["config_path"])
        if not topics:
            click.echo("No topics configured.")
            return
        for t in topics:
            desc = f" -- {t['description']}" if t.get("description") else ""
            click.echo(f"  {t['key']}: {t['name']}{desc}")
    except Exception as exc:
        click.echo(f"{exc}", err=True)
        sys.exit(ERR_RUNTIME)


@topic_group.command("show")
@click.argument("name")
@click.pass_context
def topic_show(ctx: click.Context, name: str) -> None:
    """Pretty-print a topic configuration."""
    try:
        click.echo(topic_cmd.show_topic(ctx.obj["config_path"], name))
    except FileNotFoundError as exc:
        click.echo(f"{exc}", err=True)
        sys.exit(ERR_USAGE)
    except Exception as exc:
        click.echo(f"{exc}", err=True)
        sys.exit(ERR_RUNTIME)


@topic_group.command("add")
@click.argument("name")
@click.option("--from", "from_topic", default=None, help="Clone an existing topic")
@click.pass_context
def topic_add(ctx: click.Context, name: str, from_topic: str | None) -> None:
    """Create a new topic configuration."""
    try:
        path = topic_cmd.add_topic(
            ctx.obj["config_path"], name, from_topic=from_topic
        )
        click.echo(f"Created topic '{name}' at {path}")
    except ValueError as exc:
        click.echo(f"{exc}", err=True)
        sys.exit(ERR_USAGE)
    except Exception as exc:
        click.echo(f"{exc}", err=True)
        sys.exit(ERR_RUNTIME)


# --- Promise management ---

@cli.group("promise")
def promise_group() -> None:
    """Manage government promises and their tracking status."""


@promise_group.command("list")
@click.option("--category", help="Filter by policy category")
@click.option("--status", help="Filter by status (made/in_progress/kept/broken/partially_kept/abandoned/modified)")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
@click.pass_context
def promise_list(ctx: click.Context, category: str | None, status: str | None,
                 output_json: bool) -> None:
    """List tracked promises."""
    try:
        promise_cmd.list_promises(ctx.obj["config_path"], category, status, output_json)
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(ERR_RUNTIME)


@promise_group.command("show")
@click.argument("promise_id")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
@click.pass_context
def promise_show(ctx: click.Context, promise_id: str, output_json: bool) -> None:
    """Show details for a specific promise."""
    try:
        promise_cmd.show_promise(ctx.obj["config_path"], promise_id, output_json)
    except ValueError as exc:
        click.echo(f"{exc}", err=True)
        sys.exit(ERR_USAGE)
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(ERR_RUNTIME)


@promise_group.command("sync")
@click.pass_context
def promise_sync(ctx: click.Context) -> None:
    """Sync promise definitions from YAML files into the database."""
    try:
        result = promise_cmd.sync_promises(ctx.obj["config_path"])
        click.echo(f"Promise sync: {result['created']} created, {result['updated']} updated, {result['total']} total")
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(ERR_RUNTIME)


@promise_group.command("status")
@click.argument("promise_id")
@click.argument("new_status")
@click.option("--evidence", help="Evidence for the status change")
@click.option("--articles", help="Comma-separated article entry IDs as evidence")
@click.pass_context
def promise_status_update(ctx: click.Context, promise_id: str, new_status: str,
                          evidence: str | None, articles: str | None) -> None:
    """Update a promise's status (made/in_progress/kept/broken/partially_kept/abandoned/modified)."""
    try:
        article_ids = [a.strip() for a in articles.split(",")] if articles else None
        promise_cmd.update_status(ctx.obj["config_path"], promise_id, new_status,
                                  evidence=evidence, article_ids=article_ids)
        click.echo(f"Promise {promise_id} status updated to '{new_status}'")
    except ValueError as exc:
        click.echo(f"{exc}", err=True)
        sys.exit(ERR_USAGE)
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(ERR_RUNTIME)


@promise_group.command("link")
@click.argument("promise_id")
@click.argument("entry_id")
@click.option("--score", default=1.0, type=float, help="Relevance score (default: 1.0)")
@click.pass_context
def promise_link(ctx: click.Context, promise_id: str, entry_id: str, score: float) -> None:
    """Manually link an article to a promise."""
    try:
        promise_cmd.link_article(ctx.obj["config_path"], promise_id, entry_id, score)
        click.echo(f"Linked article {entry_id[:12]}... to promise {promise_id}")
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(ERR_RUNTIME)


@promise_group.command("stats")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
@click.pass_context
def promise_stats(ctx: click.Context, output_json: bool) -> None:
    """Show promise tracking statistics."""
    try:
        promise_cmd.stats(ctx.obj["config_path"], output_json)
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(ERR_RUNTIME)


if __name__ == "__main__":  # pragma: no cover - script entry
    cli()
