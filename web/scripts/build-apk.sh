#!/usr/bin/env bash
# Build the ElderLeaf Android APK (debug-signed, installable by side-loading).
#
#   scripts/build-apk.sh https://<your-api>.modal.run     # API the app talks to by default
#
# The address can also be changed later inside the app (How it works → Server).
# Needs JDK 21 and the Android SDK (platform 36); on macOS: brew install openjdk@21 android-commandlinetools
set -euo pipefail
cd "$(dirname "$0")/.."

API_URL="${1:-${NEXT_PUBLIC_API_URL:-}}"
if [[ -z "$API_URL" ]]; then
  echo "warning: no API URL given; the app will ask for the server address on first start" >&2
fi

# Gradle needs JDK 17+ (21 recommended); an older JAVA_HOME (e.g. Java 8) is swapped for Homebrew's openjdk@21
java_major() { "$1/bin/java" -version 2>&1 | sed -nE 's/.*version "(1\.)?([0-9]+).*/\2/p' | head -1; }
if [[ -z "${JAVA_HOME:-}" || "$(java_major "$JAVA_HOME")" -lt 17 ]]; then
  if [[ -d /opt/homebrew/opt/openjdk@21 ]]; then
    export JAVA_HOME=/opt/homebrew/opt/openjdk@21/libexec/openjdk.jdk/Contents/Home
  else
    echo "error: JDK 17+ needed (brew install openjdk@21, or set JAVA_HOME)" >&2
    exit 1
  fi
fi
if [[ -z "${ANDROID_HOME:-}" && -d /opt/homebrew/share/android-commandlinetools ]]; then
  export ANDROID_HOME=/opt/homebrew/share/android-commandlinetools
fi
[[ -f android/local.properties ]] || echo "sdk.dir=${ANDROID_HOME:?set ANDROID_HOME to your Android SDK}" > android/local.properties

rm -rf out
# an explicit (even empty) value wins over .env.local, which points at a laptop-only address
NEXT_PUBLIC_API_URL="$API_URL" BUILD_TARGET=app npx next build
npx cap sync android
(cd android && ./gradlew --quiet assembleDebug)

mkdir -p dist
cp android/app/build/outputs/apk/debug/app-debug.apk dist/ElderLeaf.apk
echo "APK: $(pwd)/dist/ElderLeaf.apk (API: ${API_URL:-set in the app})"
