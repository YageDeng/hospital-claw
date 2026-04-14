#!/usr/bin/env bash
# gemma_probe_driver.sh — Agent probe driver that delegates to Ollama Gemma.
#
# Usage: gemma_probe_driver.sh <payload.json>
#
# The payload JSON contains:
#   probe_name, prompt, payload, workspace_root
#
# Exit 0 = PASS, non-zero = FAIL. Stdout is used as the summary line.

set -euo pipefail

if [[ $# -lt 1 ]]; then
    echo "Usage: $0 <payload.json>" >&2
    exit 1
fi

PAYLOAD_FILE="$1"
MODEL="${SKILL_E2E_GEMMA_MODEL:-gemma4:e4b}"
OLLAMA_URL="${SKILL_E2E_OLLAMA_URL:-http://127.0.0.1:11434}"
TIMEOUT="${SKILL_E2E_PROBE_TIMEOUT:-120}"

# Extract the prompt from payload
PROMPT=$(python3 -c "
import json, sys
with open(sys.argv[1], encoding='utf-8') as f:
    data = json.load(f)
print(data.get('prompt', ''))
" "$PAYLOAD_FILE" 2>/dev/null)

if [[ -z "$PROMPT" ]]; then
    echo "FAIL: could not extract prompt from payload"
    exit 1
fi

# Call Ollama chat API
RESPONSE=$(curl -s --max-time "$TIMEOUT" "$OLLAMA_URL/api/chat" \
    -d "$(python3 -c "
import json, sys
with open(sys.argv[1], encoding='utf-8') as f:
    data = json.load(f)
print(json.dumps({
    'model': '$MODEL',
    'messages': [{'role': 'user', 'content': data.get('prompt', '')}],
    'stream': False
}))
" "$PAYLOAD_FILE")" 2>/dev/null)

if [[ -z "$RESPONSE" ]]; then
    echo "FAIL: empty response from Ollama"
    exit 1
fi

# Extract the assistant message content
CONTENT=$(echo "$RESPONSE" | python3 -c "
import json, sys
try:
    data = json.load(sys.stdin)
    msg = data.get('message', {}).get('content', '')
    print(msg[:500])
except Exception:
    print('')
" 2>/dev/null)

if [[ -z "$CONTENT" ]]; then
    echo "FAIL: could not parse Ollama response"
    exit 1
fi

# Check if the response contains a clear failure indicator
LOWER_CONTENT=$(echo "$CONTENT" | tr '[:upper:]' '[:lower:]')
if echo "$LOWER_CONTENT" | grep -qi "i cannot\|i can't\|unable to\|not possible\|error:\|failed"; then
    echo "FAIL: model refused or errored: ${CONTENT:0:200}"
    exit 1
fi

echo "PASS: ${CONTENT:0:200}"
exit 0
