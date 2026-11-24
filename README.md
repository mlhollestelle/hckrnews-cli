# hckrnews-cli

Skim the [hckrnews.com](https://hckrnews.com/) top 10 / top 20 Hacker News headlines in your terminal, and open the article or discussion in your browser.

Uses hckrnews.com's own data and the same "top N" cut-off, so the list matches the website. Pure Python, no dependencies.

## Install

```bash
uv tool install .            # or: pipx install .
```

## Usage

```bash
hn          # interactive top 10
hn -20      # interactive top 20
hn -d 1     # yesterday
hn -p       # print the list and exit
hn -o 3     # open story 3's link
hn -c 3     # open story 3's discussion
```

Keys: `↑↓`/`jk` move · `Enter`/`o` article · `c` discussion · `b` both · `t` top 10/20 · `←→`/`hl` day · `r` refresh · `q` quit

On WSL, links open in your Windows browser.

Note: early in the day "top 10" shows fewer stories, because the cut-off scales with how much of the day has passed, just as on the website.
