#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# The version lives in two places that must not drift:
#
#   manifest.json          "version"        -- what Omarchy's plugin registry
#                                              and `omarchy plugin list` show
#   backend/daemon.py      DAEMON_VERSION   -- what the socket `hello` command
#                                              reports to the widget
#
# Release builds add a third: the git tag. Pass it to check all three.
#
#   ./tools/check-version.sh          # manifest == daemon
#   ./tools/check-version.sh v1.0.0   # manifest == daemon == tag (minus 'v')
# ---------------------------------------------------------------------------
set -euo pipefail

REPO_ROOT=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)

manifest_version=$(python3 -c \
  "import json;print(json.load(open('$REPO_ROOT/manifest.json'))['version'])")

daemon_version=$(python3 - "$REPO_ROOT/backend/daemon.py" <<'PY'
import re, sys
src = open(sys.argv[1]).read()
match = re.search(r'^DAEMON_VERSION\s*=\s*"([^"]+)"', src, re.M)
print(match.group(1) if match else "")
PY
)

status=0

if [[ -z $daemon_version ]]; then
  echo "check-version: could not read DAEMON_VERSION from backend/daemon.py" >&2
  exit 1
fi

if [[ $manifest_version != "$daemon_version" ]]; then
  echo "check-version: manifest.json version ($manifest_version) != DAEMON_VERSION ($daemon_version)" >&2
  status=1
fi

if [[ -n ${1:-} ]]; then
  tag_version=${1#v}
  if [[ $manifest_version != "$tag_version" ]]; then
    echo "check-version: git tag ($1 -> $tag_version) != manifest.json version ($manifest_version)" >&2
    status=1
  fi
fi

if (( status == 0 )); then
  echo "check-version: $manifest_version${1:+ (tag $1)}"
fi
exit $status
