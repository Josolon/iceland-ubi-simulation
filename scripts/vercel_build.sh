#!/bin/sh
# Vercel build: copy the static guided page and explorer into dist/.
set -e
rm -rf dist && mkdir dist
cp artifacts/explorer_v3/*.js dist/
cp artifacts/guided/index.html dist/index.html
cp artifacts/explorer_v3/index.html dist/explorer.html
# Vercel Web Analytics: cookieless visitor counts.
for f in dist/index.html dist/explorer.html; do
  printf '<script defer src="/_vercel/insights/script.js"></script>\n' >> "$f"
done
