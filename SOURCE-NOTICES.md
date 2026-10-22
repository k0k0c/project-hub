# Source and bundled dependency notices

Project Hub source: https://github.com/k0k0c/project-hub.

No project-wide source license is declared in this repository. Plugin metadata
does not assert an SPDX license for that source.

The local browser dependencies include their original licenses and pinned
upstream/source links in `tools/project-portal/web/vendor/README.md` and the
sibling LICENSE files. This includes Cytoscape, fCoSE/layout-base/cose-base,
ELK, Lucide, marked, DOMPurify and highlight.js. Those notices are distributed
with the runtime. No CDN is needed at runtime.

Optional parallel server dependencies are pinned in `requirements-server.txt`:
Uvicorn (BSD-3-Clause, https://github.com/Kludex/uvicorn), Click (BSD-3-Clause,
https://github.com/pallets/click), and h11 (MIT, https://github.com/python-hyper/h11).
Their installed package metadata contains the upstream license texts. The
source distribution ships the requirements and notices. The Windows installer
bundles these packages and their original license metadata.

ChatGPT sign-in uses PyJWT (MIT, https://github.com/jpadilla/pyjwt) and
cryptography (Apache-2.0 OR BSD-3-Clause, https://github.com/pyca/cryptography),
with cffi (MIT, https://github.com/python-cffi/cffi) and pycparser
(BSD-3-Clause, https://github.com/eliben/pycparser). Versions are pinned in
`requirements-server.txt`; installed wheel metadata retains their license texts.
Cryptographic dependencies bundled in cryptography retain its upstream notices.

Desktop dependencies are pinned in `requirements-desktop.txt`: pystray
(LGPL-3.0, https://github.com/moses-palmer/pystray) and six
(MIT, https://github.com/benjaminp/six). Icon rendering uses Pillow, pinned with
image dependencies in `requirements-images.txt` (HPND,
https://github.com/python-pillow/Pillow). Their upstream license files are kept
with the installed package metadata in the private runtime.

The handoff builder normalizes UTF-8 text to LF without changing JavaScript
semantics. `distribution.json` records the distributed hashes; vendor README
distinguishes the original layout-base CRLF hash from the LF distribution hash.
