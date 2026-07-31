# Aura Claude Project Guide

Read `AGENTS.md` first. It is the deployment and GCP source of truth for Aura.

Quick deploy memory:

```powershell
$gcloud = "C:\Users\ablee\AppData\Local\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd"
git -c safe.directory=C:/Work/Aura status --short
git -c safe.directory=C:/Work/Aura diff --stat
git -c safe.directory=C:/Work/Aura push origin <current-branch>
$remote = "cd /home/ablee/Aura && git pull --ff-only && sudo systemctl restart aura && sudo systemctl is-active aura && sudo journalctl -u aura -n 80 --no-pager"
& $gcloud compute ssh shortsome-vm --zone=asia-south1-a --project=project-3b739ef9-9c65-426d-905 --command=$remote
curl.exe -sI https://aura.35.200.211.18.sslip.io/
```

GCP: project `project-3b739ef9-9c65-426d-905`, zone `asia-south1-a`, VM
`shortsome-vm`, live path `/home/ablee/Aura`, service `aura`.
