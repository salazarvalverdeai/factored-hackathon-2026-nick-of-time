# Judge guide: where it lives and where to link it (draft)

Status: draft note, 2026-10-05. No file under `apps/web/` was edited.

## Where the guide lives
- The judges' tour is section 1, "For judges: a 5-minute tour", of [`docs/user-guide.md`](../user-guide.md). It has a
  minute-by-minute table (what to do, what it proves, which criterion) and a table of where the evidence for each
  criterion lives. The same file covers customers (section 2) and analysts.
- The guide is marked **skeleton**: sections tagged *(pending UI)* are completed as specs 07, 08, 13 and 16 land, and its
  screenshots come from the Playwright suite (`apps/web/e2e/docs-screenshots.spec.ts` to `docs/assets/guide/`), per its
  own header. The judge account's password goes only in the submission e-mail (`apps/api/README.md`, Accounts).
- Two links in its evidence table are still pending: a security model page and the model card (`docs/user-guide.md`).

## Proposed in-app link
The home page is `apps/web/app/page.tsx`; its header and the "How it works" block are what the guide tells judges to
read first (minute 0-1). Proposal for the web owner (GianMarco, per CLAUDE.md owners):

1. **Header, right side, next to the theme toggle:** a link "Judge guide" (UI text is English, CLAUDE.md conventions),
   opening in a new tab. Visible on every page, so a judge never has to find it.
2. **Home page, under "How it works":** a short call-to-action "Take the 5-minute tour" pointing to the same target.
3. **Target:** the rendered section on the repository (anchor `#1-for-judges-a-5-minute-tour` of `docs/user-guide.md` on
   GitHub), or, better for a closed repository, a static page `/guide` in the web app generated from the same Markdown so
   the link works without GitHub access. Choose after the lead decides whether the repository is public at judging time
   (not stated in the repo; open question).
4. Keep the brand rules of `docs/brand/BRAND.md` (Sora type, calm voice); no new color.

Not done here by design: the lead asked not to touch `apps/web/`, and the final guide text still depends on specs 07, 08
and 13 reaching live mode.
