#!/usr/bin/env python3
"""
Générateur de flux RSS personnalisé pour une émission/balado OHdio
de Radio-Canada, pour écoute dans Pocket Casts et cie.

  1. lit la page OHdio de l'émission et en extrait la liste des épisodes
     (données structurées JSON-LD de la page) ;
  2. pour chaque épisode, récupère titre, date, durée, résumé et mediaId ;
  3. résout l'URL audio directe via l'API publique de validation de
     Radio-Canada (services.radio-canada.ca) — l'audio reste hébergé
     par Radio-Canada, rien n'est recopié ;
  4. écrit un flux RSS 2.0 + iTunes valide.

Usage :
  python3 generate_feed.py --series-url <URL OHdio> --out feed.xml
      [--limit 30] [--min-duration 600] [--feed-url <URL publique du flux>]
      [--title "..."] [--cover <URL image>]
"""
import argparse, concurrent.futures, html, json, re, sys, time, urllib.request
from datetime import datetime, timezone
from email.utils import format_datetime
from xml.sax.saxutils import escape

VALIDATION = "https://services.radio-canada.ca/media/validation/v2/?appCode=medianet&idMedia={mid}&output=json"

def fetch(url, timeout=30):
    last = None
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8", "ignore")
        except Exception as e:
            last = e; time.sleep(2 * (attempt + 1))
    raise last

def fetch_json(url):
    return json.loads(fetch(url))

def head_length(url):
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.headers.get("Content-Length", "0")

def series_data(series_url):
    page = fetch(series_url)
    m = re.search(r'<script id=JSONLDCONTENT[^>]*>(.*?)</script>', page, re.S)
    if not m:
        raise RuntimeError("JSON-LD introuvable sur la page de l'émission")
    data = json.loads(m.group(1))
    for g in data["@graph"]:
        eps = g.get("episode")
        if eps:
            img = g.get("image") or {}
            if isinstance(img, dict): img = img.get("url", "")
            return {
                "title": g.get("name", ""),
                "description": g.get("description", ""),
                "image": img,
                "episode_urls": [e["@id"].replace("#episode", "") for e in eps],
            }
    raise RuntimeError("Aucune liste d'épisodes trouvée sur la page")

def square_cover(image_url):
    """Essaie la variante carrée (1x1) du visuel, sinon garde l'originale."""
    if "/16x9/" in image_url:
        cand = image_url.replace("/16x9/", "/1x1/")
        try:
            req = urllib.request.Request(cand, method="HEAD", headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=15) as r:
                if r.status == 200:
                    return cand
        except Exception:
            pass
    return image_url

def episode_info(url):
    d = fetch(url)
    title = re.search(r'"share":\{"title":"([^"]+)"', d)
    dur = re.search(r'"durationInSeconds":(\d+)', d)
    mid = re.search(r'"mediaId":"(\d+)"', d)
    date = re.search(r'"broadcastedFirstTimeAt":"([^"]+)"', d)
    if not (title and dur and mid and date):
        return None
    summary = ""
    sm = re.search(r'"summary":"((?:[^"\\]|\\.)*)"', d)
    if sm:
        try:
            summary = html.unescape(re.sub(r"<[^>]+>", "", json.loads(f'"{sm.group(1)}"'))).strip()
        except Exception:
            summary = ""
    epnum = re.search(r'"title":"Épisode (\d+) -', d)
    return {
        "url": url,
        "title": re.sub(r"<[^>]+>", "", html.unescape(title.group(1))).strip(),
        "duration": int(dur.group(1)),
        "media_id": mid.group(1),
        "datetime": date.group(1),
        "summary": summary,
        "episode_number": epnum.group(1) if epnum else None,
    }

def resolve_audio(ep):
    data = fetch_json(VALIDATION.format(mid=ep["media_id"]))
    audio_url = data.get("url")
    if not audio_url:
        return None
    ep["audio_url"] = audio_url
    ep["length"] = head_length(audio_url)
    return ep

def rfc822(iso):
    dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)
    return format_datetime(dt.astimezone(timezone.utc))

def fmt_duration(sec):
    return f"{sec // 3600:02d}:{(sec % 3600) // 60:02d}:{sec % 60:02d}"

def build_feed(series, episodes, feed_url=""):
    now = format_datetime(datetime.now(timezone.utc))
    title = series["title"]
    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd" '
           'xmlns:atom="http://www.w3.org/2005/Atom" xmlns:content="http://purl.org/rss/1.0/modules/content/">',
           "<channel>",
           f"<title>{escape(title)} — flux personnalisé</title>",
           f"<link>{escape(series['url'])}</link>",
           "<language>fr-ca</language>",
           f"<description>{escape(series['description'])}</description>",
           "<copyright>© ICI Radio-Canada — audio hébergé par Radio-Canada, flux généré pour usage personnel</copyright>",
           f"<lastBuildDate>{now}</lastBuildDate>",
           "<itunes:author>Radio-Canada</itunes:author>",
           "<itunes:owner><itunes:name>ICI Radio-Canada</itunes:name></itunes:owner>",
           f'<itunes:image href="{escape(series["image"])}"/>',
           "<itunes:explicit>no</itunes:explicit>",
           '<itunes:category text="Society &amp; Culture"/>',
           f"<image><url>{escape(series['image'])}</url><title>{escape(title)}</title><link>{escape(series['url'])}</link></image>"]
    if feed_url:
        out.append(f'<atom:link href="{escape(feed_url)}" rel="self" type="application/rss+xml"/>')
    for ep in episodes:
        guid = ep["url"].rstrip("/").split("/")[-2] if "/" in ep["url"] else ep["media_id"]
        out += ["<item>",
                f"<title>{escape(ep['title'])}</title>",
                f"<link>{escape(ep['url'])}</link>",
                f'<guid isPermaLink="false">ohdio-{guid}</guid>',
                f"<pubDate>{rfc822(ep['datetime'])}</pubDate>",
                f"<description>{escape(ep['summary'])}</description>",
                f"<content:encoded><![CDATA[<p>{escape(ep['summary'])}</p><p>Épisode publié sur OHdio : <a href=\"{escape(ep['url'])}\">{escape(ep['url'])}</a></p>]]></content:encoded>",
                f'<enclosure url="{escape(ep["audio_url"])}" length="{ep["length"]}" type="audio/mp4"/>',
                f"<itunes:duration>{fmt_duration(ep['duration'])}</itunes:duration>",
                "<itunes:author>Radio-Canada</itunes:author>",
                "<itunes:explicit>no</itunes:explicit>"]
        if ep.get("episode_number"):
            out.append(f"<itunes:episode>{ep['episode_number']}</itunes:episode>")
        out.append("</item>")
    out += ["</channel>", "</rss>", ""]
    return "\n".join(out)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--series-url", required=True)
    ap.add_argument("--out", default="feed.xml")
    ap.add_argument("--limit", type=int, default=30)
    ap.add_argument("--min-duration", type=int, default=600)
    ap.add_argument("--feed-url", default="")
    ap.add_argument("--title", default="")
    ap.add_argument("--cover", default="")
    args = ap.parse_args()

    series = series_data(args.series_url)
    series["url"] = args.series_url
    if args.title: series["title"] = args.title
    series["image"] = args.cover or square_cover(series["image"])
    print(f"{series['title']} : {len(series['episode_urls'])} épisodes listés sur OHdio", file=sys.stderr)
    with concurrent.futures.ThreadPoolExecutor(8) as ex:
        infos = [i for i in ex.map(episode_info, series["episode_urls"]) if i]
    infos = [i for i in infos if i["duration"] >= args.min_duration][: args.limit]
    print(f"{len(infos)} épisodes retenus (durée >= {args.min_duration} s)", file=sys.stderr)
    with concurrent.futures.ThreadPoolExecutor(8) as ex:
        episodes = [e for e in ex.map(resolve_audio, infos) if e]
    episodes.sort(key=lambda e: e["datetime"], reverse=True)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(build_feed(series, episodes, args.feed_url))
    print(f"Flux écrit dans {args.out} : {len(episodes)} épisodes", file=sys.stderr)
    for e in episodes:
        print(f"  {e['datetime'][:10]}  {e['duration']//60} min  {e['title']}", file=sys.stderr)

if __name__ == "__main__":
    main()
