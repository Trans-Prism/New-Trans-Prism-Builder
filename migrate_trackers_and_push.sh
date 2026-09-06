#!/bin/bash
set -e

BUILDER_ROOT="/Users/wenle/Developer/workspace/Trans_Prism/builder"
OLD_REPO="$BUILDER_ROOT/Trans-Prism-Builder"
NEW_REPO="$BUILDER_ROOT/New-Trans-Prism-Builder"

echo "=== 1. Copy Tracker Workflows ==="
cp "$OLD_REPO/.github/workflows/build_tracker.yml" "$NEW_REPO/.github/workflows/build_tracker.yml"
cp "$OLD_REPO/.github/workflows/build_transmtf_tracker.yml" "$NEW_REPO/.github/workflows/build_transmtf_tracker.yml"

echo "=== 2. Check Workflows in New Repo ==="
ls -la "$NEW_REPO/.github/workflows"

cd "$NEW_REPO"

echo "=== 3. Git Add & Commit Local Changes ==="
git add -A
git commit -m "feat: migrate HRT trackers (Oyama + TransMTF) and fix mtf ci" || echo "Nothing new to commit"

echo "=== 4. Git Pull Rebase & Push ==="
git pull --rebase origin main
git push origin main

echo "=== 6. Trigger MtF Workflow ==="
gh workflow run "OTA Builder VP - MtF" --repo daanser/New-Trans-Prism-Builder

echo ""
echo "=== 7. Recent Workflow Runs ==="
sleep 3
gh run list --repo daanser/New-Trans-Prism-Builder --limit 5
