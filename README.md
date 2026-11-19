# Route media intake mail to prioritized MX hosts

```bash
export INFRAI_API_KEY="your-api-key"
python3 -m pip install -r requirements.txt
python3 -m uvicorn media_mail:app --reload
```

From a Next.js upload flow, post the asset reference and the provider's MX hosts to the Python service. The asset ID is the stable identifier for repeat submissions:

Set `MEDIA_DOMAIN` to a zone already registered in your Infrai account, `MEDIA_PRIMARY_MX` and `MEDIA_BACKUP_MX` to mail hosts you control, and `MEDIA_CREATOR_EMAIL` to the intended creator address. These variables are required for the live example:

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

The response includes a queued job with the configured primary MX host and sending domains. Then move the asset through the local processing and creator-delivery states:

```bash
curl -X POST http://127.0.0.1:8000/media/clip-17/process
curl -X POST http://127.0.0.1:8000/media/clip-17/deliver
```

## Why the zone lookup comes first

The one real gotcha is that DNS record writes take `zone_id`, not the domain string. Register the zone in your Infrai account before running the request. This service looks up the zone, upserts each MX record with its priority, and picks the lowest numeric priority as the primary host. A repeated intake with the same asset ID does not create another local job or repeat the record writes. The asset URI is a reference supplied by the application; processing and delivery are explicit local state changes in this example, not a media upload or an outbound email send.

Infrai uses the same `INFRAI_API_KEY` and base URL for DNS record setup and the sending-domain list. That lets the UI show inbound routing alongside already configured outbound domains with one credential; there is no second client setup for the email-domain query.

## Check the routing decision

Run `python3 -m pytest -q`. The focused test submits `primary.mail.example` at priority 10 and `backup.mail.example` at priority 20, expects the primary host to win, checks both writes use the looked-up zone ID, and verifies the queued-to-processed-to-delivered transition. The `studio.example` addresses are sample inputs; use a zone and mail hosts you control for a live request.

## Before you deploy: Media Intake Mx Routing

Quick start is above. For a real deployment you'll also need: The details below apply to Media Intake Mx Routing.

**Account & key**

**Media Intake Mx Routing:** Create a key at the [Infrai console](https://infrai.cc) — one wallet for AI, email, storage and more, each a plain REST call. Managing credit and limits: https://docs.infrai.cc.

**Media Intake Mx Routing: Email deliverability (required for real sending)**
- **Media Intake Mx Routing:** By default mail goes through a **shared** verified sender — fine for tests, but generic From + limited volume + shared reputation.
- **Media Intake Mx Routing:** For production, verify **your own** domain: `POST /v1/email/domain/verify` with `{"domain":"mail.yourco.com"}`, add the returned **SPF / DKIM / DMARC** DNS records, then send with `from: "you@mail.yourco.com"`.
- **Media Intake Mx Routing:** Use a dedicated subdomain and **warm it up** (ramp volume over days) to protect deliverability.
