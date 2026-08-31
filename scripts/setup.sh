#!/usr/bin/env bash
# Manual, one-time install step. The Omarchy plugin installer never runs
# plugin code, install hooks, or sudo -- so nothing about this script runs
# automatically when the plugin is added/enabled. Run it yourself once:
#   bash ~/.config/omarchy/plugins/io.github.gio1612.omarchy-adoption/scripts/setup.sh
set -euo pipefail

source_root=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
slug="omarchy-adoption-tracker"

for cmd in python3 systemctl install; do
  command -v "$cmd" >/dev/null 2>&1 || {
    echo "setup.sh: required command is missing: $cmd" >&2
    exit 1
  }
done

if ! groups "$USER" | grep -qw input; then
  echo "setup.sh: $USER is not in the 'input' group (needed to read /dev/input/event*)." >&2
  echo "Run:  sudo usermod -aG input $USER   then log out and back in, and re-run this script." >&2
  exit 1
fi

lib_dir="$HOME/.local/lib/$slug"
data_dir="$HOME/.local/share/$slug"
venv_dir="$data_dir/venv"
unit_dir="$HOME/.config/systemd/user"
unit_file="$unit_dir/$slug.service"

install -d -m 700 -- "$lib_dir" "$data_dir" "$unit_dir"

install -m 644 -- "$source_root"/backend/*.py "$lib_dir/"
chmod 755 -- "$lib_dir/daemon.py"

if [[ ! -x $venv_dir/bin/python ]]; then
  python3 -m venv "$venv_dir"
fi
"$venv_dir/bin/pip" install --upgrade pip >/dev/null
"$venv_dir/bin/pip" install -r "$source_root/backend/requirements.txt"

sed "s|ExecStart=.*|ExecStart=$venv_dir/bin/python $lib_dir/daemon.py|" \
  "$source_root/systemd/$slug.service" > "$unit_file"
chmod 644 -- "$unit_file"

systemctl --user daemon-reload
systemctl --user enable --now "$slug.service"

# The tracker never touches Hyprland keybinds: SUPER+K is detected straight
# from the raw keyboard stream (evdev), matching the allowlist parsed from
# `hyprctl binds`. A pre-evdev install may however have left a tracking block
# and wrapper behind -- remove them so SUPER+K returns to Omarchy's stock
# `omarchy-menu-keybindings` binding. If the block is absent this is a no-op.
bindings_file="$HOME/.config/hypr/bindings.lua"
if [[ -f $bindings_file ]] && grep -qF "BEGIN omarchy-adoption-tracker" "$bindings_file"; then
  sed -i '/-- BEGIN omarchy-adoption-tracker/,/-- END omarchy-adoption-tracker/d' "$bindings_file"
  echo "setup.sh: removed legacy SUPER+K tracking block from $bindings_file (stock binding restored)"
  command -v hyprctl >/dev/null 2>&1 && hyprctl reload >/dev/null 2>&1 || true
fi
rm -f -- "$lib_dir/cheatsheet-wrapper.sh" "$lib_dir/notify_cheatsheet.py"

if ! "$venv_dir/bin/python" "$lib_dir/daemon.py" --self-test; then
  echo "setup.sh: self-test reported problems (see above) -- the daemon may still work" >&2
fi

echo "Installed. Daemon: $slug.service (enabled at login)."
echo "Add the 'Adoption Tracker' bar widget from Omarchy's plugin/widget picker to see stats."
