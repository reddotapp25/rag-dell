#!/usr/bin/env bash
# Push this project to a Hugging Face Space.
#
# Prereqs (one-time):
#   1. Create a free account: https://huggingface.co/join
#   2. Create a User Access Token with "write" scope:
#        https://huggingface.co/settings/tokens
#   3. Create an empty Space:
#        https://huggingface.co/new-space
#        - Owner:  your HF username
#        - Name:   ma-rag  (or anything you like)
#        - SDK:    Docker
#        - Hardware: CPU basic (free)
#        - Visibility: Public (or Private if you prefer)
#   4. In that Space's "Settings -> Variables and secrets" add:
#        Secret:  GROQ_API_KEY = gsk_...
#
# Then run:
#   HF_USER=your_hf_username HF_SPACE=ma-rag HF_TOKEN=hf_xxx ./scripts/push-to-hf.sh
set -euo pipefail

cd "$(dirname "$0")/.."

: "${HF_USER:?HF_USER is required (your Hugging Face username)}"
: "${HF_SPACE:?HF_SPACE is required (the Space name you created)}"
: "${HF_TOKEN:?HF_TOKEN is required (create one at https://huggingface.co/settings/tokens)}"

REMOTE_URL="https://${HF_USER}:${HF_TOKEN}@huggingface.co/spaces/${HF_USER}/${HF_SPACE}"
PUBLIC_URL="https://huggingface.co/spaces/${HF_USER}/${HF_SPACE}"

step() { printf "\n\033[1;34m==> %s\033[0m\n" "$*"; }

step "Initialising git repo (if needed)"
if [ ! -d .git ]; then
  git init -b main
fi

step "Configuring Hugging Face remote"
git remote remove hf 2>/dev/null || true
git remote add hf "$REMOTE_URL"

# HF Spaces require the README (with YAML frontmatter) at repo root.
step "Staging project files"
git add -A
if git diff --cached --quiet; then
  echo "No changes to commit."
else
  git commit -m "Deploy: multi-agent RAG chat to Hugging Face Spaces"
fi

step "Pushing to Hugging Face Space (this also triggers the Docker build)"
# First push may need --force if the Space was created with an initial README
# you want to overwrite.
git push hf HEAD:main --force

cat <<EOF

===============================================================================
Pushed successfully.

Build logs:  ${PUBLIC_URL} (click "Logs" tab)
Live app:    https://${HF_USER}-${HF_SPACE}.hf.space

The first build takes ~5-8 minutes (it pre-downloads the embedding model into
the image). After it's "Running", the first request triggers auto-ingest of
the Dell docs (~30 seconds) before answering.

Make sure you added the GROQ_API_KEY secret in:
   ${PUBLIC_URL}/settings

If the app logs say 'GROQ_API_KEY is not configured', add/fix the secret and
then click "Restart this Space" on the Settings page.
===============================================================================
EOF
