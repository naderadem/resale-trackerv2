# Inspecting Grailed's search page with devtools

Goal: see exactly what network requests the Grailed search page makes when
you search and filter, so you know what's publicly served (and how) before
writing any code against it. This is manual, read-only inspection of your
own browser session -- it doesn't touch robots.txt-disallowed paths itself,
though note that `/search` (the page you're about to load) is one of the
paths Grailed's robots.txt disallows for crawlers -- see
`docs/grailed_robots.txt`. Keep that in mind while deciding what, if
anything, to automate afterward.

## Steps (Chrome / Edge / Brave -- Firefox and Safari are equivalent, noted below)

1. Open a new browser tab and open DevTools (`Cmd+Option+I` on Mac,
   `F12` or `Ctrl+Shift+I` on Windows/Linux).
2. Go to the **Network** tab in DevTools.
3. Check the box to **Preserve log** (top of the Network panel) so requests
   survive page navigations.
4. In the filter/search box at the top of the Network panel, type `fetch/xhr`
   (Chrome shows this as a filter chip) to hide static assets (JS, CSS,
   images, fonts) and only show API-style calls.
5. Navigate to `https://www.grailed.com/` and log in if you normally would --
   but note results may differ logged-out, which matters if you want this to
   work without a Grailed account.
6. Type a search, e.g. "rick owens geobasket", and press enter.
7. Watch the Network panel populate. Look for requests that:
   - Go to a different host than `www.grailed.com` (Grailed's search is
     commonly backed by a third-party search service -- look for a host
     like `*.algolia.net` or similar; the exact provider may have changed,
     which is exactly what this inspection is for).
   - Have a response `Content-Type` of `application/json`.
8. Click on a promising request. In the right-hand panel:
   - **Headers** tab: note the request URL, method, and any custom headers
     (especially anything like `X-Algolia-API-Key`, `X-Algolia-Application-Id`,
     or an `Authorization` header -- these tell you whether the request is
     using a public, front-end-embedded key or something session-specific).
   - **Payload / Request** tab: see what query parameters or JSON body was
     sent (the search term, filters, pagination).
   - **Response** tab: see the actual JSON returned -- this is the shape
     you'd be parsing if you built an adapter around it.
9. Apply a filter on the page (e.g. size, price range) and repeat -- compare
   the new request's payload to see how filters map to query parameters.
10. Right-click the request in the list -> **Copy** -> **Copy as cURL** to
    save a reproducible copy of the exact request (headers, cookies, and all)
    for later reference. Careful: this will include your session cookie/auth
    header if one was sent -- treat that copied command as a secret, don't
    paste it anywhere shared.

### Firefox
Same idea: DevTools (`Cmd+Option+I` / `F12`) -> **Network** tab -> filter by
`XHR` -> perform the search -> click a request -> **Headers** / **Request** /
**Response** tabs. Firefox's "Copy as cURL" is in the same right-click menu.

### Safari
Enable the Develop menu (Preferences -> Advanced -> "Show Develop menu"),
then Develop -> Show Web Inspector -> **Network** tab -> filter by `XHR`.

## What to look for / decide afterward

- **Is the search backed by a first-party endpoint on grailed.com, or a
  third-party service** (e.g. Algolia)? This changes both what robots.txt
  applies (Grailed's robots.txt governs grailed.com paths, not a third-party
  search host) and what a Terms-of-Service review needs to cover.
- **Does the request require an API key or token?** If so, is it a public
  key visibly embedded in the page's JS bundle (common for client-side
  Algolia setups), or something tied to your logged-in session? A key
  that's shipped to every visitor's browser is a different situation than
  one that's part of your personal, authenticated session.
- **Does it work logged out?** If the search only returns results when
  you're authenticated, that's a strong signal against automating it outside
  a real, personal, logged-in browsing session.
- **Rate/volume**: whatever you find, this project's whole design point is
  low request volume (shared rate limiter + on-disk cache, see
  `common/rate_limiter.py` and `common/cache.py`) -- so even a green light
  here should still mean occasional, cached, polite requests, not polling.

Once you've done this and decided how (or whether) to proceed, come back to
`sources/grailed.py` and implement `GrailedSource` -- it currently just
raises `NotImplementedError`.
