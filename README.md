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

Deploying to Fly.io (recommended - FREE 24/7)
---------------------------------------------

I added a `Dockerfile` and `fly.toml` so you can deploy the fetcher to Fly.io's free tier (includes persistent storage and always-on).

### Prerequisites
1. Install Fly.io CLI (flyctl)
2. Create a free Fly.io account
3. Authenticate flyctl

### Step-by-step deployment:

#### 1. Install flyctl (if not already installed)

```powershell
# Using PowerShell (run as Administrator)
iwr https://fly.io/install.ps1 -useb | iex
```

After installation, **close and reopen** your terminal, then verify:

```powershell
flyctl version
```

#### 2. Authenticate with Fly.io

```powershell
flyctl auth login
```

This will open a browser window — sign up or log in (GitHub auth is easiest).

#### 3. Launch the app

```powershell
# This will create the app and prompt for configuration
flyctl launch --no-deploy
```

When prompted:
- **App name:** Press Enter to use `rss-fetcher-data` (or choose your own)
- **Region:** Choose closest to you (e.g., `sin` for Singapore, `lax` for LA, `fra` for Frankfurt)
- **Would you like to set up a Postgresql database?** → **No**
- **Would you like to set up an Upstash Redis database?** → **No**
- **Would you like to deploy now?** → **No** (we'll create volume first)

#### 4. Create persistent volume for data storage

```powershell
# Create a 1GB volume (free tier allows up to 3GB total)
flyctl volumes create rss_data --size 1 --region sin
```

**Important:** Use the same region you selected in step 3!

#### 5. Deploy the app

```powershell
flyctl deploy
```

This will:
- Build the Docker image
- Push to Fly.io registry
- Deploy and start the worker
- Mount the volume at `/app/data`

#### 6. Verify it's running

```powershell
# Check app status
flyctl status

# View logs (should show fetching activity)
flyctl logs
```

You should see logs like:
```
INFO Starting fetcher: url=https://data.gmanetwork.com/gno/rss/news/regions/feed.xml
INFO Fetched 15 items, inserted 15 new.
INFO Updated JSON snapshot, 15 rows
```

#### 7. Check the data (optional)

```powershell
# SSH into the running container
flyctl ssh console

# Inside container, check the files:
ls -lh /app/data/
cat /app/data/rss_items.jsonl | head -n 2
exit
```

### Managing your app

```powershell
# View logs in real-time
flyctl logs -f

# Restart the app
flyctl apps restart

# Scale to 0 (stop) or 1 (start)
flyctl scale count 0  # stop
flyctl scale count 1  # start

# Check resource usage
flyctl status

# Destroy app (if you want to remove it)
flyctl apps destroy rss-fetcher-data
```

### Important Notes

**Free tier limits (as of 2025):**
- 3 shared-cpu VMs (256MB RAM each)
- 3GB persistent volume storage (total across all apps)
- 160GB outbound transfer/month
- **Perfect for this RSS fetcher!**

**Data persistence:**
- The volume (`rss_data`) persists across deploys and restarts
- `data/rss_items.db` and `data/rss_items.jsonl` are preserved

**Updating the app:**
- Make code changes locally
- Run `flyctl deploy` to rebuild and redeploy
- Data in the volume is preserved

### Troubleshooting

**If deployment fails:**
```powershell
# Check detailed logs
flyctl logs

# Check app status
flyctl status

# View machine details
flyctl machines list
```

**If you need to recreate volume:**
```powershell
# List volumes
flyctl volumes list

# Delete volume (WARNING: destroys data)
flyctl volumes delete <volume-id>

# Create new volume
flyctl volumes create rss_data --size 1 --region sin
```

### Local Testing (already done earlier)

```powershell
# Build the image
docker build -t rss-fetcher:local .

# Run the container (mount ./data so you can inspect DB output locally)
docker run --rm -v ${PWD}/data:/app/data rss-fetcher:local
```

### Next Steps

Once deployed, your fetcher will:
- Run 24/7 on Fly.io's free tier
- Poll the RSS feed every 5 minutes
- Store data in persistent volume
- Auto-restart if it crashes

**Need help?**
- Fly.io docs: https://fly.io/docs/
- Check your dashboard: https://fly.io/dashboard
