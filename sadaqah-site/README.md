# SADAQAH — faith, home & community

A functional, mobile-first multi-page Islamic store **preview**, built with FastAPI, Jinja, SQLAlchemy, vanilla JavaScript and CSS. It can be hosted on Railway with a Railway PostgreSQL database.

## What is included

- Home page with photography, category collections, featured goods and three editable **What's on this week** feature cards.
- `/shop`: 21 example products across six categories, with CAD prices, search and category filters. Individual product detail pages.
- `/new-to-islam`: compassionate new Muslim guidance, books and mentor-interest link.
- `/about`, `/contact`, `/privacy`: complete editable copy.
- Local-storage shopping basket and inquiry-based checkout **without taking payment**.
- `/inquire`: general, catering, bulk/event, mentor and product inquiries. Client-side and server-side validation, CSRF, a spam trap, an in-memory rate limit, consent and required fields. **Valid submissions are saved to the SQL database**.
- `/thank-you`: confirmation of receipt, not an order or booking confirmation.
- `/admin/login`: password-protected store owner sign-in. `/admin`: private inquiry table (status changes, CSV export), editable weekly features, editable weekday opening/closing times.
- `/api/status`: timezone-aware open/closed status calculated from the current weekly schedule. Header updates every 60 seconds.

## Before public launch

This site uses **example products, sample prices, sample hours and illustrative free-use photographs**. Replace these with real inventory, opening times, shop contact details and your business policies. No merchant account or payment gateway is connected. No real catering dates or mentorship matches are guaranteed by the preview. The privacy page is a draft that needs local legal review.

### Local development

```bash
cd sadaqah-site
python -m venv .venv
# activate .venv using your OS's method
pip install -r requirements.txt
cp .env.example .env
# Load variables from .env in your shell; FastAPI does not automatically load this file.
export ADMIN_PASSWORD='create-a-long-unique-password'
export SECRET_KEY='create-a-separate-long-random-secret'
uvicorn app:app --reload
```

Then open `http://localhost:8000` and `http://localhost:8000/admin/login`.

The local setup uses SQLite at `data/sadaqah.db` unless `DATABASE_URL` is set. A SQLite file is **not** safe to rely on for durable Railway data without a persistent volume. For production, use PostgreSQL.

### Recommended Railway deployment

1. Create a **Railway project**, add a **PostgreSQL service**, and deploy this folder as the web service (from GitHub or the Railway CLI). The included `Dockerfile` supports a standard Railway deployment.
2. In the web service, configure `DATABASE_URL` to reference the Railway PostgreSQL service (typically `${{Postgres.DATABASE_URL}}` in Railway's variables interface; select the actual service name from Railway). This application accepts `postgresql://` and `postgres://` URLs and uses psycopg.
3. Set `ADMIN_PASSWORD` to a long private password and `SECRET_KEY` to an independent cryptographically random 32+ byte value. Set `STORE_TIMEZONE` to the store's location, e.g. `America/Regina`, and `PUBLIC_BASE_URL` to the final `https://` website URL to enable HTTPS-only session cookies.
4. Generate a Railway public domain, verify `/health`, the catalog, the `/api/status` response, form submission and the authenticated `/admin` inbox. Verify submissions persist across **redeploys**.
5. Connect your custom domain, update the sample catalog, business location, true hours, policies, event offerings, and arrange database backups. Do not expose the administrator password publicly.

Run tests using `python -m pytest -q` (install `pytest`, `httpx`, and `beautifulsoup4` for the test suite).

### Product and page edits

- Edit `products.py` to change product names, pricing (CAD), descriptions, tags and representative photography.
- Edit HTML copy in `templates/`.
- Use `/admin` to update three weekly special cards, visibility, opening hours, and inquiry statuses.
- Change `STORE_TIMEZONE` to match the actual store.
- To send notifications by email, integrate a transactional email provider; this preview deliberately saves inquiries to the admin inbox only.

### Photographs

The website uses **real, illustrative** photographs via `images.unsplash.com` URLs and links to the [Unsplash License](https://unsplash.com/license). Photo subjects include Qur’ans and stands by GR Stocks and Tahmeed Ahmad, Islamic books by Indra Projects and Rachid Oucharia, perfume bottles by yousef samuil, prayer rugs by Wildan Ramdani Akbar and beads by Shedrack Salami. They are not photos of SADAQAH's specific merchandise. Original photo pages:

- https://unsplash.com/photos/brown-book-on-brown-wooden-table-sIpVwr9SbF8
- https://unsplash.com/photos/blue-and-white-book-on-brown-wooden-table-YvRnUCc70Rs
- https://unsplash.com/photos/the-holy-quran-resting-on-a-wooden-stand-lst1ik_wXk0
- https://unsplash.com/photos/books-lined-up-on-a-shelf-4FnxDuzPbTU
- https://unsplash.com/photos/brown-and-black-hardbound-book-D4jS3ZV8nbc
- https://unsplash.com/photos/four-colorful-perfume-bottles-with-decorative-caps-tSyrOEW7iF0
- https://unsplash.com/photos/prayer-rugs-displayed-for-sale-outside-a-shop-Iu8twd5pAbo
- https://unsplash.com/photos/a-close-up-of-a-person-holding-a-ring-DRjeesi2kFM

## Security and operations notes

- Administrators must configure a nonempty `ADMIN_PASSWORD`; no default admin password exists.
- Session cookies are signed using `SECRET_KEY`; set `PUBLIC_BASE_URL=https://...` to make them Secure over HTTPS.
- CSRF validation covers mutating admin operations and public inquiries. Displayed form content is HTML escaped. CSV exports mitigate spreadsheet formula injection.
- Maintain appropriate business privacy policies, privacy contact information, database backups, software patching, and secrets management before public launch.
- Store may need anti-bot protections, stronger distributed rate-limiting and email sending as traffic grows.
