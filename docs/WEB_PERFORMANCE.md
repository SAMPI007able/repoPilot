# Web performance budget and degradation policy

The application targets the Core Web Vitals “good” thresholds at the 75th percentile:

- Largest Contentful Paint (LCP): **2.5 seconds or less**
- Interaction to Next Paint (INP): **200 milliseconds or less**
- Cumulative Layout Shift (CLS): **0.1 or less**

These are field targets, not claims based on a local build. Release validation should use production RUM plus a Lighthouse mobile run with Slow 4G and 4× CPU throttling.

## Production bundle baseline

Measured with `npm run build` on 2026-10-17. Before this pass the main JavaScript output was 568.86 kB (188.00 kB gzip). After route/component splitting, the entry is 104.55 kB (39.84 kB gzip), with the Vue runtime at 62.43 kB (24.51 kB gzip), the home route at 20.28 kB (7.18 kB gzip), and the workspace store at 8.82 kB (3.19 kB gzip). The initial home-route JavaScript is therefore roughly 74.7 kB gzip plus sub-kilobyte shared icon chunks, about 60% below the prior main bundle.

Large optional dependencies are isolated from initial navigation:

- PostHog: 227.73 kB (75.34 kB gzip), loaded during browser idle time.
- OIDC client: 68.87 kB (17.45 kB gzip), loaded at idle for public navigation or immediately for protected routes.
- CKEditor: 864.39 kB JavaScript (229.09 kB gzip) and 273.10 kB CSS (41.01 kB gzip), loaded only when a support user enables rich formatting.
- Support route shell: 6.65 kB (2.87 kB gzip).
- Dependency graph worker: 2.57 kB, outside the main thread.

The main stylesheet is 77.39 kB (15.23 kB gzip). Remote Google Fonts were removed; the UI uses the local system font stack and therefore has no render-blocking font request.

## Runtime and network rules

- Public navigation does not wait for authentication or feature-flag requests. Protected routes still wait for authentication before rendering.
- Unverified users only perform the identity check required to determine verification state; workspace and feature-flag calls stay gated.
- Analytics initialization and queued events wait for idle time and are not part of LCP.
- Hashed `/assets/` responses use one-year immutable caching in both Nginx and Vercel. HTML uses `no-cache` so deployments are discovered promptly.
- API responses over 1 kB use gzip at compression level 5. Event streams remain streamable.
- Repository-provider results no longer add a cache-busting timestamp unless the user explicitly presses Refresh.
- Provider avatars decode asynchronously and non-critical avatars use low fetch priority.

## Progressive degradation thresholds

- Repository browsing renders 50 rows at a time. Users can reveal the next batch without paying the DOM/layout cost up front.
- Graph layout runs in a Web Worker. A synchronous fallback exists for older browsers.
- Graph search waits 120 ms after typing, pan updates are coalesced to animation frames, and transient hover highlighting is disabled above 750 visible nodes. Click and keyboard selection remain available.
- Graph labels use semantic zoom: short labels are suppressed above 250 nodes until zoomed; full labels are suppressed above 90 nodes until zoomed.
- Preview event refreshes coalesce into at most one state/log refresh per 750 ms and retain only the latest 200 events.
- Workspace build polling backs off from 600 ms to 2 seconds and uses 5 seconds while the page is hidden.
- Below-the-fold sections use `content-visibility: auto`. Reduced-motion preferences disable non-essential motion, and small screens avoid full-surface backdrop blur.

## Release checks

1. Run `npm run build` and fail review if the initial home-route gzip total grows by more than 10% without an explicit exception.
2. Run Lighthouse mobile against the production build, not the Vite development server.
3. Exercise a large repository graph while recording Chrome Performance. Confirm layout computation occurs in `graphLayout.worker`, pointer interactions do not produce long tasks over 50 ms, and detached component instances do not grow across route changes.
4. Verify static assets return `Cache-Control: public, max-age=31536000, immutable`, HTML returns `no-cache`, and API JSON over 1 kB includes `Content-Encoding: gzip` when the client advertises it.
5. Track p75 LCP and INP in production RUM by release and device class. A regression above the targets blocks promotion even if the synthetic build budget passes.
