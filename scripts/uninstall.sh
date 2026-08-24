#!/usr/bin/env bash
# Reverses setup.sh. Pass --purge to also delete the local SQLite database
# (~/.local/share/omarchy-adoption-tracker/tracker.db) -- without it, your
# tracked history is kept in case you reinstall later.
set -euo pipefail

slug="omarchy-adoption-tracker"
purge=false
[[ ${1:-} == --purge ]] && purge=true

lib_dir="$HOME/.local/lib/$slug"
data_dir="$HOME/.local/share/$slug"
unit_file="$HOME/.config/systemd/user/$slug.service"
bindings_file="$HOME/.config/hypr/bindings.lua"

if systemctl --user is-active --quiet "$slug.service" 2>/dev/null; then
  systemctl --user stop "$slug.service"
fi
systemctl --user disable "$slug.service" >/dev/null 2>&1 || true
rm -f -- "$unit_file"
systemctl --user daemon-reload

if [[ -f $bindings_file ]] && grep -qF "BEGIN omarchy-adoption-tracker" "$bindings_file"; then
  sed -i '/-- BEGIN omarchy-adoption-tracker/,/-- END omarchy-adoption-tracker/d' "$bindings_file"
  echo "uninstall.sh: removed the SUPER+K tracking wrapper from $bindings_file"
  command -v hyprctl >/dev/null 2>&1 && hyprctl reload >/dev/null 2>&1 || true
fi

rm -rf -- "$lib_dir"

if $purge; then
  rm -rf -- "$data_dir"
  echo "uninstall.sh: removed all local data ($data_dir)"
else
  echo "uninstall.sh: kept local data at $data_dir (use --purge to remove it too)"
fi

echo "uninstall.sh: done."
