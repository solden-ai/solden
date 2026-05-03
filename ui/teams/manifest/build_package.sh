#!/usr/bin/env bash
# Build the Teams app package (manifest + icons -> app.zip).
#
# Microsoft Teams admins (and the AppSource submission flow) require
# a single .zip file containing manifest.json + the two icon PNGs.
# This script substitutes the bot's Microsoft App ID into the
# manifest template, validates the JSON, and zips the bundle.
#
# Usage
#   MICROSOFT_APP_ID=<bot-uuid> ./build_package.sh
#   MICROSOFT_APP_ID=<bot-uuid> APP_VERSION=1.2.0 ./build_package.sh
#
# Output
#   dist/solden-teams-<version>.zip
#
# Prerequisites
#   * MICROSOFT_APP_ID env var set (Bot Framework registration ID).
#   * jq (for JSON validation) — `brew install jq` on macOS.
#   * zip (standard on macOS / Linux).

set -euo pipefail

# Resolve script directory + repo paths.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DIST_DIR="${SCRIPT_DIR}/dist"
APP_ID="${MICROSOFT_APP_ID:-}"
APP_VERSION="${APP_VERSION:-1.0.0}"

if [[ -z "${APP_ID}" ]]; then
  echo "ERROR: MICROSOFT_APP_ID env var is required." >&2
  echo "       Get this from Bot Framework registration in Azure." >&2
  exit 2
fi

# Validate the bot ID looks like a UUID. Microsoft accepts only the
# 36-char hyphenated UUID form here.
if ! echo "${APP_ID}" | grep -Eq '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'; then
  echo "ERROR: MICROSOFT_APP_ID '${APP_ID}' is not a valid UUID." >&2
  exit 2
fi

# Required source files. Fail fast if any are missing rather than
# building a half-broken package.
for f in manifest.json color.png outline.png; do
  if [[ ! -f "${SCRIPT_DIR}/${f}" ]]; then
    echo "ERROR: missing source file ${SCRIPT_DIR}/${f}" >&2
    exit 1
  fi
done

mkdir -p "${DIST_DIR}"
WORK_DIR="$(mktemp -d -t solden-teams-build-XXXXXX)"
trap 'rm -rf "${WORK_DIR}"' EXIT

# Substitute the bot ID + version into the manifest template.
# The template keeps the literal placeholders so it's safe to commit
# without baking secrets in.
sed \
  -e "s|\${MICROSOFT_APP_ID}|${APP_ID}|g" \
  -e "s|\"version\": \"1.0.0\"|\"version\": \"${APP_VERSION}\"|" \
  "${SCRIPT_DIR}/manifest.json" > "${WORK_DIR}/manifest.json"

# Validate the resulting JSON. jq -e exits non-zero on invalid JSON.
if command -v jq >/dev/null 2>&1; then
  if ! jq -e . "${WORK_DIR}/manifest.json" >/dev/null; then
    echo "ERROR: built manifest.json is not valid JSON." >&2
    exit 1
  fi
else
  echo "WARNING: jq not installed, skipping JSON validation." >&2
fi

# Copy icons alongside the substituted manifest.
cp "${SCRIPT_DIR}/color.png" "${WORK_DIR}/color.png"
cp "${SCRIPT_DIR}/outline.png" "${WORK_DIR}/outline.png"

# Zip from inside the work dir so paths are flat (Teams rejects
# packages with nested directories).
OUTPUT_ZIP="${DIST_DIR}/solden-teams-${APP_VERSION}.zip"
rm -f "${OUTPUT_ZIP}"
( cd "${WORK_DIR}" && zip -q "${OUTPUT_ZIP}" manifest.json color.png outline.png )

echo "Built ${OUTPUT_ZIP}"
echo "  manifest.json (botId=${APP_ID}, version=${APP_VERSION})"
echo "  color.png + outline.png"
echo
echo "Next steps:"
echo "  Sideload (test):  Teams Admin Center > Manage apps > Upload"
echo "  Distribute:       Teams Admin Center > Permission policies, or"
echo "                    submit to AppSource via Partner Center."
