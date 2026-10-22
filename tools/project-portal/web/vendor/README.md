# Local browser dependencies

- Lucide 0.468.0, `dist/umd/lucide.min.js`: https://github.com/lucide-icons/lucide - ISC; see lucide.LICENSE. Retrieved from pinned unpkg npm distribution on 2026-09-19; used for UI controls and status icons.

Pinned distributions are committed alongside the viewer: no CDN calls or package installation are needed to use the hub.

- Cytoscape.js 3.33.1, `dist/cytoscape.min.js`: https://github.com/cytoscape/cytoscape.js/tree/v3.33.1 — MIT; see cytoscape.LICENSE. Retrieved from the tagged upstream distribution on 2026-10-02. SHA-256: `f55947f3daa3bae53209d4b885c195c157f595c225e508a6b382598d9452d6e2`. Used for the architecture graph, native interaction and directed layouts.

- marked 18.0.12, `lib/marked.umd.js`: https://github.com/markedjs/marked — MIT; see marked.LICENSE.
- DOMPurify 3.4.15, `dist/purify.min.js`: https://github.com/cure53/DOMPurify — see purify.LICENSE.
- highlight.js 11.12.0, common browser bundle from `@highlightjs/cdn-assets`: https://github.com/highlightjs/highlight.js — BSD-3-Clause; see highlight.LICENSE.

Files retrieved from version-pinned npm distributions through jsDelivr on 2026-09-12. Versions recorded in versions.json. Upgrade deliberately, preserving licenses, and recheck Markdown sanitization and rendering. Markdown HTML is sanitized before insertion. Images/embedded media/forms and inline styles are disabled in this viewer; external links require an explicit click.

- layout-base 2.0.1 — MIT; upstream source: https://github.com/iVis-at-Bilkent/layout-base/tree/v2.0.1. Retrieved from version-pinned official npm distributions on 2026-10-02. `layout-base.js` SHA-256: `ec15ab5df9af3f20708f4faab994accf91cda71848cd5bb10a23432cc50b6745`. License included as layout-base.LICENSE.

  That hash identifies the original CRLF bytes. Git's canonical LF bytes and the
  local handoff ZIP have SHA-256 `f5c66be21c9cca16c4f25a576bffbd16ed1a48181c1c2dcbb8d905ec822e76b5`.
  The handoff builder normalizes UTF-8 text to LF and records actual distributed
  hashes in `distribution.json`; this changes line endings only.

- cose-base 2.2.0 — MIT; upstream source: https://github.com/iVis-at-Bilkent/cose-base/tree/v2.2.0. Retrieved from version-pinned official npm distributions on 2026-10-02. `cose-base.js` SHA-256: `7cae9509bd36235a63a85e71c8d9fa2cd0bc1d0c1ecc5b5a737976f39d040ddf`. License included as cose-base.LICENSE.

- cytoscape-fcose 2.2.0 — MIT; upstream source: https://github.com/iVis-at-Bilkent/cytoscape.js-fcose/tree/v2.2.0. Retrieved from version-pinned official npm distributions on 2026-10-02. `cytoscape-fcose.js` SHA-256: `4b1cab218d74996aa59cd8473f9239cc6398b8c1774d84d7e59ad9a68959cb57`. License included as cytoscape-fcose.LICENSE.

- elkjs 0.11.0 — EPL-2.0; upstream source: https://github.com/kieler/elkjs/tree/releases/0.11.0. Retrieved from version-pinned official npm distributions on 2026-10-02. `elk-api.js` SHA-256: `5ba557441d2b9c0fca02174f4f11d741ae980b258dcd67cfe331273f14d6dfde`. `elk-worker.min.js` SHA-256: `c0dc844ac1739a1e1e4f64d08a9ec4594818d5aa7e0cb26e5096b6d34b864e2b`. License included as elk.LICENSE.md.

fCoSE computes compound/card geometry. ELK Layered computes directed placement and orthogonal edge bend points in a local Web Worker; the worker is loaded on demand. The upstream assets are unchanged, committed locally, and make no CDN requests at runtime. The EPL source and notices are available at the pinned ELK source link above.
