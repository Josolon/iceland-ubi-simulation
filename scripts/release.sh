#!/bin/sh
# Release a version to the public repository: one commit on top of public/main carrying this branch's tree, a tag,
# and a GitHub release whose notes are the CHANGELOG's section for the version.
#
#     sh scripts/release.sh 2.1.1            # dry run: checks everything, builds the commit and tag locally, pushes nothing
#     sh scripts/release.sh 2.1.1 --push     # the same, then pushes main and the tag and creates the GitHub release
#
# The public repository has its own history (each release is one commit), so the release commit is made with
# commit-tree on top of public/main rather than by merging. Before 2.1.0, public/main had moved on its own (the
# link-preview image, canonical and sitemap tags): the script refuses to release while public/main has files this
# branch does not carry. It never force-pushes; if public/main moves between the fetch and the push, the push fails.
set -eu
V=${1:?usage: release.sh VERSION [--push]}
PUSH=${2:-}
BRANCH=$(git rev-parse --abbrev-ref HEAD)
PY=${PY:-../iceland-ubi-simulation/.venv/bin/python}
die() { echo "release: $*" >&2; exit 1; }

# 1. the tree is what gets released, so nothing tracked may be uncommitted
git diff --quiet && git diff --cached --quiet || die "uncommitted changes to tracked files on $BRANCH"

# 2. the version is the same everywhere it is written
grep -q "<small class=\"ver\">$V</small>" artifacts/explorer_v3/index.html || die "the Explorer page does not say $V"
grep -q "^version: \"$V\"" CITATION.cff || die "CITATION.cff does not say $V"
grep -q "^## $V (" CHANGELOG.md || die "CHANGELOG.md has no '## $V (date)' heading"
git rev-parse -q --verify "refs/tags/v$V" >/dev/null && die "a local tag v$V exists"

# 3. the checks
$PY -m unittest discover tests >/dev/null 2>&1 || die "the tests fail: $PY -m unittest discover tests"
$PY scripts/build_stamp.py check || die "a page file is stale"

# 4. public/main: anything there that this branch does not carry would be removed by the release
git fetch -q public
git ls-remote --exit-code --tags public "refs/tags/v$V" >/dev/null 2>&1 && die "public already has v$V"
# each release is one commit titled "Borgaralaun X.Y.Z"; anything after the last one was changed on public itself
LAST=$(git log -1 --format=%H --grep='^Borgaralaun [0-9]' public/main)
[ -n "$LAST" ] || die "no release commit found on public/main"
CHANGED=$(git diff --name-only "$LAST" public/main)
MISSING=""
[ -z "$CHANGED" ] || MISSING=$(git diff --name-only "$BRANCH" public/main -- $CHANGED)
[ -z "$MISSING" ] || die "public/main changed these since $(git log -1 --format='%s' "$LAST") and $BRANCH does not carry them:
$MISSING
Bring them into $BRANCH first (git checkout public/main -- <file>), commit, and run again."

# 5. the release commit and tag, local
C=$(git commit-tree "$BRANCH^{tree}" -p public/main -m "Borgaralaun $V")
T=$(printf 'object %s\ntype commit\ntag v%s\ntagger %s\n\nBorgaralaun %s\n' "$C" "$V" "$(git var GIT_COMMITTER_IDENT)" "$V" | git mktag)
git update-ref "refs/public-tags/v$V" "$T"
NOTES=$(mktemp)
awk -v v="## $V (" 'index($0, v) == 1 { on = 1; next } on && /^## / { exit } on' CHANGELOG.md > "$NOTES"
echo "release commit $C on public/main $(git rev-parse --short public/main), tag v$V ($T)"
echo "files changed against public/main: $(git diff --name-only public/main "$C" | wc -l | tr -d ' ')"
echo "release notes: $(wc -l < "$NOTES" | tr -d ' ') lines from CHANGELOG.md"

if [ "$PUSH" != "--push" ]; then
  echo "dry run: nothing pushed. To release: sh scripts/release.sh $V --push"
  exit 0
fi

# 6. push and release
git push public "$C:refs/heads/main" "refs/public-tags/v$V:refs/tags/v$V"
gh release create "v$V" --repo Josolon/iceland-ubi-simulation --verify-tag --title "Borgaralaun $V" --notes-file "$NOTES"
echo "released v$V. Vercel deploys public/main; check it with:"
echo "  gh api repos/Josolon/iceland-ubi-simulation/commits/$C/status --jq .state"
