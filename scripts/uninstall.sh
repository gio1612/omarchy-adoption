#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Reverses setup.sh.
#
#   --purge   also delete the local SQLite database
#             (~/.local/share/omarchy-adoption-tracker/) -- without it, your
#             tracked history is kept in case you reinstall later.
#
# Like setup.sh, this touches only the three paths this plugin owns. It does
# NOT edit ~/.config/hypr/ or any other configuration.
# ---------------------------------------------------------------------------
set -euo pipefail

slug="omarchy-adoption-tracker"
purge=false
for arg in "$@"; do
  case "$arg" in
    --purge) purge=true ;;
    -h|--help) sed -n '2,11p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "uninstall.sh: unknown argument: $arg" >&2; exit 2 ;;
  esac
done

lib_dir="$HOME/.local/lib/$slug"
data_dir="$HOME/.local/share/$slug"
unit_file="$HOME/.config/systemd/user/$slug.service"

if systemctl --user is-active --quiet "$slug.service" 2>/dev/null; then
  systemctl --user stop "$slug.service"
fi
systemctl --user disable "$slug.service" >/dev/null 2>&1 || true
rm -f -- "$unit_file"
systemctl --user daemon-reload >/dev/null 2>&1 || true

rm -rf -- "$lib_dir"

if $purge; then
  rm -rf -- "$data_dir"
  echo "uninstall.sh: removed all local data ($data_dir)"
else
  echo "uninstall.sh: kept local data at $data_dir (use --purge to remove it too)"
fi

echo "uninstall.sh: done. Remove the plugin itself with:"
echo "  omarchy plugin remove io.github.gio1612.omarchy-adoption"
