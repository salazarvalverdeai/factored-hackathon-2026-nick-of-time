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
- Resend → Domains → Add Domain → copy the **Records** tab (DKIM TXT, SPF TXT, MX) exactly. The lead's agent creates
  them in Hostinger (dry run, backup, apply, verify on public DNS). Verification usually takes ~15 minutes; up to 72 h.
  DMARC is optional.

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
