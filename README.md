# India Bureaucrat Accountability Tracker

A production-ready, Dockerized public interest portal that automatically discovers, stores, and displays IAS/IPS officer corruption and misconduct cases from live internet news sources using automated daily scraping.

**Public Interest Disclaimer**: This application aggregates publicly available news articles about allegations against Indian civil service officers. Charges are allegations unless judicially proven. This tool is intended for transparency, research, and public accountability purposes only.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                    Nginx Reverse Proxy                   │
│                   (Port 80 / 443 SSL)                    │
└─────────────────────┬───────────────────────────────────┘
                      │
        ┌─────────────▼─────────────┐
        │   FastAPI Application     │
        │  (Port 8000 internal)     │
        │                           │
        │  ┌─────────────────────┐  │
        │  │  Jinja2 Templates   │  │
        │  │  (Frontend SPA)     │  │
        │  └─────────────────────┘  │
        │  ┌─────────────────────┐  │
        │  │  REST API Routers   │  │
        │  │  /api/officers      │  │
        │  │  /api/articles      │  │
        │  │  /api/stats         │  │
        │  └─────────────────────┘  │
        │  ┌─────────────────────┐  │
        │  │  APScheduler        │  │
        │  │  (Daily @02:00 IST) │  │
        │  └─────────────────────┘  │
        └─────────────────┬──────────┘
                          │
        ┌─────────────────▼──────────────┐
        │    SQLite Database             │
        │  /app/data/tracker.db          │
        │  (Docker Volume: ./data)       │
        │                                │
        │  Tables:                       │
        │  - officers                    │
        │  - articles                    │
        │  - settings                    │
        └────────────────────────────────┘

Scraper Pipeline (Runs Daily):
  RSS Feeds (8x Google News) → Article Fetch + HTML Parse
    ↓
  spaCy NLP Extraction (PERSON, GPE entities)
    ↓
  Regex-based Fallback Parsing (if NLP unavailable)
    ↓
  Officer Name Fuzzy Matching (difflib 0.85 threshold)
    ↓
  Status, Agency, Charges Detection
    ↓
  Deduplication & Database Upsert
    ↓
  Update last_scraped_at timestamp
```

---

## Prerequisites

- **Docker**: v20.10+
- **Docker Compose**: v1.29+
- **Git** (optional, for cloning)
- **4GB+ free disk space** (for spaCy model + database)
- **Internet connection** (for RSS feed and article fetching)

---

## Quick Start

### 1. Clone or Download the Repository

```bash
git clone https://github.com/yourusername/india-tracker.git
cd india-tracker
```

### 2. Copy and Configure Environment

```bash
cp .env.example .env
nano .env  # or edit in your preferred editor
```

Update the ADMIN_TOKEN to a secure random string:
```
ADMIN_TOKEN=your_super_secret_random_token_here_at_least_16_chars
```

### 3. Start the Application

```bash
docker-compose up --build
```

On first boot:
- Docker builds the image (installs Python, dependencies, downloads spaCy model)
- Container starts FastAPI server
- Initial scrape runs automatically (fetches ~50-100 recent cases from Google News)
- APScheduler schedules daily scrapes at 02:00 IST

**First run takes 3-5 minutes** (downloading spaCy model is slow).

### 4. Access the Application

Open your browser:
```
http://localhost/
```

You should see:
- Dashboard with 6 metric cards (Total, IAS, IPS, Suspended, Arrested, Convicted)
- Filter bar (by Service, Status, Cadre, Search)
- Data table with officer records
- Clickable rows showing article drawer with details

---

## Features

### Dashboard
- **Real-time statistics** of cases by service (IAS/IPS/IRS) and status
- **Last scraped timestamp** showing when data was last refreshed
- **Quick metrics** for high-level accountability overview

### Search & Filtering
- Text search by officer name or charge summary
- Filter by service type, status, or cadre
- Dropdown filters dynamically populated from database
- Instant results (no page reload required)

### Officer Records
- Full details: name, service, batch year, cadre, current position
- Charge summary and investigating agency
- Status badge with color coding (red=Arrested, amber=Suspended, purple=Convicted)
- Link to original news articles

### Article Linking
- Each officer record shows all linked news articles
- Direct links to original sources (The Hindu, NDTV, etc.)
- Publication dates and article snippets
- Evidence trail for allegations

### Daily Automated Scraping
- Runs at **02:00 IST** daily via APScheduler
- Fetches 8 Google News RSS feeds with officer corruption keywords
- Extracts officer details using spaCy NLP
- Deduplicates using fuzzy name matching (85% similarity threshold)
- Graceful error handling (timeouts, network failures)

---

## API Endpoints

All responses in JSON. All `datetime` fields in ISO 8601 format.

### Frontend
- `GET /` - Serves the single-page application (Jinja2 template)

### Statistics
- `GET /api/stats` - Global stats (total count, by service, by status, by cadre, last_scraped_at)

### Officers
- `GET /api/officers?service=IAS&status=Suspended&cadre=UP&q=searchterm&page=1&per_page=50`
  - List officers with optional filters
  - Returns: `{data: [...], total, page, per_page, pages}`

- `GET /api/officers/{id}` - Single officer detail with linked articles

### Articles
- `GET /api/articles?officer_id=5&limit=20` - Recent articles
- `GET /api/articles/{id}` - Single article details

### Scraping
- `POST /api/scrape/trigger` - Manually trigger a scrape (requires `X-Admin-Token` header)
  - Returns: `{status, result: {new_officers, updated_officers, new_articles, skipped, errors, timestamp}}`

### Health
- `GET /api/health` - System health check
  - Returns: `{status, db_record_count, last_scraped_at}`

---

## Manual Scraping

Trigger a scrape on-demand (useful for testing or urgent updates):

```bash
curl -X POST http://localhost/api/scrape/trigger \
  -H "X-Admin-Token: your_admin_token_from_env"
```

Response:
```json
{
  "status": "success",
  "result": {
    "new_officers": 3,
    "updated_officers": 5,
    "new_articles": 18,
    "skipped": 2,
    "errors": 0,
    "timestamp": "2024-01-15T12:30:45.123456"
  }
}
```

**In the UI**: Click "Trigger Scrape" button (top-right), enter the admin token, and results show in a dialog.

---

## Database Schema

### officers
```sql
id              INTEGER PRIMARY KEY
name            TEXT NOT NULL (indexed)
service         TEXT (IAS, IPS, IRS, IFS, etc.)
batch_year      TEXT
cadre           TEXT (indexed) — state/cadre
charge_summary  TEXT
investigating_agency  TEXT (CBI, ED, CVC, ACB, etc.)
status          TEXT (Suspended, Arrested, Convicted, etc.)
current_position TEXT
source_url      TEXT
first_seen_at   DATETIME
last_updated_at DATETIME
is_verified     BOOLEAN (default False)
```

### articles
```sql
id              INTEGER PRIMARY KEY
officer_id      INTEGER FK → officers.id (nullable)
headline        TEXT NOT NULL
source_name     TEXT (publication: "The Hindu", "NDTV", etc.)
url             TEXT UNIQUE NOT NULL (indexed)
published_at    DATETIME
scraped_at      DATETIME
full_text       TEXT
snippet         TEXT (first 300 chars)
matched_keywords TEXT (comma-separated)
raw_entities    TEXT (JSON)
```

### settings
```sql
id              INTEGER PRIMARY KEY (always 1)
key             TEXT UNIQUE (e.g., "last_scraped_at")
value           TEXT
```

---

## Scraper Details

### Data Sources
Fetches from **8 Google News RSS feeds** searching for keywords:
- IAS officer arrests
- IPS officer corruption cases
- CBI/ED/Vigilance investigations
- Bribery, disproportionate assets, money laundering charges
- Dismissals, suspensions, convictions

**No hardcoded data** — all records originate from live news sources.

### NLP Processing

Uses **spaCy en_core_web_sm** model to:
1. Extract **PERSON entities** → candidate officer name (picks most prominent)
2. Extract **GPE entities** → cadre/state information
3. Detect service type via regex patterns ("IAS officer", "IPS officer", etc.)
4. Identify investigating agency via keyword matching (CBI, ED, CVC, ACB)
5. Determine status via keyword rules (arrested, suspended, convicted, etc.)

**Fallback**: If spaCy fails to load, the scraper falls back to regex-only extraction (still functional, slightly less accurate).

### Deduplication

- **Officer names**: Fuzzy matching using `difflib.SequenceMatcher` (threshold: 0.85)
- **Articles**: URL-based uniqueness constraint (no duplicates)
- **Updates**: If officer already exists, updates status/agency/charges if newer info found; links new article to same officer record

### Error Handling

- Network timeouts (httpx): logs and skips article, continues with next
- RSS parse failures: logged error, moves to next feed
- spaCy model unavailable: switches to regex extraction automatically
- Database commits: transaction-safe with rollback on error
- Scheduler failures: logged but don't crash application

---

## Configuration

### .env File

```bash
# Admin token for manual scraping (use strong random string)
ADMIN_TOKEN=your_secret_token

# SQLite database path inside container
DATABASE_URL=sqlite:////app/data/tracker.db

# Scrape interval (currently unused; scheduler uses hardcoded 02:00 IST)
SCRAPE_INTERVAL_HOURS=24

# Logging level (DEBUG, INFO, WARNING, ERROR)
LOG_LEVEL=INFO
```

### Docker Compose

- **app service**:
  - Builds from Dockerfile
  - Ports: 8000 (FastAPI) — **not exposed** to internet (proxied via Nginx)
  - Volume: `./data:/app/data` — persists SQLite database
  - Reads .env file automatically
  - Depends on Nginx service

- **nginx service**:
  - Uses `nginx:alpine` image
  - Ports: 80 (HTTP), 443 (HTTPS ready)
  - Proxies all traffic to app:8000
  - Includes gzip compression
  - SSL block commented out (ready for production)

---

## Production Deployment

### Enable HTTPS with Let's Encrypt

```bash
# 1. Install Certbot
sudo apt-get install certbot python3-certbot-nginx

# 2. Generate certificate (stop docker-compose first)
sudo certbot certonly --standalone -d yourdomain.com

# 3. Update nginx/nginx.conf — uncomment HTTPS block, update paths:
#    ssl_certificate /etc/nginx/ssl/fullchain.pem;
#    ssl_certificate_key /etc/nginx/ssl/privkey.pem;

# 4. Mount certificates in docker-compose.yml:
#    volumes:
#      - /etc/letsencrypt/live/yourdomain.com:/etc/nginx/ssl:ro

# 5. Restart services
docker-compose up -d
```

### Firewall & Security

```bash
# UFW (Ubuntu)
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable

# Restrict admin token to IP whitelist (in Nginx config):
# allow 203.0.113.0/24;
# deny all;
```

### Backup Strategy

```bash
# Daily backup of SQLite database
0 3 * * * docker cp india-tracker-app:/app/data/tracker.db /backups/tracker-$(date +\%Y\%m\%d).db
```

### Monitoring

Check logs:
```bash
docker-compose logs -f app
docker-compose logs -f nginx
```

---

## Development

### Local Setup (without Docker)

```bash
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows
pip install -r requirements.txt
python -m spacy download en_core_web_sm
export ADMIN_TOKEN=dev_token
export DATABASE_URL=sqlite:///./test.db
uvicorn app.main:app --reload
```

### Running Tests

```bash
# TODO: Add pytest fixtures and test suite
pytest tests/
```

### Adding New Scraper Feeds

Edit `app/scraper.py` → `RSS_FEEDS` list:
```python
RSS_FEEDS = [
    "https://news.google.com/rss/search?q=new_search_query&hl=en-IN&gl=IN&ceid=IN:en",
    # ... add new feeds
]
```

Restart container:
```bash
docker-compose restart app
```

---

## Contributing

This is a public interest project. Contributions welcome!

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/your-feature`)
3. Commit changes (`git commit -am 'Add your feature'`)
4. Push to branch (`git push origin feature/your-feature`)
5. Open a Pull Request

---

## License

MIT License — See LICENSE file for details.

---

## Disclaimer

This application aggregates publicly available information. The data and allegations presented are from public news sources and do not constitute judicial findings. This tool is intended for transparency, research, and public accountability purposes under Indian RTI/FOIA principles. Users should verify information independently.

**Not affiliated with any government agency or organization.**

---

## Support & Issues

Report bugs: [GitHub Issues](https://github.com/yourusername/india-tracker/issues)

For questions or feedback, open a discussion or contact the maintainers.

---

## Roadmap

- [ ] Multi-language support (Hindi, regional languages)
- [ ] Advanced filtering (date range, concurrent investigation count)
- [ ] CSV/PDF export of filtered records
- [ ] Officer photo integration (if available from news)
- [ ] Timeline visualization of cases
- [ ] Integration with RTI/DOPT official records (if APIs available)
- [ ] Email alerts for new cases
- [ ] Mobile app (React Native)
- [ ] Integration tests with real Docker container
- [ ] Performance optimization (pagination, caching layer)

---

Last Updated: 2024-01-15
#   G o v E m p T r a c k e r  
 