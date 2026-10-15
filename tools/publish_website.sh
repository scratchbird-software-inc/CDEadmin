#!/usr/bin/env bash
set -euo pipefail

repo_root=$(git rev-parse --show-toplevel)
cd "$repo_root"

if [[ $(git branch --show-current) != master ]]; then
    echo 'Publish from master only.' >&2
    exit 1
fi
if [[ -n $(git status --porcelain) ]]; then
    echo 'Commit or remove working-tree changes before publishing.' >&2
    exit 1
fi
if [[ ! -f website/index.html || ! -f website/.nojekyll ]]; then
    echo 'The website source is incomplete.' >&2
    exit 1
fi

git fetch origin master gh-pages 2>/dev/null || git fetch origin master
if [[ $(git rev-parse HEAD) != $(git rev-parse origin/master) ]]; then
    echo 'Push master and recheck origin before publishing.' >&2
    exit 1
fi

site_commit=$(git subtree split --quiet --prefix=website HEAD)
git push origin "$site_commit:refs/heads/gh-pages"
echo "Published website subtree $site_commit to origin/gh-pages."
