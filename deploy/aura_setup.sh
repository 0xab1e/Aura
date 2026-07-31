#!/usr/bin/env bash
# One-shot server setup for Aura on shortsome-vm.
set -euo pipefail

DOMAIN="aura.35.200.211.18.sslip.io"
PORT=8765

sudo tee /etc/systemd/system/aura.service > /dev/null <<'EOF'
[Unit]
Description=Aura AI interview mentor (web UI)
After=network.target

[Service]
User=ablee
WorkingDirectory=/home/ablee/Aura
Environment=HOME=/home/ablee
ExecStart=/usr/bin/python3 /home/ablee/Aura/interview_agent.py --web --port 8765
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo tee /etc/nginx/sites-available/aura > /dev/null <<'EOF'
server {
    listen 80;
    listen [::]:80;
    server_name aura.35.200.211.18.sslip.io;

    # Audio is uploaded as base64 JSON; 15 MB of audio becomes ~20 MB on the wire.
    client_max_body_size 32m;

    # Model turns can take a while
    proxy_connect_timeout 300;
    proxy_send_timeout 300;
    proxy_read_timeout 300;
    send_timeout 300;

    location / {
        proxy_pass http://127.0.0.1:8765;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_buffering off;
    }

    access_log /var/log/nginx/aura_access.log;
    error_log /var/log/nginx/aura_error.log;
}
EOF

sudo ln -sf /etc/nginx/sites-available/aura /etc/nginx/sites-enabled/aura
sudo nginx -t
sudo systemctl reload nginx

sudo systemctl daemon-reload
sudo systemctl enable --now aura
sleep 3
sudo systemctl --no-pager -l status aura | head -12

echo "--- local HTTP check ---"
curl -s -o /dev/null -w "aura local: %{http_code}\n" "http://127.0.0.1:${PORT}/"

echo "--- requesting certificate ---"
sudo certbot --nginx -d "${DOMAIN}" --non-interactive --agree-tos --keep-until-expiring
sudo nginx -t
sudo systemctl reload nginx

echo "--- HTTPS check ---"
curl -s -o /dev/null -w "aura https: %{http_code}\n" "https://${DOMAIN}/"
echo "DONE: https://${DOMAIN}"
