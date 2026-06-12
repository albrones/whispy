## Context

Whispy is a macOS-only Python daemon. The promotional website is intentionally decoupled from the application runtime: it is plain static HTML/CSS/JS with no build pipeline, so it can be hosted anywhere (GitHub Pages, Vercel, S3) and reviewed/tested without a Node toolchain. The next TODO item (CI/CD to Vercel) will consume this `website/` directory as its deploy root.

## Goals / Non-Goals

- **Goals**: Zero-dependency static site, brand-consistent, responsive, accessible, testable from the existing Python/pytest suite.
- **Non-Goals**: No CMS, no analytics, no JS framework, no localization, no actual binary download hosting (links point to the GitHub repo / install script). Deployment configuration is out of scope (next TODO).

## Decisions

- **Plain static files over a framework**: A landing page does not justify a Node build step; plain files keep the repo testable in pytest and trivially deployable. Trade-off: manual HTML, but content is small and stable.
- **Directory `website/`**: Clear, conventional, and a natural Vercel "root directory" for the next task.
- **Brand**: Reuse the in-app accent `#24bf9e` (from `waveform_window.py`) on a dark theme (`~#121217`) so the site matches the product UI.
- **Testing approach**: Since there is no JS test harness, validate the site from Python — assert `index.html` exists, contains the brand name, brand color, required section anchors, the GitHub link, and that every locally-referenced `href`/`src` asset exists on disk. This catches broken asset paths (the most common static-site regression) without a browser.
- **Reduced motion**: Gate the waveform animation behind `prefers-reduced-motion` and a feature check so the page is accessible and degrades gracefully.

## Risks / Trade-offs

- Manual HTML can drift from the README content. Mitigation: keep copy minimal and source-of-truth links pointing at the repo.
- Python-side tests cannot verify visual rendering. Mitigation: structural assertions cover the high-value regression (missing/renamed assets, dropped sections); visual review is manual.
