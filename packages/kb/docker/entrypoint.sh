#!/bin/sh
set -e

PROFILE="${KB_PROFILE:?KB_PROFILE is required}"

exec 1c-cursor-kb-mcp --profile "$PROFILE" --transport http --port 8000
