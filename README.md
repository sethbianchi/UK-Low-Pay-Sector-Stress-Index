# UK Low-Pay Sector Stress Index (LPS)

A live-updating index tracking employment momentum in the UK's two largest
low-pay sectors — retail and hospitality — around each April National
Living Wage uprating, built from Office for National Statistics (ONS)
workforce jobs data.

**Live site:** enable GitHub Pages on this repo (Settings → Pages → Deploy
from branch `main` / root) and it'll be served at
`https://<your-username>.github.io/<repo-name>/`

## How it works

- `fetch_and_score.py` pulls the latest retail (JWS3) and hospitality
  (JWS5) workforce jobs figures from ONS's time-series CSV endpoints,
  computes year-on-year and quarter-on-quarter momentum for each sector,
  and combines that with the size of the latest National Living Wage
  uprating into a single 0–100 stress score.
- `data.json` is the output of that script — the numbers the page displays.
- `index.html` fetches `data.json` at load time and renders the score,
  indicator cards, sector charts, and methodology table.
- `.github/workflows/update-lps.yml` runs the script every Monday via
  GitHub Actions and commits the refreshed `data.json` automatically —
  the same schedule as the companion Recession Vulnerability Index project.

## Methodology summary

| Indicator | Weight |
|---|---|
| Retail sector momentum (YoY jobs change, inverted) | 30% |
| Hospitality sector momentum (YoY jobs change, inverted) | 30% |
| Quarterly trend (latest q/q change, inverted) | 20% |
| Wage cost pressure (size of latest NLW uprating) | 20% |

See the "Methodology" and "Limitations" sections on the live page for full detail.

Built by **Seth Bianchi**.
