# 0011. One EC2 with Docker Compose, two subdomains, deploy through OIDC and SSM

- **Status:** Accepted
- **Date:** 2026-09-29 (deploy path updated 2026-10-03)
- **Deciders:** Freddy, GianMarco · **Owner:** @gianzk
- **Related:** spec 06, [`docs/infrastructure.md`](../infrastructure.md)

## Context
Judges must open a working HTTPS URL after the deadline. The stack is a web app, an API, an MCP server and Postgres.
The instance has no SSH (access through SSM) and AWS keys must not live in GitHub.

## Decision
One EC2 (`t3.medium`, Ubuntu 24.04, Elastic IP) runs Docker Compose with **Caddy** (automatic TLS), **web**, **api**,
**mcp** and **postgres**. Two subdomains: `nickoftime.salazarvalverdeai.com` serves the web app and `/api` (same origin,
no CORS) and `mcp.nickoftime.salazarvalverdeai.com` serves the MCP server. GitHub Actions builds images to GHCR,
assumes an AWS role through **OIDC**, and deploys with **SSM Run Command** (pull, migrate, `up -d`, reload Caddy,
health check with retries). The new image is built before containers are touched, so a failed build leaves the old
version serving.

## Alternatives considered
| Option | Pros | Cons |
|---|---|---|
| One EC2 + Compose + OIDC/SSM (chosen) | One box, one command, same compose locally; no keys in GitHub | No HA or autoscaling |
| ECS / App Runner | Managed scaling | More infrastructure as code for the same demo |
| Vercel for web + EC2 for API | Fast front-end deploys | Two origins (CORS), split logs |

## Consequences
Production path: ECS for api and mcp, RDS for Postgres, S3 for gold. Only the repository admin can edit Actions secrets,
so the lead loads them.

## Confidence
High.
