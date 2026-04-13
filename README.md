# Tisza Tracker

Hungarian government promise tracker. Monitors daily media coverage via RSS feeds, ranks articles by relevance using semantic similarity, and links them to specific campaign promises made by the Tisza party.

## Pipeline

```
tt filter   →  tt rank   →  tt fetch   →  tt match   →  tt html / tt email
  (RSS)       (scoring)    (full text)   (promises)     (output)
```

- **filter** — fetch RSS feeds, apply per-topic regex patterns to title + summary
- **rank** — compute semantic similarity (Sentence-Transformers) between topic query and article titles
- **fetch** — store RSS summaries for all ranked entries; download full article text (via trafilatura) for entries above `fetch_threshold`
- **match** — link articles to government promises using per-promise regex pre-filter + semantic scoring against title + summary
- **html / email** — generate HTML reports or send digests via SMTP

## Databases

- `all_feed_entries.db` — global RSS archive for deduplication
- `papers.db` — current run processing (filter → rank → match)
- `matched_entries_history.db` — long-term archive of matched articles
- `article_text.db` — extracted article body text (separate to keep main DBs lean)
- `promises.db` — promise definitions, status tracking, article-promise links

## Configuration

Main config: `config.yaml` (feeds, defaults, database paths)

Topic configs: `topics/*.yaml` (per-topic regex patterns, ranking queries, feed selection)

Promise configs: `promises/*.yaml` (per-promise regex filter + semantic ranking query)

### Key defaults

- `rank_threshold: 0.25` — minimum score to display in output
- `fetch_threshold: 0.40` — minimum score to download full article text
- `ranking_negative_penalty: 0.20` — penalty for negative query terms (sport, weather, celebrity)
- `time_window_days: 30` — RSS entry age filter

## RSS feeds

13 active Hungarian media sources across the political spectrum:

- Independent / opposition-leaning: Telex, 444.hu, HVG, Nepszava
- Large portals: Index, 24.hu, Hirado.hu
- Business: Portfolio, Vilaggazdasag
- Right-leaning: Magyar Nemzet, Mandiner, 168.hu
- English-language: Hungary Today, Budapest Times

## Promise tracking

148 promises extracted from the Tisza party election programme ("A mukodo es embersages Magyarorszag alapjai", 2026), organized into 10 policy categories mapped to monitoring topics.

Each promise has a `filter_pattern` (regex for fast pre-filtering against title + summary) and a `ranking_query` (semantic similarity query for scoring).

### Promise categories

| File | Topic | Count | Covers |
|---|---|---|---|
| `altalanos.yaml` | altalanos | 17 | public administration, defence, migration, demographics, digital/AI |
| `gazdasag.yaml` | gazdasag | 22 | economy, tax policy, budget, agriculture |
| `egeszsegugy.yaml` | egeszsegugy | 9 | healthcare |
| `igazsagszolgaltatas.yaml` | igazsagszolgaltatas | 13 | rule of law, justice, civil society |
| `kornyezetvedelem.yaml` | kornyezetvedelem | 17 | environment, waste, water, animal welfare, rural development |
| `korrupcio.yaml` | korrupcio | 8 | anti-corruption, transparency |
| `kozlekedes.yaml` | kozlekedes | 23 | transport, energy, housing |
| `kulpolitika.yaml` | kulpolitika | 5 | foreign policy |
| `oktatas.yaml` | oktatas | 12 | education, culture |
| `szocialis.yaml` | szocialis | 22 | pensions, child protection, family policy, women's/Roma equality |

### Promise status lifecycle

`made` → `in_progress` → `kept` / `broken` / `partially_kept` / `abandoned` / `modified`

Status changes are tracked with timestamps and evidence in an audit trail.

## CLI reference

```
tt filter   [--topic NAME] [--json]
tt rank     [--topic NAME] [--json]
tt fetch    [--topic NAME] [--threshold 0.4] [--force] [--json]
tt match    [--topic NAME] [--threshold 0.3] [--json]
tt html     [--topic NAME]
tt email    [--topic NAME] [--mode auto|ranked] [--dry-run]
tt query    [--history|--all-feeds] [--search TERM] [--fuzzy TERM] [--min-rank 0.3] [--since DATE] [--json]
tt purge    [--days N | --all]
tt export-recent [--days 60]
tt status   [--json]
tt config   show | get KEY | set KEY VALUE | validate
tt topic    list | show NAME | add NAME
tt promise  list | show ID | sync | status ID STATUS | link ID ENTRY_ID | stats
```

## Tech stack

- Python 3.10+
- SQLite (5 databases, FTS5 trigram + keyword indexes)
- Sentence-Transformers (paraphrase-multilingual-MiniLM-L12-v2)
- feedparser, trafilatura, requests, Click, PyYAML

## Setup

```
pip install -e .
tt status
```
