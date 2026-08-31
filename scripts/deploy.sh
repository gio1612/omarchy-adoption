#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Deploy.sh -- push local dev-repo changes out to the running Omarchy setup.
#
# This project has THREE copies, so edits in the dev repo don't reach the
# running plugin on their own. This script makes the whole loop one command:
#
#   1. dev repo            /home/.../omarchy-adoption   (edit + test here)
#   2. plugin dir          ~/.config/omarchy/plugins/<id>
#                          (where the Omarchy shell loads the QML/widget from)
#   3. daemon runtime      ~/.local/lib/<slug>
#                          (the copy the systemd service actually runs)
#
# It syncs changed source files from the dev repo (this checkout) out to the
# plugin dir and the daemon runtime, then restarts the daemon service and
# reloads the shell so the running bar picks up the new widget code.
#
# Usage:
#   bash scripts/deploy.sh            # deploy + restart daemon + reload shell
#   bash scripts/deploy.sh --no-shell # deploy + restart daemon, skip shell reload
#   bash scripts/deploy.sh --dry-run  # show what would be copied, change nothing
#
# Requires the plugin to be installed at the standard Omarchy plugin path and
# the daemon to have been set up by scripts/setup.sh. Both are skipped (with
# a warning) if they're absent, so the script is safe to run from a fresh
# checkout before install.
# ---------------------------------------------------------------------------
set -euo pipefail

SOURCE_ROOT=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
ID=$(python3 -c "import json,sys; print(json.load(open('$SOURCE_ROOT/manifest.json'))['id'])" 2>/dev/null || echo "io.github.gio1612.omarchy-adoption")
SLUG="omarchy-adoption-tracker"

PLUGIN_DIR="${OMARCHY_PLUGIN_DIR:-$HOME/.config/omarchy/plugins/$ID}"
LIB_DIR="${OMARCHY_DAEMON_LIB_DIR:-$HOME/.local/lib/$SLUG}"

SHELL_RELOAD=true
DRY_RUN=false
for arg in "$@"; do
  case "$arg" in
    --no-shell) SHELL_RELOAD=false ;;
    --dry-run)  DRY_RUN=true ;;
    *) echo "deploy.sh: unknown argument: $arg" >&2; exit 1 ;;
  esac
done

PLUGIN_OK=false
LIB_OK=false

# --- Root QML/JS/manifest -> plugin dir -------------------------------------
if [[ -d "$PLUGIN_DIR" ]]; then
  PLUGIN_OK=true
  files=$(cd "$SOURCE_ROOT" && ls -1 *.qml *.js *.json 2>/dev/null || true)

  if $DRY_RUN; then
    echo "[dry-run] would copy root sources: ${files//$'\n'/ }"
  else
    while IFS= read -r f; do
      [[ -z "$f" ]] && continue
      install -m 644 -- "$SOURCE_ROOT/$f" "$PLUGIN_DIR/$f"
    done < <(cd "$SOURCE_ROOT" && printf '%s\n' *.qml *.js *.json)
    echo "deploy: synced root sources -> $PLUGIN_DIR"
  fi

  # backend/*.py -> plugin dir backend/
  if $DRY_RUN; then
    echo "[dry-run] would copy backend/*.py -> $PLUGIN_DIR/backend/"
  else
    install -d -m 700 -- "$PLUGIN_DIR/backend"
    for f in "$SOURCE_ROOT"/backend/*.py; do
      install -m 644 -- "$f" "$PLUGIN_DIR/backend/$(basename "$f")"
    done
    echo "deploy: synced backend -> $PLUGIN_DIR/backend/"
  fi
fi

# --- backend/*.py -> daemon runtime ------------------------------------------
if [[ -d "$LIB_DIR" ]]; then
  LIB_OK=true
  if $DRY_RUN; then
    echo "[dry-run] would copy backend/*.py -> $LIB_DIR"
  else
    for f in "$SOURCE_ROOT"/backend/*.py; do
      install -m 644 -- "$f" "$LIB_DIR/$(basename "$f")"
    done
    chmod 755 -- "$LIB_DIR/daemon.py" 2>/dev/null || true
    echo "deploy: synced backend -> $LIB_DIR (daemon runtime)"
  fi
fi

if $DRY_RUN; then
  echo "[dry-run] plugin dir : $PLUGIN_DIR"
  echo "[dry-run] daemon lib : $LIB_DIR"
  echo "[dry-run] source     : $SOURCE_ROOT"
fi

# --- restart the daemon service ----------------------------------------------
if ! $DRY_RUN; then
  if systemctl --user is-active --quiet "$SLUG.service" 2>/dev/null; then
    systemctl --user restart "$SLUG.service"
    echo "deploy: restarted $SLUG.service"
  else
    echo "deploy: $SLUG.service not running -- skipping restart (run scripts/setup.sh to install)"
  fi
fi

# --- reload the Omarchy shell so the bar picks up the new widget code --------
if $SHELL_RELOAD && ! $DRY_RUN; then
  if command -v omarchy-shell >/dev/null 2>&1; then
    omarchy-shell shell rescanPlugins || true
    echo "deploy: reloaded Omarchy shell (rescanPlugins)"
  else
    echo "deploy: omarchy-shell not found -- skipped shell reload"
  fi
fi

if $DRY_RUN; then
  echo "[dry-run] no changes were made."
fi

if ! $PLUGIN_OK || ! $LIB_OK; then
  echo "deploy: WARNING -- missing target(s), not fully deployed:" >&2
  ! $PLUGIN_OK && echo "  - plugin dir: $PLUGIN_DIR (run scripts/setup.sh or install the plugin first)" >&2
  ! $LIB_OK && echo "  - daemon lib: $LIB_DIR (run scripts/setup.sh to install)" >&2
fi
