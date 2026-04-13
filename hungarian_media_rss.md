# Hungarian Media RSS Feeds

## Major independents / opposition-leaning

| Outlet | RSS URL |
|--------|---------|
| Telex | `https://telex.hu/rss` |
| 444 | `https://444.hu/feed` |
| HVG | `https://hvg.hu/rss/rss.hvg/hirek` |
| Népszava | `https://nepszava.hu/feed` *(verify)* |

> **444 tip:** append `/feed` to any tag, author, or category URL for a filtered feed.

## Large portals / mixed

| Outlet | RSS URL |
|--------|---------|
| Index | `https://index.hu/24ora/rss` |
| Index (all sections) | `https://index.hu/24ora/rss?&rovatkeres=osszes` |
| 24.hu | `https://24.hu/feed/` *(verify)* |
| Origo (main) | `https://www.origo.hu/contentpartner/rss/hircentrum/origo.xml` |
| Origo – Itthon | `https://www.origo.hu/contentpartner/rss/itthon/origo.rss` |
| Origo – Tudomány | `https://www.origo.hu/contentpartner/rss/tudomany/origo.rss` |
| Origo – Sport | `https://www.origo.hu/contentpartner/rss/sport/origo.rss` |
| Origo – Tech | `https://www.origo.hu/contentpartner/rss/techbazis/origo.rss` |

## Business / economics

| Outlet | RSS URL |
|--------|---------|
| Világgazdaság (VG) | `https://vg.hu/feed` *(verify)* |
| Portfolio | `https://www.portfolio.hu/rss/all.xml` *(verify)* |
| G7 | `https://g7.hu/feed/` *(verify)* |

## Government-aligned / right-leaning

| Outlet | RSS URL |
|--------|---------|
| Magyar Nemzet | `https://magyarnemzet.hu/feed/` *(verify)* |
| Mandiner | `https://mandiner.hu/rss` *(verify)* |
| 168.hu | `https://168.hu/feed` *(verify)* |

## English-language

| Outlet | RSS URL |
|--------|---------|
| Hungary Today | `https://hungarytoday.hu/feed` |
| Budapest Times | `https://budapesttimes.hu/feed` |

---

*Items marked (verify) follow standard conventions but were not confirmed from primary sources. Quick check:*

```bash
curl -sI <url> | head
# look for Content-Type: application/rss+xml or text/xml
```
