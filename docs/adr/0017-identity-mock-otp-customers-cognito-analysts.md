# 0017. Identity: mock session + OTP for customers, Cognito for analysts

- **Status:** Accepted
- **Date:** 2026-10-03
- **Deciders:** Freddy · **Owner:** @gianzk
- **Related:** specs 05, 08

## Context
The challenge states that an id number alone does not prove identity. Dataset customers are synthetic, so they cannot
receive real one-time codes. Analyst actions change money-related state and must have a real actor in the audit log.
Judges need to try both sides.

## Decision
- **Customers:** a mock identity — pick a demo customer, receive an OTP shown on screen, session TTL 15 minutes; tools
  read the `customer_id` only from the session. Expired sessions return `SESSION_EXPIRED`.
- **Analysts:** an **Amazon Cognito** user pool with its hosted login; the backend validates the JWT and takes the
  `actor_id` of every action from the token. Accounts for the three team members and one "judge" account whose password
  goes only in the submission e-mail. No Amplify Hosting is needed.

## Alternatives considered
| Option | Pros | Cons |
|---|---|---|
| Mock OTP + Cognito (chosen) | Real actor in the audit; managed; MFA available | Cognito setup |
| Basic auth at the proxy | Minutes to set up | No real actor; weak |
| Real SSO / bank identity provider | Production-like | Out of scope |

## Consequences
Production replaces the mock with the bank's customer authentication and Cognito with the bank's workforce identity
provider; the session and actor contracts stay the same.

## Confidence
High.
