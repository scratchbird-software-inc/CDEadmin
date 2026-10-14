# Open-source site source

`index.html` and `assets/site.css` form a buildless GitHub Pages site. Publish
from `master` and `/docs` after the reviewed source commit is pushed. The
`.nojekyll` file preserves static files without a Jekyll transformation.

The site must reflect the dated status in `en_US/implementation_status.rst`.
It describes development access, not a release download. The commercial
ScratchRobin product page is a separate destination. Never add credentials,
local test fixtures or generated Sphinx output to this directory.
