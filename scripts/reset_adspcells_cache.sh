#!/usr/bin/env bash

# Preserve and reset the .adsPcells cache in one ADS workspace.
# ADS must be completely closed before this script is run.

set -eu

if [ "$#" -ne 1 ]; then
    printf 'Usage: %s /absolute/path/to/workspace_wrk\n' "$0" >&2
    exit 2
fi

workspace_path=$1

if [ ! -d "$workspace_path" ]; then
    printf 'Workspace directory does not exist: %s\n' "$workspace_path" >&2
    exit 2
fi

if [ ! -f "$workspace_path/de_sim.cfg" ]; then
    printf 'Refusing to continue: de_sim.cfg was not found in %s\n' "$workspace_path" >&2
    exit 2
fi

cache_path="$workspace_path/.adsPcells"
if [ ! -d "$cache_path" ]; then
    printf 'No .adsPcells directory exists in %s. Nothing changed.\n' "$workspace_path"
    exit 0
fi

printf 'ADS must be completely closed for workspace:\n  %s\n' "$workspace_path"
printf 'Type CLOSED to confirm that ADS is not running: '
IFS= read -r confirmation

if [ "$confirmation" != 'CLOSED' ]; then
    printf 'Cancelled. Nothing changed.\n'
    exit 1
fi

timestamp=$(date '+%Y%m%d-%H%M%S')
backup_path="$cache_path.stale-$timestamp"
counter=1
while [ -e "$backup_path" ]; do
    backup_path="$cache_path.stale-$timestamp-$counter"
    counter=$((counter + 1))
done

mv "$cache_path" "$backup_path"
printf 'Cache preserved as:\n  %s\n' "$backup_path"
printf 'Restart ADS, keep RFPro closed, and run refresh_rfpro_view.py.\n'
