#!/usr/bin/env bash
# Idempotent injector for the SUPER+K tracking wrapper into the user's own
# ~/.config/hypr/bindings.lua override file. Never invoked automatically by
# the Omarchy plugin installer -- run manually, once, by setup.sh.
set -euo pipefail

bindings_file="$HOME/.config/hypr/bindings.lua"
marker_begin="-- BEGIN omarchy-adoption-tracker (do not edit this block by hand; managed by setup.sh)"
marker_end="-- END omarchy-adoption-tracker"
wrapper="$HOME/.local/lib/omarchy-adoption-tracker/cheatsheet-wrapper.sh"

if [[ ! -f $bindings_file ]]; then
  echo "install-keybind.sh: $bindings_file not found -- is this an Omarchy/Hyprland install?" >&2
  exit 1
fi

if grep -qF -- "$marker_begin" "$bindings_file"; then
  echo "install-keybind.sh: already installed in $bindings_file, nothing to do"
  exit 0
fi

if grep -Eqi 'SUPER[[:space:]]*\+[[:space:]]*K"' "$bindings_file"; then
  echo "install-keybind.sh: $bindings_file already has a custom SUPER+K binding." >&2
  echo "Remove or rename it, then re-run this script -- we won't overwrite your own bindings." >&2
  exit 1
fi

{
  echo ""
  echo "$marker_begin"
  echo 'hl.unbind("SUPER + K")'
  echo "o.bind(\"SUPER + K\", \"Keybindings\", \"$wrapper\")"
  echo "$marker_end"
} >> "$bindings_file"

echo "install-keybind.sh: added SUPER+K tracking wrapper to $bindings_file"

if command -v hyprctl >/dev/null 2>&1; then
  hyprctl reload >/dev/null 2>&1 || true
fi
