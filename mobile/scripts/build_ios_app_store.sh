#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

build_number="${BUILD_NUMBER:-$(date +%Y%m%d%H)}"
api_base_url="${DALIJOB_API_BASE_URL:-https://jobmatch.dalifin.com/api/v1/}"

flutter build ipa \
  --release \
  --export-method app-store \
  --build-number "$build_number" \
  --dart-define=DALIJOB_ENV="${DALIJOB_ENV:-production}" \
  --dart-define=DALIJOB_API_BASE_URL="$api_base_url"

echo "Built App Store IPA with build number: $build_number"
echo "IPA: $(pwd)/build/ios/ipa/dalijob_mobile.ipa"
