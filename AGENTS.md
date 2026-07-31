# Aura Agent Guide

Fresh assistant sessions must read this file before deploying Aura.

## Live Topology

- GCP account: `ableudemy@gmail.com`
- GCP project: `project-3b739ef9-9c65-426d-905`
- Zone: `asia-south1-a`
- VM: `shortsome-vm`
- Static/public IP: `35.200.211.18`
- Live URL: `https://aura.35.200.211.18.sslip.io`
- Code on VM: `/home/ablee/Aura`
- Linux user: `ablee`
- systemd unit: `aura.service`
- App port: `127.0.0.1:8765`
- nginx site: `/etc/nginx/sites-available/aura`

## GCP Access

Use the same explicit GCP access style as the Amban/Shortsome project.

```powershell
$gcloud = "C:\Users\ablee\AppData\Local\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd"
& $gcloud compute ssh shortsome-vm --zone=asia-south1-a --project=project-3b739ef9-9c65-426d-905
```

## Deploy Procedure

Always inspect scope first:

```powershell
git -c safe.directory=C:/Work/Aura status --short
git -c safe.directory=C:/Work/Aura diff --stat
```

Commit and push relevant files only. Do not assume local changes are live.

```powershell
git -c safe.directory=C:/Work/Aura push origin <current-branch>
```

Then pull and restart on the GCP VM:

```powershell
$gcloud = "C:\Users\ablee\AppData\Local\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd"
$remote = "cd /home/ablee/Aura && git pull --ff-only && sudo systemctl restart aura && sudo systemctl is-active aura && sudo journalctl -u aura -n 80 --no-pager"
& $gcloud compute ssh shortsome-vm --zone=asia-south1-a --project=project-3b739ef9-9c65-426d-905 --command=$remote
```

Verify:

```powershell
curl.exe -sI https://aura.35.200.211.18.sslip.io/
```

## Voice Recording Path

The web UI must not use phone/browser speech recognition. The phone records with
`MediaRecorder`, uploads the audio to `/api/audio/message`, the server writes the
file under `.aura/users/<user>/audio/`, and server-side Codex CLI receives the
server audio file path for transcription. Aura replies remain text-only.
