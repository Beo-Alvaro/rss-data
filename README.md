# RSS fetcher

This workspace contains a small, dependency-free RSS fetcher you can run on Windows (or any OS with Python 3).

What I added
- `scripts/rss_fetcher.py` — lightweight poller that fetches an RSS/Atom feed, deduplicates items, and stores them in SQLite.

Quick start (PowerShell)

1. Run the feed once to verify it works:

```powershell
python .\scripts\rss_fetcher.py --url "https://data.gmanetwork.com/gno/rss/news/regions/feed.xml" --once
```

2. Run as a 24/7 poller (poll every 5 minutes):

```powershell
python .\scripts\rss_fetcher.py --url "https://data.gmanetwork.com/gno/rss/news/regions/feed.xml" --interval 300
```

Notes
- The script stores data in `data/rss_items.db` by default. Add `--db path\to\file.db` to change location.
- No external packages are required; it uses Python stdlib (urllib, xml.etree, sqlite3).
- For production on Windows you can run with Task Scheduler, `Start-Job`, or a Windows service wrapper.

Next steps (suggested)
- Add a small exporter to output JSONL for your zero-shot classification tests.
- Add a simple web endpoint to stream latest items.

Recent changes
- Article-page fetching removed: I removed the article-fetching script and any stored article HTML/previews because you asked to avoid fetching link contents. We still keep the RSS feed metadata (title/link/summary) in the SQLite DB and can export it to JSONL.

Exporter and JSONL
- `scripts/export_jsonl.py` exports rows from `data/rss_items.db` into JSONL. Each line contains the following fields:
	- `guid` — unique id for the RSS item
	- `title` — the feed title
	- `link` — the original article URL
	- `published` — published date when available
	- `summary` — the RSS/ATOM description or summary
	- `fetched_at` — when the item was fetched into the DB

	Example:

	{
		"guid": "tag:gmanetwork.com:news_story-963756",
		"title": "Three minor eruptions monitored at Taal Volcano --PHIVOLCS",
		"link": "https://...",
		"published": "2025-10-26T10:01:00Z",
		"summary": "Taal Volcano had three minor eruptions...",
		"fetched_at": "2025-10-26T11:10:31.646373Z"
	}

Is `data/rss_items.jsonl` enough for zero-shot classification?
- Short answer: yes — it can be sufficient for early zero-shot experiments, depending on what you want to classify.

- When it's sufficient:
	- You want to classify news headlines or summaries into broad categories (e.g., "disaster", "volcano", "crime", "politics").
	- Your model's prompt will rely on the headline/title and/or the summary — both are present in the JSONL.
	- You plan to test generic zero-shot prompt templates (no fine-tuning) and evaluate coarse-grained outputs.

- When it's not ideal:
	- You need the full article text to capture details used by fine-grained labels (e.g., named entities, sentiment inside the article, or multi-paragraph reasoning).
	- You want to create strong in-context examples for few-shot prompts that use long article contexts.

Recommendations and quick recipes
- Minimal zero-shot recipe (headline-only):

	Prompt template:

	"Classify the following headline into one of these labels: [disaster, weather, politics, crime, human-interest, other].\n\nHeadline: \"{title}\"\nLabel:" 

	Use the `title` field from each JSONL line as `{title}`.

- Better recipe (headline + summary):

	Prompt template:

	"Given the headline and short summary, classify into one of these labels: [disaster, weather, politics, crime, human-interest, other].\n\nHeadline: \"{title}\"\nSummary: \"{summary}\"\nLabel:"

- Creating prompt/label pairs locally
	- If you want scripted prompt/label generation, I can add a small helper script that reads `data/rss_items.jsonl` and writes a `data/zero_shot_prompts.jsonl` file where each line is {"prompt":..., "expected": null, "metadata": ...} so you can feed the prompts to your model.

Practical tips
- Use the `title` as the highest-signal field for short prompts. Add `summary` if you need more context.
- If a site adds cookie banners or noise into `summary`, you might want to pre-clean the text (strip common cookie banner phrases). The exporter uses the raw feed summary; feel free to ask and I'll add a small cleaner.
- If you later decide you need full article text, I recommend using a readability-oriented extractor (readability-lxml or newspaper3k) — I can add that and a `requirements.txt`.

How to regenerate JSONL
1. If you want to re-run the exporter and produce `data/rss_items.jsonl`:

```powershell
python .\scripts\export_jsonl.py --db data\rss_items.db --out data\rss_items.jsonl
```

2. Convert to prompt lines (I can add this script for you) or run the exporter with `--since`/`--limit` to get desired subsets.

If you'd like, I can now:
- Add a small helper script to convert `data/rss_items.jsonl` into prompt JSONL for zero-shot testing.
- Add cleaning of `summary` to remove cookie-banner noise.
- Add a short README example showing exact PowerShell commands and a sample prompt file.

Deploying to Render (quick start)
--------------------------------

I added a `Dockerfile` and a `render.yaml` template so you can deploy the fetcher as a worker on Render.

Important notes before you deploy:
- The container runs the fetcher as a long-running worker (no web port required).
- Render instances have an ephemeral filesystem by default. If you need to preserve `data/rss_items.db` across deploys or restarts, you must either attach a Render Disk to the service or store the data externally (managed DB or object storage). See "persistence" below.

Steps (recommended, via the Render dashboard):

1. Commit and push the repo (including the new `Dockerfile` and `render.yaml`) to GitHub.
2. On Render, create a new service -> "Connect a repository" -> choose the repo and branch.
3. When selecting the service type, choose "Docker" and set it up as a "Worker" service. If you use the `render.yaml` file, Render can import the spec automatically.
4. Enable automatic deploys on push (Render will build the Dockerfile and start the worker).

Local test (build & run the container locally):

```powershell
# build the image
docker build -t rss-fetcher:local .

# run the container (mount ./data so you can inspect DB output locally)
docker run --rm -v ${PWD}/data:/app/data rss-fetcher:local
```

Persistence options
- Use Render Disks (attach a disk to the service) — this keeps files across deploys and restarts.
- Use an external persistence layer: push data to a managed database or object store (e.g., managed Postgres, Cloud SQL, S3/GCS). I can add support for a remote DB if you prefer.

Environment variables and secrets
- If you need API keys or other secrets, add them in the Render dashboard under the service settings (they're exposed as environment variables inside the container). No secrets are required by default.

Next steps I can do for you
- Fill in `render.yaml` with your repo URL and branch.
- Add Render Disk support or switch to a managed DB for persistence.
- Add an optional GitHub Actions workflow that notifies Render (or calls Render's API) if you prefer CI-triggered deploys rather than Render's GitHub integration.

If you want, I can now fill in the `render.yaml` with your GitHub repo URL and finish wiring a simple GitHub Actions deploy step — tell me your repo URL (or allow me to keep placeholders and provide step-by-step instructions).
