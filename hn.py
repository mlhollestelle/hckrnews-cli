#!/usr/bin/env python3
"""hn - skim the hckrnews.com "top 10" / "top 20" Hacker News headlines in the terminal.

Uses the same data and the same filter as hckrnews.com: for each day, a story is
shown if its points are at least those of the N-th best story of that day
(N scaled down for a day that is still in progress).

Keys:  ↑/↓ j/k move   enter/o open link   c open discussion   b open both
       t toggle top 10/20   ←/→ h/l or p/n previous/next day   r refresh   q quit
"""

import argparse
import curses
import datetime as dt
import html
import json
import math
import os
import re
import shutil
import subprocess
import sys
import urllib.request
import webbrowser

BASE = "https://hckrnews.com"
HN_ITEM = "https://news.ycombinator.com/item?id="
UA = "hckrnews-cli/1.0"


# ---------------------------------------------------------------- data

def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.read().decode("utf-8", "replace")


_LI = re.compile(r'<li class="entry row" id="(\d+)">(.*?)</li>', re.S)


def _parse_homepage(text):
    """The front page embeds the two most recent days as HTML."""
    days = {}
    for m in re.finditer(r'<ul class="entries[^"]*" id="(\d{8})">(.*?)</ul>', text, re.S):
        entries = []
        for li in _LI.finditer(m.group(2)):
            body = li.group(2)
            date = re.search(r'data-date="(\d+)"', body)
            pts = re.search(r'class="points[^"]*">\s*(\d*)', body)
            com = re.search(r'class="comments[^"]*">\s*(\d*)', body)
            link = re.search(r'<a class="link[^"]*" href="([^"]*)">(.*?)(?:<span class="source">\(([^)]*)\)</span>)?\s*</a>', body, re.S)
            if not link:
                continue
            entries.append({
                "id": li.group(1),
                "date": int(date.group(1)) if date else 0,
                "points": int(pts.group(1) or 0) if pts else 0,
                "comments": int(com.group(1) or 0) if com else 0,
                "link": html.unescape(link.group(1)),
                "link_text": html.unescape(re.sub(r"<[^>]+>", "", link.group(2))).strip(),
                "source": link.group(3) or "",
                "homepage": "homepage" in (re.search(r'class="(points[^"]*)"', body) or [None, ""])[1],
                "dead": bool(re.search(r'class="link[^"]*\bdead\b', body)),
            })
        days[m.group(1)] = entries
    return days


class Source:
    def __init__(self):
        self.cache = {}

    def refresh(self):
        self.cache = _parse_homepage(_get(BASE + "/"))

    def day(self, key):
        if key not in self.cache:
            try:
                raw = json.loads(_get(f"{BASE}/data/{key}.js"))
            except Exception:
                raw = []
            for e in raw:
                for f in ("points", "comments", "date"):
                    try:
                        e[f] = int(e.get(f) or 0)
                    except (TypeError, ValueError):
                        e[f] = 0
                e["link_text"] = html.unescape(e.get("link_text") or "")
            self.cache[key] = raw
        return self.cache[key]


def top(entries, n):
    """hckrnews' pointsAbove(): threshold = points of the k-th best story, where
    k = n scaled by how many hours of the day the entries span."""
    live = [e for e in entries if not e.get("dead")]
    if not live:
        return []
    dates = [e["date"] for e in live]
    hours = (max(dates) - min(dates)) // 3600
    k = max(1, math.ceil(hours / 24 * n))
    by_pts = sorted(live, key=lambda e: -e["points"])
    threshold = by_pts[min(k, len(by_pts)) - 1]["points"] or 1
    return [e for e in by_pts if e["points"] >= threshold]


def link_of(e):
    link = e.get("link")
    return link if link and link != "undefined" else HN_ITEM + e["id"]


# ---------------------------------------------------------------- browser

def open_url(url):
    """Open in the default browser; on WSL hand the URL to Windows."""
    is_wsl = "microsoft" in os.uname().release.lower()
    try:
        if is_wsl:
            for cmd in (["wslview", url], ["rundll32.exe", "url.dll,FileProtocolHandler", url]):
                if shutil.which(cmd[0]):
                    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    return
        if shutil.which("xdg-open") and not sys.platform == "darwin":
            subprocess.Popen(["xdg-open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             start_new_session=True)
            return
        webbrowser.open(url)
    except Exception:
        webbrowser.open(url)


# ---------------------------------------------------------------- UI

def day_label(key):
    d = dt.datetime.strptime(key, "%Y%m%d").date()
    today = dt.datetime.now(dt.timezone.utc).date()
    rel = {0: "today", 1: "yesterday"}.get((today - d).days)
    return d.strftime("%a %d %b %Y") + (f" ({rel})" if rel else "")


def run_tui(stdscr, src, n, day_key):
    curses.curs_set(0)
    curses.use_default_colors()
    for i, c in enumerate((curses.COLOR_YELLOW, curses.COLOR_CYAN, 8 if curses.COLORS > 8 else curses.COLOR_WHITE), 1):
        curses.init_pair(i, c, -1)
    YEL, CYAN, DIM = (curses.color_pair(i) for i in (1, 2, 3))

    sel, scroll, msg = 0, 0, ""
    while True:
        items = top(src.day(day_key), n)
        sel = max(0, min(sel, len(items) - 1))
        h, w = stdscr.getmaxyx()
        stdscr.erase()
        head = f" HN top {n} · {day_label(day_key)} · {len(items)} stories "
        stdscr.addnstr(0, 0, head.ljust(w), w, curses.A_REVERSE | curses.A_BOLD)

        rows = h - 3
        if sel < scroll:
            scroll = sel
        elif sel >= scroll + rows:
            scroll = sel - rows + 1
        if not items:
            stdscr.addnstr(2, 2, "No stories for this day.", w - 3, DIM)
        for i, e in enumerate(items[scroll:scroll + rows]):
            idx = scroll + i
            y = 1 + i
            attr = curses.A_REVERSE if idx == sel else 0
            stdscr.addnstr(y, 0, " " * w, w, attr)
            col = 0
            stdscr.addnstr(y, col, f"{e['points']:>5} ", w, attr | YEL | curses.A_BOLD); col += 6
            stdscr.addnstr(y, col, f"{e['comments']:>4}  ", max(0, w - col), attr | CYAN); col += 6
            title = e["link_text"]
            stdscr.addnstr(y, col, title, max(0, w - col - 1), attr | (curses.A_BOLD if e.get("homepage") else 0))
            col += len(title) + 1
            if e.get("source") and col < w - 2:
                stdscr.addnstr(y, col, f"({e['source']})", max(0, w - col - 1), attr | DIM)

        help_ = " ↑↓ move  ⏎/o link  c discussion  b both  t top10/20  ←→ day  r refresh  q quit "
        stdscr.addnstr(h - 2, 0, (msg or "").ljust(w), w - 1, DIM)
        stdscr.addnstr(h - 1, 0, help_.ljust(w), w - 1, curses.A_REVERSE)
        stdscr.refresh()
        msg = ""

        k = stdscr.getch()
        cur = items[sel] if items else None
        if k in (ord("q"), 27):
            return
        elif k in (curses.KEY_DOWN, ord("j")):
            sel += 1
        elif k in (curses.KEY_UP, ord("k")):
            sel -= 1
        elif k in (curses.KEY_NPAGE, ord(" ")):
            sel += rows
        elif k == curses.KEY_PPAGE:
            sel -= rows
        elif k in (curses.KEY_HOME, ord("g")):
            sel = 0
        elif k in (curses.KEY_END, ord("G")):
            sel = len(items) - 1
        elif k in (10, 13, curses.KEY_ENTER, ord("o")) and cur:
            open_url(link_of(cur)); msg = "Opened " + link_of(cur)
        elif k == ord("c") and cur:
            open_url(HN_ITEM + cur["id"]); msg = "Opened discussion"
        elif k == ord("b") and cur:
            open_url(HN_ITEM + cur["id"]); open_url(link_of(cur)); msg = "Opened link + discussion"
        elif k == ord("t"):
            n = 20 if n == 10 else 10; sel = scroll = 0
        elif k in (curses.KEY_LEFT, ord("h"), ord("p")):
            day_key = shift(day_key, -1); sel = scroll = 0; msg = "Loading…"
        elif k in (curses.KEY_RIGHT, ord("l"), ord("n")):
            nxt = shift(day_key, 1)
            if nxt <= today_key():
                day_key = nxt; sel = scroll = 0
        elif k == ord("r"):
            try:
                src.refresh(); msg = "Refreshed"
            except Exception as ex:
                msg = f"Refresh failed: {ex}"


def shift(key, days):
    d = dt.datetime.strptime(key, "%Y%m%d") + dt.timedelta(days=days)
    return d.strftime("%Y%m%d")


def today_key():
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d")


def print_list(src, n, day_key, color):
    items = top(src.day(day_key), n)
    b, y, c, d, r = ("\033[1m", "\033[33m", "\033[36m", "\033[2m", "\033[0m") if color else ("",) * 5
    print(f"{b}HN top {n} · {day_label(day_key)}{r}")
    for i, e in enumerate(items, 1):
        src_ = f" {d}({e['source']}){r}" if e.get("source") else ""
        print(f"{i:>3}. {y}{e['points']:>5}{r} {c}{e['comments']:>4}{r}  {e['link_text']}{src_}")
        print(f"      {d}{link_of(e)}  ·  {HN_ITEM}{e['id']}{r}")


def main():
    ap = argparse.ArgumentParser(description="Skim hckrnews.com top 10/20 Hacker News headlines.")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("-10", dest="n", action="store_const", const=10, help="top 10 (default)")
    g.add_argument("-20", dest="n", action="store_const", const=20, help="top 20")
    ap.add_argument("-d", "--days-ago", type=int, default=0, help="show a past day (0 = today)")
    ap.add_argument("-p", "--print", action="store_true", help="print the list and exit (no TUI)")
    ap.add_argument("-o", "--open", type=int, metavar="N", help="open link of story N and exit")
    ap.add_argument("-c", "--comments", type=int, metavar="N", help="open discussion of story N and exit")
    a = ap.parse_args()
    n = a.n or 10
    day_key = shift(today_key(), -a.days_ago)

    src = Source()
    try:
        src.refresh()
    except Exception as ex:
        sys.exit(f"Could not reach hckrnews.com: {ex}")
    # The front page's newest day may lag UTC "today" by a bit; fall back to it.
    if a.days_ago == 0 and src.cache:
        day_key = max(src.cache)

    if a.open or a.comments:
        items = top(src.day(day_key), n)
        i = (a.open or a.comments) - 1
        if not 0 <= i < len(items):
            sys.exit(f"No story #{i + 1} (there are {len(items)}).")
        open_url(link_of(items[i]) if a.open else HN_ITEM + items[i]["id"])
    elif a.print or not sys.stdout.isatty():
        print_list(src, n, day_key, sys.stdout.isatty())
    else:
        curses.wrapper(run_tui, src, n, day_key)


if __name__ == "__main__":
    main()
