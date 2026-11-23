# Palaverde event calendar

A static, mobile-first Italian event calendar with an English toggle. Venue details, map coordinates, event feed, affiliate links, sponsor checkout, and SEO copy are centralized in `venue.json`. The same project can be copied for another venue by editing that file and its event-source list.

## Before launch

1. Edit `venue.json`: set `canonicalUrl` to the actual HTTPS domain; confirm address and coordinates; add ticket and hotel affiliate URLs; replace the sponsor URL with your Stripe Payment Link or self-serve form; add a real contact and privacy/cookie pages as needed.
2. Add approved event listing URLs to `scripts/sources.json`. The scraper reads public Schema.org `Event` JSON-LD. The initial URLs are discovery starting points, not guaranteed event feeds. Check each provider's terms and `robots.txt`, use actual schedule or event-detail URLs, and do not scrape pages that prohibit it. The script never bypasses login, bot protection, or access controls.
3. For sources without event JSON-LD, use a documented public feed/API or add a source-specific parser only after checking its terms. Team and ticketing site layouts can change, so review Actions output weekly.
4. Update the canonical URL in the `<link rel="canonical">` in `index.html` when publishing. Add a custom domain and HTTPS in the hosting settings. Add `sitemap.xml` and verify the site in Google Search Console after launch.

## Beginner deployment: GitHub Pages

1. Create a free GitHub account, then create a new **public** repository. Give it a simple name such as `palaverde-calendar`.
2. Upload this project's files and folders to the repository root (`index.html`, `venue.json`, `events.json`, `scripts/`, `.github/`, and `requirements.txt`). Commit the upload.
3. Open **Settings → Pages**. Under **Build and deployment**, choose **Deploy from a branch**, select `main` and `/(root)`, then save. GitHub will show the live URL after it publishes.
4. Open that URL on a phone and check the language switch, filters, map, and calendar download. The site fetches its JSON files, so use the published `https://` URL; opening `index.html` directly from your computer will not load the config correctly.
5. In **Settings → Actions → General**, allow the repository's GitHub Actions to run and commit changes. Open **Actions → Update Palaverde events → Run workflow** once to try the scraper. The recurring workflow runs Mondays at 05:00 UTC. Once source URLs are configured and the workflow succeeds, its commits update the published calendar.
6. For a custom domain, add it under **Settings → Pages → Custom domain**, follow GitHub's DNS instructions at your domain provider, wait for HTTPS provisioning, and set the same domain in both canonical URL locations.

## Alternative: Vercel

1. Push the project to GitHub as above and create a free Vercel account.
2. Choose **Add New → Project**, import the repository, and leave the framework preset as **Other**. This is a static site: no build command and no output directory are needed.
3. Deploy. Vercel supplies a live `.vercel.app` URL. Set `venue.canonicalUrl` and the canonical link in `index.html` to that URL, commit the change, and Vercel will redeploy.
4. Keep GitHub Actions enabled for the weekly event data refresh, or use the Vercel domain settings to connect a custom domain.

## Local scraper use

Python 3.10+ is required. From the project directory, install `requirements.txt` and run `python scripts/scrape_events.py`. It writes `events.json` and `events.ics`. Events without a confirmed date are excluded. Failed sources are recorded in the JSON and printed in the run log. An empty result can mean a source has no public JSON-LD feed; configure permitted event detail pages or a documented feed before relying on automation.

## Monetization and operations

- Set `affiliates.tickets.urlTemplate` / `hotels.urlTemplate` to affiliate URL templates containing `{event}` and optionally `{venue}`, or use their fallback URLs. The event's official `ticketUrl` takes precedence for the ticket button; configure affiliate redirects on your own domain if you need commission tracking on every ticket click.
- Create a Stripe Payment Link for the sponsor placement, or a self-serve form, and replace `sponsor.url`. Do not advertise an unconfigured payment placeholder as a live booking flow.
- The three ad containers are reserved. `ads.enabled` is false until you have an approved AdSense account and publisher/slot IDs; wire those values only after approval.
- Confirm ticket prices, dates, postponements, and venue details with the official organizer. This independent calendar is not affiliated with the arena or teams.

## Event data format

`events.json` has an `events` array. Each event can include `title` (string or `{ "it": "…", "en": "…" }`), `startDate` (ISO 8601), `endDate`, `description`, `category` (`basket`, `volley`, or `concert`), `venue`, `location`, `ticketUrl`, and `sourceUrl`. `events.ics` is the downloadable calendar for all collected events.
