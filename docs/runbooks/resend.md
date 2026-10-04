# Runbook · Resend (e-mail)

Customer notifications by e-mail, **only to an address the demo user types and confirms** — never to dataset addresses
(spec 13, [ADR 0013](../adr/0013-customer-receives-proof-receipt-case-page-notifications.md)). Facts verified against
Resend's [domains](https://resend.com/docs/dashboard/domains/introduction),
[regions](https://resend.com/docs/dashboard/domains/regions) and [pricing](https://resend.com/pricing) pages on 2026-10-04.

## 1. Account (owner: lead)
Free plan: 3,000 e-mails/month, 100/day, 3 domains, 30-day log retention. Use the team e-mail as the account owner.

## 2. Sending domain
- Domain: **`notify.nickoftime.salazarvalverdeai.com`** (Resend recommends a subdomain to isolate reputation).
- Sender: `avisos@notify.nickoftime.salazarvalverdeai.com`.
- Region: **North Virginia (`us-east-1`)**; alternatives: Ireland, São Paulo, Tokyo.
- Resend → Domains → Add Domain → copy the **Records** tab exactly. The lead's agent creates them in Hostinger (dry
  run, backup, apply, verify on public DNS). Verification usually takes ~15 minutes; up to 72 h. DMARC is optional.

**Done on 2026-10-04** (domain id `36f8ca8a-60d7-4864-b7f0-a8cfe12ab24c`). Resend returned four records, all created in
the `salazarvalverdeai.com` zone:

| Type | Name | Value | Resend group |
|---|---|---|---|
| TXT | `resend._domainkey.notify.nickoftime` | `p=MIGf…` (public DKIM key; copy it from Resend) | DKIM |
| MX | `send.notify.nickoftime` | `10 feedback-smtp.us-east-1.amazonses.com` | SPF |
| TXT | `send.notify.nickoftime` | `v=spf1 include:amazonses.com ~all` | SPF |
| CNAME | `rsend.notify.nickoftime` | `send.forge.rmta.net` | SPF |

MX, SPF and the CNAME verified within minutes; DKIM took about 2 hours although the published value already matched on
every public resolver. If DKIM stays `pending`, wait (Resend allows up to 72 h) instead of re-creating the record. The
domain was verified the same day and `make check-resend` passed from `avisos@notify.nickoftime.salazarvalverdeai.com`.

## 3. API key and values
Resend → API Keys → Create: **Sending access**, restricted to the domain above.

Production (SSM):
```bash
aws ssm put-parameter --profile nickoftime --region us-east-2 --type SecureString \
  --name /nickoftime/prod/RESEND_API_KEY --value '<key>' --tags Key=Project,Value=nickoftime
```
Local `.env`:
```
RESEND_API_KEY=<key>
RESEND_FROM=Nick of Time <avisos@notify.nickoftime.salazarvalverdeai.com>
```

## 4. Access check
```bash
make check-resend ARGS="--to you@example.com"     # an address you own
# OK    accepted by Resend (email id …) from Nick of Time <avisos@notify…> — check the inbox
```
`HTTP 403` with a domain error → the domain is not verified yet; `HTTP 401` → wrong key.

## How the product uses it (spec 13)
The user enters an address on `/case/{id}` → one-time confirmation link → only then notifications are sent
(`email_confirmed`). Each send is a `notification_sent` event; if Resend fails, the notification remains in "My
notifications". Templates are ES/PT and never include the score, policy ids or the transcript.

## If the key leaks
Delete it in Resend → create a new sending-only key → update SSM and `.env` → rerun the check.
