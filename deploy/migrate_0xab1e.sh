#!/usr/bin/env bash
# Seed the 0xab1e user from the repo-root JD/resume (the old single-user setup).
set -euo pipefail
cd ~/Aura

mkdir -p .aura/users/0xab1e
cp job_description.md .aura/users/0xab1e/jd.md
cp resume.md .aura/users/0xab1e/resume.md
cat > .aura/users/0xab1e/meta.json <<'EOF'
{
  "display_name": "0xab1e",
  "created": "2026-06-11T00:00:00+00:00"
}
EOF

ls -la .aura/users/0xab1e/
echo "--- login check ---"
curl -s -X POST https://aura.35.200.211.18.sslip.io/api/login \
     -H 'Content-Type: application/json' -d '{"name":"0xab1e"}'
echo
