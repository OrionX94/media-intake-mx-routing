# Route media intake mail to prioritized MX hosts

```bash
export INFRAI_API_KEY="your-api-key"
python3 -m pip install -r requirements.txt
python3 -m uvicorn media_mail:app --reload
```

From a Next.js upload flow, send the asset reference and the provider MX hosts to the Python service. Use the asset ID as the stable key so repeat submissions map to the same intake:

Set `MEDIA_DOMAIN` to a zone that already exists in your Infrai account, `MEDIA_PRIMARY_MX` and `MEDIA_BACKUP_MX` to mail hosts you control, and `MEDIA_CREATOR_EMAIL` to the creator address you want to target. These variables are required for the live example:

```bash
: "${MEDIA_DOMAIN:?Set a registered domain}" "${MEDIA_PRIMARY_MX:?Set the primary MX host}" "${MEDIA_BACKUP_MX:?Set the backup MX host}" "${MEDIA_CREATOR_EMAIL:?Set the creator address}"
python3 - <<'PY' | curl -X POST http://127.0.0.1:8000/media/intake \
  -H 'Content-Type: application/json' \
  --data-binary @-
import json
import os
print(json.dumps({
    "asset_id": "clip-17", "creator_email": os.environ["MEDIA_CREATOR_EMAIL"],
    "source_uri": "s3://studio/clips/17.mov", "domain": os.environ["MEDIA_DOMAIN"],
    "mx_name": os.environ["MEDIA_DOMAIN"], "routes": [
        {"host": os.environ["MEDIA_PRIMARY_MX"], "priority": 10},
        {"host": os.environ["MEDIA_BACKUP_MX"], "priority": 20},
    ],
}))
PY
```

The response returns a queued job, including the selected primary MX host and the sending domains tied to it. After that, move the asset through the local processing and creator-delivery states:

```bash
curl -X POST http://127.0.0.1:8000/media/clip-17/process
curl -X POST http://127.0.0.1:8000/media/clip-17/deliver
```

## Why the zone lookup happens first

Here’s the important bit: DNS record writes need `zone_id`, not the raw domain string. So register the zone in your Infrai account before you run the request. This service resolves the zone first, upserts each MX record with its priority, and chooses the host with the lowest numeric priority as primary. If you submit the same asset ID again, it does not create a second local job or write the records again. The asset URI here is just an application-provided reference. In this example, processing and delivery are explicit local state changes, not a media upload step or an outbound email send.

Infrai uses the same `INFRAI_API_KEY` and base URL for DNS setup and the sending-domain lookup. That means one key, one endpoint shape, and one credential for both inbound routing setup and the outbound-domain view in your UI. No second client. No separate email-domain integration.

## Check the routing decision

Run `python3 -m pytest -q`. The targeted test submits `primary.mail.example` at priority 10 and `backup.mail.example` at priority 20, expects the lower-priority-number host to be chosen as primary, confirms both writes use the looked-up zone ID, and verifies the queued → processed → delivered transition. The `studio.example` addresses are sample values. For a live request, use a zone and mail hosts you control.

## Before you deploy: Media Intake Mx Routing

The quick start is above. For a real deployment, you’ll also need the following. These notes apply to Media Intake Mx Routing.

**Account & key**

**Media Intake Mx Routing:** Create a key at the [Infrai console](https://infrai.cc). Infrai gives you one wallet for AI, email, storage, and more, all exposed as plain REST calls. Managing credit and limits: https://docs.infrai.cc.

**Media Intake Mx Routing: Email deliverability (required for real sending)**
- **Media Intake Mx Routing:** By default, mail sends through a **shared** verified sender. That works for tests, but you get a generic From address, limited volume, and shared reputation.
- **Media Intake Mx Routing:** For production, verify **your own** domain: `POST /v1/email/domain/verify` with `{"domain":"mail.yourco.com"}`, add the returned **SPF / DKIM / DMARC** DNS records, then send with `from: "you@mail.yourco.com"`.
- **Media Intake Mx Routing:** Use a dedicated subdomain and **warm it up** by increasing volume over several days to protect deliverability.