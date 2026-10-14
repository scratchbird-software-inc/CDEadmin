# Open-source site source

`index.html` and `assets/site.css` form a buildless GitHub Pages site. The
reviewed source lives in `master:website/`. GitHub's branch publisher only
accepts a repository root or `/docs`, so the published `gh-pages` branch is a
derived copy of this directory at its root. The `.nojekyll` file is included.

After committing and reviewing a change on `master`, publish the exact
committed `website/` subtree with `tools/publish_website.sh`. The script
requires a clean `master` checkout and performs a fast-forward-only push to
`origin/gh-pages`. The Pages setting must remain `gh-pages` at `/`.

The repository currently limits Actions to local actions. Its existing
workflows that call external actions end in startup failures, so site
publication does not depend on an Actions workflow.

The site must reflect the dated status in `../docs/en_US/implementation_status.rst`.
It describes development access, not a release download. The commercial
ScratchRobin product page is a separate destination. Never add credentials,
local test fixtures or generated Sphinx output to this directory. Keep
documentation source in `docs/`, separate from this site.
