# Finals runbook: running Voxam locally, with a free tunnel when judges need a link

**Decision (D26): no hosting.** The product runs on a computer we control (your Mac or a lab iMac, as MSOT's "local-first" answer suggests).
Nothing is rented, so the cost is Rs 0. A free tunnel gives other computers an https link for a few hours when needed.

## Why a tunnel at all
Browsers allow the microphone only on `https` or on `localhost`. A judge on another computer cannot use `http://192.168...`. Two ways round it:
1. The judge sits at the machine running Voxam (nothing to set up): use `http://localhost:5173`.
2. The judge uses their own computer: give them one https link from a free tunnel.

## Start it (about 2 minutes)
```bash
cd /path/to/ai-viva && git pull
FACULTY_TOKENS="mayank:$(openssl rand -hex 12)" scripts/run_finals.sh --fresh      # note the token that is printed back
```
It builds the app, starts the backend, scoring worker and the two seeded vivas (`local-dsa`, `local-webdev`), and serves everything on **one address**,
`http://localhost:5173` (the API is under `/api`). Student codes are in `.local/codes.txt`; the faculty token is the part of `FACULTY_TOKENS` after the colon.
Approve the Web Development questions (Faculty > viva > Manage question bank) **before** any student joins.

## The public link (free, no account)
```bash
brew install cloudflared                  # once
TUNNEL=1 FACULTY_TOKENS="mayank:..." scripts/run_finals.sh        # prints https://<random>.trycloudflare.com
```
or in a second terminal: `cloudflared tunnel --url http://localhost:5173`. Without installing anything: `ssh -R 80:localhost:5173 nokey@localhost.run`.
Give judges `https://<random>.trycloudflare.com/student?viva=local-dsa`. The address changes every time the tunnel restarts.

## What protects it
Anyone with the link can open the pages, so: a long random faculty token (the script refuses the public demo token), one-time personal student codes, and
the wrong-code throttle. Do not paste the link or token into public places, stop the tunnel (Ctrl-C) when the session is over, and use `--fresh` for a clean database.

## Rehearse once (30 minutes)
1. Start it, open the public link on a phone or another computer, join as `LOCAL01` by typing, then by voice (headphones).
2. Run the simulated batch while you take a viva: `python scripts/load_test.py --scenario finals --levels 10 25` (modelled providers; see `docs/reports/T7.md` for what it proves).
3. Check the faculty tab: transcript, audio replay, score, release results.

## What it can and cannot do
- One Mac handled about 25 accelerated sessions at p95 3.1 s in the modelled run (`results/load/`); real speech models were not load-tested together, so keep the live batch small.
- The tunnel adds a little latency; voice goes over a WebSocket through it (tested here with a scripted bot over the single address).
- If the tunnel drops, students keep their session and reconnect; the clock keeps running on the server.
