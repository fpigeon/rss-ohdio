#!/usr/bin/env python3
"""
Flux RSS personnalisé pour « La journée (est encore jeune) » (Radio-Canada OHdio).

Le flux officiel externe de Radio-Canada ne contient qu'une sélection
d'épisodes (environ 1 par semaine). Ce script construit un flux complet
à partir de la liste quotidienne publiée sur OHdio :
  1. lit la page de l'émission et en extrait la liste des épisodes ;
  2. pour chaque épisode, récupère titre, date, durée, résumé et mediaId ;
  3. résout l'URL audio directe via l'API publique de validation de
     Radio-Canada (services.radio-canada.ca) — l'audio reste hébergé
     par Radio-Canada, rien n'est recopié ;
  4. écrit un flux RSS 2.0 + iTunes valide pour Pocket Casts et cie.

Usage : python3 generate_feed.py [--limit 30] [--out feed.xml]
"""
import argparse, concurrent.futures, html, json, re, sys, urllib.request
from datetime import datetime, time, timedelta, timezone
from email.utils import format_datetime
from xml.sax.saxutils import escape

SERIES_URL = "https://ici.radio-canada.ca/ohdio/balados/9887/la-journee-est-encore-jeune"
SERIES_TITLE = "La journée (est encore jeune)"
SERIES_DESC = ("Jean-Philippe Wauthier et ses complices, dont le bel Olivier Niquet, "
               "passent l'actualité dans le tordeur, avec l'esprit mordant et affûté "
               "qu'on leur connaît. Évidemment, Jean-Sébastien Girard y fait quelques "
               "saucettes. Les fans de l'émission culte La soirée est (encore) jeune en "
               "retrouveront l'énergie, le plaisir et le côté juste assez piquant.")
COVER = ("https://images.radio-canada.ca/w_1400,h_1400/v1/audio/partenaire-externe/1x1/"
         "la-journee-est-encore-jeune-visuel-partenaire-externe.jpg")
VALIDATION = "https://services.radio-canada.ca/media/validation/v2/?appCode=medianet&idMedia={mid}&output=json"
TORONTO = timezone(timedelta(hours=-5), "EST")  # les dates du flux officiel sont en heure de l'Est
MIN_DURATION = 1200  # secondes : exclut les courts segments, garde les épisodes complets

def fetch(url, timeout=30):
    import time as _time
    last = None
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8", "ignore")
        except Exception as e:
            last = e; _time.sleep(2 * (attempt + 1))
    raise last

def fetch_json(url):
    return json.loads(fetch(url))

def episode_urls():
    page = fetch(SERIES_URL)
    m = re.search(r'<script id=JSONLDCONTENT[^>]*>(.*?)</script>', page, re.S)
    data = json.loads(m.group(1))
    series = [g for g in data["@graph"] if g.get("@type") == "PodcastSeries"][0]
    return [e["@id"].replace("#episode", "") for e in series["episode"]]

def episode_info(url):
    d = fetch(url)
    title = re.search(r'"share":\{"title":"([^"]+)"', d)
    dur = re.search(r'"durationInSeconds":(\d+)', d)
    mid = re.search(r'"mediaId":"(\d+)"', d)
    date = re.search(r'"broadcastedFirstTimeAt":"([^"]+)"', d)
    summ = re.search(r'"broadcastedFirstTimeAt":"[^"]+","credits":"(?:[^"\\]|\\.)*","hasTranscription":(?:true|false),"isBroadcastedReplay":(?:true|false),"sponsoredContentWarning":null,"summary":"((?:[^"\\]|\\.)*)"', d)
    epnum = re.search(r'"title":"Épisode (\d+) -', d)
    if not (title and dur and mid and date):
        return None
    summary = ""
    if summ:
        summary = json.loads(f'"{summ.group(1)}"')
        summary = html.unescape(re.sub(r"<[^>]+>", "", summary)).strip()
    return {
        "url": url,
        "title": html.unescape(title.group(1)).strip(),
        "duration": int(dur.group(1)),
        "media_id": mid.group(1),
        "date": date.group(1)[:10],
        "summary": summary,
        "episode_number": epnum.group(1) if epnum else None,
    }

def resolve_audio(ep):
    data = fetch_json(VALIDATION.format(mid=ep["media_id"]))
    audio_url = data.get("url")
    if not audio_url:
        return None
    ep["audio_url"] = audio_url
    # taille du fichier (en-tête seulement)
    req = urllib.request.Request(audio_url, method="HEAD", headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        ep["length"] = r.headers.get("Content-Length", "0")
    return ep

def rfc822(date_str):
    d = datetime.combine(datetime.fromisoformat(date_str).date(), time(14, 30), tzinfo=TORONTO)
    return format_datetime(d)

def fmt_duration(sec):
    return f"{sec // 3600:02d}:{(sec % 3600) // 60:02d}:{sec % 60:02d}"

def build_feed(episodes, feed_url=""):
    now = format_datetime(datetime.now(timezone.utc))
    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd" '
           'xmlns:atom="http://www.w3.org/2005/Atom" xmlns:content="http://purl.org/rss/1.0/modules/content/">',
           "<channel>",
           f"<title>{escape(SERIES_TITLE)} — flux personnalisé (quotidien)</title>",
           f"<link>{SERIES_URL}</link>",
           "<language>fr-ca</language>",
           f"<description>{escape(SERIES_DESC)}</description>",
           "<copyright>© ICI Radio-Canada — audio hébergé par Radio-Canada, flux généré pour usage personnel</copyright>",
           f"<lastBuildDate>{now}</lastBuildDate>",
           "<itunes:author>Radio-Canada</itunes:author>",
           "<itunes:owner><itunes:name>ICI Radio-Canada</itunes:name></itunes:owner>",
           f'<itunes:image href="{COVER}"/>',
           "<itunes:explicit>no</itunes:explicit>",
           '<itunes:category text="Society &amp; Culture"/>',
           f"<image><url>{COVER}</url><title>{escape(SERIES_TITLE)}</title><link>{SERIES_URL}</link></image>"]
    if feed_url:
        out.append(f'<atom:link href="{escape(feed_url)}" rel="self" type="application/rss+xml"/>')
    for ep in episodes:
        out += ["<item>",
                f"<title>{escape(ep['title'])}</title>",
                f"<link>{escape(ep['url'])}</link>",
                f'<guid isPermaLink="false">ohdio-9887-{ep["url"].split("/")[-2]}</guid>',
                f"<pubDate>{rfc822(ep['date'])}</pubDate>",
                f"<description>{escape(ep['summary'])}</description>",
                f"<content:encoded><![CDATA[<p>{escape(ep['summary'])}</p><p>Épisode diffusé sur ICI Première et publié sur OHdio : <a href=\"{escape(ep['url'])}\">{escape(ep['url'])}</a></p>]]></content:encoded>",
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
    ap.add_argument("--limit", type=int, default=30)
    ap.add_argument("--out", default="feed.xml")
    ap.add_argument("--feed-url", default="")
    args = ap.parse_args()

    urls = episode_urls()
    print(f"{len(urls)} épisodes listés sur OHdio", file=sys.stderr)
    with concurrent.futures.ThreadPoolExecutor(8) as ex:
        infos = [i for i in ex.map(episode_info, urls) if i]
    infos = [i for i in infos if i["duration"] >= MIN_DURATION][: args.limit]
    print(f"{len(infos)} épisodes complets retenus", file=sys.stderr)
    with concurrent.futures.ThreadPoolExecutor(8) as ex:
        episodes = [e for e in ex.map(resolve_audio, infos) if e]
    episodes.sort(key=lambda e: e["date"], reverse=True)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(build_feed(episodes, args.feed_url))
    print(f"Flux écrit dans {args.out} : {len(episodes)} épisodes", file=sys.stderr)
    for e in episodes:
        print(f"  {e['date']}  {e['title']}", file=sys.stderr)

if __name__ == "__main__":
    main()
