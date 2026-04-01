#!/bin/zsh

set -euo pipefail

API_URL="http://127.0.0.1:9090/invocation"
OUTPUT_FILE="alice_output.txt"
USER_ID="alice"
RUN_ID="alice-session-2"

append_turn() {
  local query="$1"
  local response

  response=$(curl -s -X POST "$API_URL" \
    -H "Content-Type: application/json" \
    -d "{\"user_id\":\"$USER_ID\",\"run_id\":\"$RUN_ID\",\"query\":\"$query\"}" | jq -r '.response')

  printf 'User: %s\n' "$query" >> "$OUTPUT_FILE"
  printf 'Agent: %s\n\n' "$response" >> "$OUTPUT_FILE"
}

printf '\n=== Alice Session 2 (New Session) ===\n\n' >> "$OUTPUT_FILE"

append_turn "What do you remember about me?"
append_turn "What project am I working on?"
