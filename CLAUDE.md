# Aura Claude Project Guide

Read `AGENTS.md` first. It is the deployment and GCP source of truth for Aura.

Quick deploy memory:

```powershell
$gcloud = "C:\Users\ablee\AppData\Local\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd"
git -c safe.directory=C:/Work/Aura status --short
git -c safe.directory=C:/Work/Aura diff --stat
git -c safe.directory=C:/Work/Aura push origin <current-branch>
$remote = "cd /home/ablee/Aura && git pull --ff-only && sudo systemctl restart aura && sudo systemctl is-active aura && sudo journalctl -u aura -n 80 --no-pager"
& $gcloud compute ssh jbel-trim-web --zone=asia-south1-a --project=project-222c4aed-d452-434d-a84 --command=$remote
curl.exe -sI https://aura.34.93.196.79.sslip.io/
```

GCP: project `project-222c4aed-d452-434d-a84`, zone `asia-south1-a`, VM
`jbel-trim-web`, live path `/home/ablee/Aura`, service `aura`.
