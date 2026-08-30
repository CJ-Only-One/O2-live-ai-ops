#!/bin/sh
set -eu

source_repo=$(git rev-parse --show-toplevel)
workspace=$(dirname "$source_repo")
deploy_repo="$workspace/O2-live-deploy"
org_repo="${O2_ORG_PROFILE_REPO:-$workspace/.github}"

for repo in "$deploy_repo" "$org_repo"; do
  git -C "$repo" rev-parse --is-inside-work-tree >/dev/null
done

if [ -n "$(git -C "$deploy_repo" status --porcelain -- README.md docs/images/architecture)" ]; then
  echo "O2-live-deploy README assets have uncommitted changes." >&2
  exit 1
fi

if [ -n "$(git -C "$org_repo" status --porcelain -- profile/README.md profile/docs/images/architecture)" ]; then
  echo "Organization README assets have uncommitted changes." >&2
  exit 1
fi

mkdir -p "$deploy_repo/docs/images/architecture"
mkdir -p "$org_repo/profile/docs/images/architecture"

cp "$source_repo/README.md" "$workspace/README.md"
cp "$source_repo/README.md" "$deploy_repo/README.md"
cp "$source_repo"/docs/images/architecture/*.png "$deploy_repo/docs/images/architecture/"
cp "$source_repo/README.md" "$org_repo/profile/README.md"
cp "$source_repo"/docs/images/architecture/*.png "$org_repo/profile/docs/images/architecture/"

echo "Synced README to the workspace, O2-live-deploy, and CJ-Only-One/.github."
