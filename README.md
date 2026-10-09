# NewsPulse — Backend (FastAPI)

## Scope so far
- **Day 1:** health-check endpoint only.
- **Module 2:** JWT Authentication — register, login, forgot/reset password (real SMTP email, with console fallback), current-user, logout.
- **Module 3:** News Search — multi-provider search (GNews → NewsData.io → Google News RSS fallback), predefined + custom tags, newspaper/edition metadata, search history logging.
- **Module 4:** PDF Report Generation — selected articles become a professional, branded PDF (WeasyPrint) with cover page, headers/footers/page numbers, stored in MySQL + on disk.
- **Module 5 (this update): Admin Dashboard.** Org-wide stats (total/active users, searches, reports), recent activity, per-user activity breakdown, and six charts — all computed with live aggregation queries, no separate analytics table to keep in sync.

This is the last module from the original project spec — see project root README for what's next.

## Setup

```bash
cd backend
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

pip install -r requirements.txt

cp .env.example .env            # then edit values — SECRET_KEY especially

uvicorn app.main:app --reload
```

On startup the app calls `Base.metadata.create_all()`, which creates the
`users` and `password_reset_tokens` tables automatically if they don't
already exist (matching `database/schema.sql` exactly). You still need
a running MySQL server and a database named `newspulse` — either run
`database/schema.sql` yourself first, or just start the app against an
empty `newspulse` database and let it create the auth tables for you.

API will be available at:
- http://localhost:8000/            → root status message
- http://localhost:8000/api/v1/health → health check used by the frontend
- http://localhost:8000/api/v1/auth/* → auth endpoints (see below)
- http://localhost:8000/docs         → interactive Swagger UI (has an "Authorize" button)

## Upgrading an existing database

If you already had this project running against a real MySQL database
before this update, **you don't need to run any SQL manually.** The
`newspapers` and `newspaper_editions` tables (and their 12 newspapers'
worth of seed data) are created and populated automatically the next
time you start the backend — `Base.metadata.create_all()` adds the two
new tables without touching your existing ones, and
`newspaper_service.seed_if_empty()` fills them in right after. Just
restart `uvicorn` and it's handled.

## News search endpoints

| Method | Path                     | Auth required | Purpose |
|--------|--------------------------|----------------|---------|
| GET    | `/api/v1/news/languages` | No             | The 3 supported languages: `[{"code": "en", "label": "English"}, ...]` |
| GET    | `/api/v1/news/newspapers`| No             | Newspapers for a language — `?language=te` or `?language=Telugu` (case-insensitive, either works) |
| GET    | `/api/v1/news/editions`  | No             | Editions for one newspaper — `?newspaper=eenadu` |
| GET    | `/api/v1/news/search`    | Yes (Bearer)   | Search articles — see params below |
| GET    | `/api/v1/news/tags`      | Yes (Bearer)   | Predefined tags + your custom tags |
| POST   | `/api/v1/news/tags`      | Yes (Bearer)   | Add a custom tag: `{"tag": "Slag Utilization"}` |
| DELETE | `/api/v1/news/tags/{id}` | Yes (Bearer)   | Delete one of your custom tags |

**`GET /news/search` query params:** `keyword` (required, 2+ chars),
`language` (`en`/`te`/`hi`, default `en`), `newspaper` (a key from
`/news/newspapers`, e.g. `the_hindu`), `edition` (must be one of that
newspaper's editions from `/news/editions` — requires `newspaper` to be
set), `date_filter` (`any`/`today`/`yesterday`/`custom`, default `any`),
`date_from` and `date_to` (`YYYY-MM-DD`, both required when
`date_filter=custom`, `date_to` must be on or after `date_from`), `page`
(default 1), `page_size` (default 10, max 30).

### The Language → Newspaper → Edition cascade

This is a genuine cascading hierarchy, stored in the database (tables
`newspapers` and `newspaper_editions` — see `app/models/newspaper.py`),
not hardcoded anywhere in the frontend or backend Python. The frontend
follows exactly this request flow:

```
GET /news/languages
      ↓ (user picks a language)
GET /news/newspapers?language=Telugu
      ↓ (user picks a newspaper — optional)
GET /news/editions?newspaper=eenadu   (or GET /news/editions with no param, for every edition across all newspapers)
      ↓ (user picks an edition, keyword/tags, and searches)
GET /news/search?...
```

Changing the language resets the newspaper and edition selections;
changing the newspaper resets the edition. If a newspaper genuinely has
no editions on file, the endpoint returns `{"editions": []}` (a normal
200, not an error) and the frontend shows "No editions available."

**Edition does not require a newspaper to be selected first.** Picking
just an edition (e.g. "Visakhapatnam") searches across every newspaper
for that location instead of one specific outlet — `GET /news/editions`
with no `newspaper` param returns the deduplicated union of every
edition across all 12 newspapers for exactly this case. Since none of
the three integrated providers support true per-edition filtering
(`edition_query_supported` is `False` on every seeded newspaper), the
edition is folded into the search query text as a location hint
instead — this happens whether or not a newspaper is also selected.

**When a specific newspaper *is* selected, results are strictly
verified to actually be from that outlet** before reaching the user —
see "Newspaper filtering is enforced, not just hinted" below.

**Adding a new newspaper or edition needs zero frontend or backend code
changes** — it's a database insert:

```sql
INSERT INTO newspapers (`key`, label, language, domain, edition_query_supported)
VALUES ('deccan_chronicle', 'Deccan Chronicle', 'en', 'deccanchronicle.com', FALSE);

INSERT INTO newspaper_editions (newspaper_id, name)
VALUES ((SELECT id FROM newspapers WHERE `key` = 'deccan_chronicle'), 'Hyderabad');
```

It'll show up in `/news/newspapers?language=en` and the frontend
dropdown immediately, with no restart needed.

**Where this data initially comes from:** `app/db/seed_data.py` is read
exactly once — on first startup, if the `newspapers` table is empty,
`app/services/newspaper_service.seed_if_empty()` populates it with the
12 newspapers from the project spec (editions for The Hindu, Times of
India, Eenadu, Sakshi, and Dainik Jagran match the spec's exact
required lists; the other 7 newspapers' editions are a reasonable
real-world approximation, not independently verified — safe to correct
with an `UPDATE`/`INSERT` if you know the real ones you want). After
that first run, this file is never read again — every request is
served from the database.

Note: `languages` itself (English/Telugu/Hindi) is kept as a small
fixed list in `newspaper_service.py`, not a database table — unlike
newspapers/editions, adding a language isn't a pure data change (it
needs RSS locale support, provider language capability flags, and
translated predefined tags too), so it's reasonably scoped as a backend
code change rather than a runtime insert. It's still served through a
real endpoint rather than hardcoded in the frontend.

### Newspaper filtering is enforced, not just hinted

Selecting a newspaper used to only *hint* at a restriction — GNews and
NewsData.io's free tiers have no real per-domain filter, and Google
News RSS's `site:` search operator is a best-effort signal Google can
still ignore, especially when combined with an OR expression from
multi-tag selection (`Steel OR RINL site:thehindu.com` was silently
being parsed as `Steel OR (RINL site:thehindu.com)` — the site
restriction only applied to half the query). Two fixes:

1. **Query construction is now always parenthesized**
   (`(Steel OR RINL) site:thehindu.com`) so the restriction applies to
   the whole keyword expression, not just the term next to it.
2. **Every result is verified after fetching**, before it ever reaches
   the user (`app/services/news/aggregator.py::_matches_newspaper`).
   This checks two signals, since no single one is reliable across all
   three providers: the article's URL domain (works for GNews/
   NewsData.io, which link directly to the original publisher) and its
   `source_name` against the newspaper's label (the only reliable
   signal for RSS, whose `<link>` is always a `news.google.com` redirect
   wrapper, never the publisher's own domain). If a provider's results
   turn out to contain zero genuine matches after this check, the
   aggregator moves on to the next provider in the fallback chain
   rather than showing the wrong newspaper's articles.

### News provider architecture

`app/services/news/` implements one class per provider behind a shared
`BaseNewsProvider` interface, and `aggregator.py` tries them **in this
order**, per the project's required architecture:

1. **GNews** (primary) — needs `GNEWS_API_KEY`. Supports English + Hindi.
2. **NewsData.io** (secondary) — needs `NEWSDATA_API_KEY`. Supports
   English, Telugu, and Hindi — this is why it's kept as a real fallback
   rather than dropped, since GNews has no Telugu support.
3. **Google News RSS** (fallback) — **no API key needed, always active.**
   This is what search runs on by default with a fresh clone. It also
   uniquely supports restricting results to one newspaper (via a
   `site:domain.com` search operator), since neither GNews's nor
   NewsData.io's free tiers offer real domain filtering.

The aggregator skips a provider outright if it doesn't support the
requested language, catches any request/API failure and moves to the
next provider, and — if a provider's results come back empty after the
date filter is applied — also moves to the next one rather than
returning zero results prematurely. The response's `provider_used`
field tells you which one actually answered.

Every newspaper currently has `edition_query_supported: False`:
editions are shown in the UI for the user's own reference (and recorded
in search history) but not passed to any provider, since none of the
three integrated sources support real per-edition search — this
follows the spec's "gracefully disable unsupported filters" requirement
rather than pretending the filter works.

To get real API keys:
- GNews: https://gnews.io/ (free tier: 100 requests/day)
- NewsData.io: https://newsdata.io/ (free tier: 200 requests/day)

Both are optional — leave them blank in `.env` and search still works
end-to-end via the RSS fallback.

## Report generation endpoints

| Method | Path                         | Auth required | Purpose |
|--------|------------------------------|----------------|---------|
| POST   | `/api/v1/reports/generate`   | Yes (Bearer)   | Build a PDF from selected articles, returns metadata + a download URL |
| GET    | `/api/v1/reports`            | Yes (Bearer)   | List your own generated reports, most recent first |
| GET    | `/api/v1/reports/{id}/download` | Yes (Bearer) | Stream the PDF file (404s if it's not your report) |

**`POST /reports/generate` body:**
```json
{
  "keyword": "Blast Furnace",
  "language": "en",
  "newspaper": "the_hindu",
  "edition": "Visakhapatnam",
  "articles": [
    {
      "title": "...", "source_name": "...", "url": "...",
      "description": "...", "image_url": "...", "published_at": "...",
      "content": "..."
    }
  ]
}
```
`newspaper`/`edition` are optional (used only for the PDF's cover page).
`articles` should be the exact objects the frontend already has from a
search response (`ArticleOut`) — the backend doesn't re-fetch from the
news provider, since the person already reviewed and selected these
specific results.

### How the PDF is built

- **Template:** `app/templates/report_template.html`, rendered with
  Jinja2 (autoescaping on, so article text containing HTML/special
  characters can never break the layout or inject markup) and turned
  into a PDF with WeasyPrint.
- **Header/footer/page numbers:** done with CSS `@page` rules
  (`@top-center`, `@bottom-left`, `@bottom-right`, `counter(page)` /
  `counter(pages)`) — WeasyPrint renders these on every page automatically.
- **Automatic page breaks:** each article block uses `break-inside:
  avoid` so WeasyPrint's normal flow layout never splits one article's
  headline from its body across a page boundary; there's no manual
  page-break-per-article, so short articles share pages efficiently.
- **Maximizing available text without scraping:** `content` (GNews/
  NewsData.io, mainly paid-tier) is often truncated with a trailing
  `[+N chars]` marker, which is stripped. When `description` says
  something genuinely different from what's left of `content`, both
  are kept in the report (content, then description) instead of
  picking only one — this is what actually maximizes the text shown.
  If one is just a near-duplicate of the other, only the longer is
  kept, so the same sentence never appears twice. If there's no
  `content` at all (always true for the RSS fallback), the report
  falls back to `description` alone, then finally a "no summary
  available" note. No scraping of the original article page is done —
  content is only ever what the news provider itself supplied. See
  `app/services/report_service.py::_resolve_content`.
- **Storage:** `app/services/report_service.py` caches each selected
  article in the `articles` table (deduped by URL — the same article
  picked into two reports doesn't create two rows), creates a `reports`
  row, writes the PDF to `REPORTS_DIR/<user_id>/<report_id>-<slug>.pdf`,
  and links them via `report_articles`.

## Automated tests

```bash
cd backend
pip install -r requirements.txt -r requirements-dev.txt
pytest
```

58 tests in `tests/`, organized by module (`test_auth.py`, `test_news.py`,
`test_reports.py`, `test_admin.py`). Each test gets its own isolated
in-memory SQLite database (see `tests/conftest.py`) — nothing touches a
real MySQL instance, and tests can't leak state into each other. News
provider calls are mocked with a canned RSS feed (`mock_rss` fixture) so
the suite never makes real network calls or needs API keys.

Coverage includes: registration/login/password-reset edge cases,
cross-user data isolation (can't see another user's tags/reports),
admin-only route enforcement, the RSS provider fallback path, PDF
generation producing a real, correctly-escaped PDF, and article
deduplication across reports.

## Installing WeasyPrint's system dependencies (important on Windows)

WeasyPrint renders PDFs using Pango/Cairo/GDK-Pixbuf — native libraries
that `pip install` alone does not provide. If report generation fails
with an error mentioning `libgobject`, `cairo`, or `pango`, install these
first:

- **Windows:** install the GTK3 runtime — the easiest path is the
  installer from https://github.com/tschoonj/GTK-for-Windows-Runtime-Environment-Installer/releases
  (adds Pango/Cairo/GDK-Pixbuf to your PATH). Restart your terminal
  after installing. Full WeasyPrint Windows notes:
  https://doc.courtbouillon.org/weasyprint/stable/first_steps.html#windows
- **macOS:** `brew install pango`
- **Linux (Debian/Ubuntu):** `sudo apt-get install libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf2.0-0 libcairo2 libffi-dev shared-mime-info fonts-liberation`

This only affects report generation — auth and news search work without
any of this installed.

## Admin dashboard endpoints

Both require the signed-in user's `is_admin` flag to be true — anyone
else gets a 403.

| Method | Path                   | Purpose |
|--------|------------------------|---------|
| GET    | `/api/v1/admin/dashboard` | Overview stats, recent searches/reports, and all 6 charts in one response |
| GET    | `/api/v1/admin/users`     | Every user with their search/report counts and last login |

### Making yourself an admin

There's no signup flow for admins on purpose — registration always
creates a regular user. To promote an account, run this directly
against MySQL:

```sql
UPDATE users SET is_admin = TRUE WHERE email = 'your.email@vizagsteel.com';
```

### How the metrics are computed

Everything in `app/services/admin_service.py` is a live `COUNT`/`GROUP BY`
query over `users`, `search_history`, and `reports` — there's no
separate analytics table that could drift out of sync with real data.
A few judgment calls worth knowing about:

- **Active Users** = users with `last_login_at` within the last 30 days
  (`ACTIVE_USER_WINDOW_DAYS` in `admin_service.py`). `last_login_at` is
  set on every successful `/auth/login` call (not on registration), so
  a freshly-registered-but-never-logged-in-again user won't count.
- **Most Searched Keywords** groups case-sensitively ("Steel" and
  "steel" count separately) — this keeps the query portable across
  MySQL's `ONLY_FULL_GROUP_BY` mode and SQLite without extra
  workarounds; worth revisiting with a normalized column if it matters
  for real usage.
- **Daily/Monthly Reports** are zero-filled for the full 14-day/12-month
  window, so the chart never has a misleading gap for a day with no
  reports.

## Auth endpoints

| Method | Path                          | Auth required | Purpose |
|--------|-------------------------------|----------------|---------|
| POST   | `/api/v1/auth/register`       | No             | Create an account, returns a token (auto-login) |
| POST   | `/api/v1/auth/login`          | No             | Sign in, returns a token |
| POST   | `/api/v1/auth/forgot-password`| No             | Request a reset link — emailed via SMTP if configured, otherwise logged to console |
| POST   | `/api/v1/auth/reset-password` | No             | Consume the token, set a new password |
| GET    | `/api/v1/auth/me`             | Yes (Bearer)   | Get the signed-in user's profile |
| POST   | `/api/v1/auth/logout`         | Yes (Bearer)   | No-op server-side (JWTs are stateless); exists for a consistent frontend contract |

**Login/register request bodies** use `email` + `password` (+ `remember_me`
for login). A password must be 8+ characters with at least one letter
and one number. `remember_me: true` issues a 7-day token instead of the
default 1-hour one (`REMEMBER_ME_EXPIRE_MINUTES` in `.env`).

**Protected routes** (this module's `/auth/me`, and every future
search/report/admin route) depend on `get_current_user` from
`app/api/deps.py` — call it with `Depends(get_current_user)` and it
resolves the `User` row for you, or raises 401.

## Email (forgot-password)

`app/services/email_service.py` sends the reset link over SMTP if
`SMTP_HOST`, `SMTP_USER`, and `SMTP_PASSWORD` are all set in `.env`.
If any are blank, or if sending fails for any reason, it falls back to
printing the link to the console — so this always works, with or
without real mail credentials.

To use Gmail: enable 2-Step Verification on the account, generate an
**App Password** (not your normal password) at
https://myaccount.google.com/apppasswords, and set:

```
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your.address@gmail.com
SMTP_PASSWORD=the-16-character-app-password
```

Any other SMTP provider (Outlook, SendGrid's SMTP relay, or an internal
RINL mail server) works the same way — just swap in its host/port/credentials.

## How to test

1. Start MySQL and create an empty `newspulse` database (or run `database/schema.sql`).
2. `uvicorn app.main:app --reload`
3. Open http://localhost:8000/docs
4. Try `POST /auth/register` with a body like:
   ```json
   { "full_name": "Shriya Reddy", "email": "shriya@vizagsteel.com", "password": "Steel1234" }
   ```
   You should get back a 201 with an `access_token`.
5. Click **Authorize** in Swagger, paste the token, then call `GET /auth/me` — it should return your profile.
6. Try `POST /auth/login` with the wrong password — expect a 401.
7. Try registering the same email twice — expect a 409.
8. Try `GET /news/search?keyword=steel&language=en` — with no API keys configured, this runs on the Google News RSS fallback and should return real, current articles about steel. Check `provider_used` in the response — it'll say `"google_rss"`.
9. Try `GET /news/tags` — you should see the 23 predefined tags. `POST /news/tags` with `{"tag": "test tag"}`, then confirm it shows up in a repeat `GET /news/tags` call, then `DELETE` it.
10. Search for something, copy 1-2 articles from the response into a `POST /reports/generate` body (see format above), and confirm you get back a `download_url`.
11. `GET` that download URL (with your Bearer token set in Swagger's Authorize) — it should return a real PDF. Open it and confirm the cover page, article content, header/footer, and page number all look right.
12. `GET /reports` — should list the report you just generated.
13. Try downloading another user's report ID while authenticated as yourself — expect a 404, not the file.
14. Promote your test user to admin via the SQL above, log in again (to be safe), then `GET /admin/dashboard` — you should see your searches/reports reflected in the stats and charts. Try it with a non-admin token first — expect a 403.

## How to verify

- `SELECT * FROM users;` in MySQL should show your new row with a bcrypt hash in `password_hash` (never plaintext).
- `POST /auth/forgot-password` with a registered email — if SMTP is configured, check that inbox; otherwise check the **uvicorn console log**, which prints the reset link instead.
- Copy the token from that logged link into `POST /auth/reset-password` and confirm you can then log in with the new password.

## Folder structure

```
backend/
├── app/
│   ├── main.py            # FastAPI app instance, CORS, router registration, startup table creation
│   ├── core/
│   │   ├── config.py      # Environment-driven settings (Pydantic Settings)
│   │   └── security.py    # Password hashing (bcrypt) + JWT encode/decode
│   ├── db/
│   │   ├── database.py    # SQLAlchemy engine/session
│   │   └── seed_data.py   # Newspaper/edition seed data (read once, on first startup)
│   ├── models/
│   │   ├── user.py        # User, PasswordResetToken ORM models
│   │   ├── tag.py         # CustomTag ORM model
│   │   ├── search_history.py # SearchHistory ORM model
│   │   ├── report.py      # Article, Report, report_articles ORM models
│   │   └── newspaper.py   # Newspaper, NewspaperEdition ORM models
│   ├── schemas/
│   │   ├── auth.py        # Register/Login/Token/etc. Pydantic schemas
│   │   ├── news.py        # Search/Article/Tag Pydantic schemas
│   │   ├── report.py      # Report generation request/response schemas
│   │   └── admin.py       # Admin dashboard response schemas
│   ├── templates/
│   │   └── report_template.html # Jinja2 HTML template rendered to PDF
│   ├── services/
│   │   ├── auth_service.py  # Business logic: register, authenticate, password reset
│   │   ├── email_service.py # SMTP send for reset links, with console fallback
│   │   ├── tag_service.py   # Predefined + custom tag logic
│   │   ├── pdf_service.py   # Jinja2 render + WeasyPrint PDF generation
│   │   ├── report_service.py # Report orchestration: cache articles, create Report, render PDF
│   │   ├── admin_service.py # All admin dashboard aggregation queries
│   │   ├── newspaper_service.py # DB-backed language/newspaper/edition cascade + startup seeding
│   │   └── news/
│   │       ├── base.py               # BaseNewsProvider interface + NormalizedArticle
│   │       ├── gnews_provider.py     # Primary provider
│   │       ├── newsdata_provider.py  # Secondary provider
│   │       ├── google_rss_provider.py# No-key fallback provider
│   │       └── aggregator.py         # Tries providers in order, applies date filter
│   ├── utils/
│   │   └── newspaper_sources.py # Static newspaper/edition/predefined-tag reference data
│   └── api/
│       ├── deps.py         # get_current_user / get_current_admin_user dependencies
│       └── routes/
│           ├── health.py   # GET /health
│           ├── auth.py     # All /auth/* routes
│           ├── news.py     # All /news/* routes
│           ├── reports.py  # All /reports/* routes
│           └── admin.py    # All /admin/* routes
├── requirements.txt
├── .env.example
└── .gitignore
```

This layout keeps **routes** (HTTP layer), **schemas** (validation
layer), **services** (business logic), and **models** (data layer)
separate, so future modules (search, reports, admin) each drop into
the same folders without restructuring.

