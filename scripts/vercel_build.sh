#!/bin/sh
# Vercel build: copy the static guided page and explorer into dist/.
set -e
ORIGIN=https://ubi.josolon.com
rm -rf dist && mkdir dist
cp artifacts/explorer_v3/*.js artifacts/og.png dist/
cp artifacts/guided/index.html dist/index.html
cp artifacts/explorer_v3/index.html dist/explorer.html
# Canonical URL and link-preview tags, after each page's <title>.
tags() {
  printf '<link rel="canonical" href="%s"><meta property="og:type" content="website"><meta property="og:url" content="%s"><meta property="og:title" content="%s"><meta property="og:description" content="Interactive results from the Iceland UBI agent-based model"><meta property="og:image" content="%s/og.png"><meta property="og:image:width" content="1200"><meta property="og:image:height" content="630"><meta name="twitter:card" content="summary_large_image"><meta name="twitter:image" content="%s/og.png">' "$1" "$1" "$2" "$ORIGIN" "$ORIGIN"
}
sed -i "0,/<\/title>/s#</title>#</title>$(tags "$ORIGIN/" "Borgaralaun Guide")#" dist/index.html
sed -i "0,/<\/title>/s#</title>#</title>$(tags "$ORIGIN/explorer" "Borgaralaun Explorer")#" dist/explorer.html
# Vercel Web Analytics: cookieless visitor counts.
for f in dist/index.html dist/explorer.html; do
  printf '<script defer src="/_vercel/insights/script.js"></script>\n' >> "$f"
done
# For search engines.
printf 'User-agent: *\nAllow: /\nSitemap: %s/sitemap.xml\n' "$ORIGIN" > dist/robots.txt
cat > dist/sitemap.xml <<XML
<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>$ORIGIN/</loc></url>
  <url><loc>$ORIGIN/explorer</loc></url>
</urlset>
XML
