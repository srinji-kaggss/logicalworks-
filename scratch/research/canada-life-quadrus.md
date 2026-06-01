# Canada Life & Quadrus Investment Services — Grounded Research

Compiled 2026-06-01. Every claim carries a source URL and a confidence tag:
**grounded-primary** (issuer / regulator), **grounded-secondary** (reputable trade/encyclopedia), **unverified** (single low-trust source).
Tooling note: WebFetch / Bash(crwl) / Firecrawl-scrape were unavailable (permission denials + Firecrawl 402 out-of-credits). All findings are from WebSearch result extracts of the cited primary/secondary pages — direct full-page primary scraping was blocked, so primary-source claims are marked grounded-primary by virtue of the cited issuer/regulator URL but were not byte-verified by full fetch. Treat anything needing exact figures (AUM, dates) as confirm-on-fetch.

---

## 1. Corporate identity & structure

- **Legal name (insurer):** The Canada Life Assurance Company. On **January 1, 2020**, three insurers — The Great-West Life Assurance Company, London Life Insurance Company, and The Canada Life Assurance Company — plus two holding companies (Canada Life Financial Corporation and London Insurance Group Inc.) amalgamated into a single company that took the name **The Canada Life Assurance Company**, operating under the single **Canada Life** brand. Received final approval from Canada's Minister of Finance; in-force policy terms were unchanged. *grounded-primary* — https://www.canadalife.com/about-us/amalgamation.html ; https://www.greatwestlifeco.com/news-events/news/great-west-lifeco-announces-plan-to-proceed-with-amalgamation-of.html ; https://en.wikipedia.org/wiki/Canada_Life

- **Parent / ownership chain (top-down):** Power Corporation of Canada (Desmarais family control) → Power Financial Corporation (wholly owned) → **Great-West Lifeco Inc.** (publicly traded; TSX: GWO) → **The Canada Life Assurance Company** (Lifeco's largest subsidiary). Power Corp holds ~**70.55%** of Lifeco's common shares / ~65% of voting rights as of Dec 31, 2024. *grounded-secondary* — https://en.wikipedia.org/wiki/Great-West_Lifeco ; https://pestel-analysis.com/blogs/owners/greatwestlifeco
  - Note: one secondary source phrases it as "Lifeco owns 100% of The Great-West Life Assurance Company" — stale post-2020 (Great-West Life no longer exists as a separate entity; it is now Canada Life). Flagged contradiction. *grounded-secondary*

- **Canada Life ↔ Quadrus relationship:** Quadrus Investment Services Ltd. is a **subsidiary of The Canada Life Assurance Company** and a member of the Great-West Lifeco group. Quadrus is Canada Life's retail mutual-fund **dealer/distribution arm**. VERIFIED. *grounded-primary* — https://www.quadrusinvestmentservices.com/about-us.html ; https://www.ciro.ca/investors/choosing-investment-advisor/dealers-we-regulate/quadrus-investment-services-ltd

- **Quadrus legal name / bilingual name:** Quadrus Investment Services Ltd. / Services D'Investissement Quadrus Ltée. **LEI: 549300UPU7EQVWQZ6H43.** *grounded-secondary* — https://lei.bloomberg.com/leis/view/549300UPU7EQVWQZ6H43 ; https://opengovca.com/corporation/569747

- **HQ — Canada Life:** Winnipeg, Manitoba (corporate HQ; major operations also in London, ON and Toronto). *grounded-secondary* — https://en.wikipedia.org/wiki/Canada_Life

- **HQ — Quadrus:** **255 Dufferin Avenue, London, ON N6A 4K1** (the Canada Life campus). A secondary office is at 1 City Centre Dr, Mississauga, ON. *grounded-secondary* — https://opengovca.com/corporation/569747 ; https://www.quadrusinvestmentservices.com/
  - **CONTRADICTION FLAG:** An early WebSearch summary asserted Quadrus is "based in Halifax, Nova Scotia." This appears to be an AI-summary error / conflation with Excel Funds or IPC heritage. Multiple corporate-registry and Canada Life-campus sources place Quadrus HQ in **London, ON**. Treat London, ON as correct; Halifax = unverified/likely-wrong.

- **Key corporate dates:**
  - 2003: Great-West Lifeco acquired Canada Life Financial for ~C$7.3B (became Canada's largest insurer). *grounded-secondary* — https://www.encyclopedia.com/books/politics-and-business-magazines/great-west-lifeco-inc
  - Jan 1, 2020: tri-company amalgamation → The Canada Life Assurance Company / single brand. *grounded-primary* (above)
  - **Jan 1, 2022: Excel Private Wealth Inc. amalgamated into Quadrus**, continuing as Quadrus Investment Services Ltd. *grounded-primary* — https://www.ciro.ca/newsroom/publications/amalgamation-excel-private-wealth-inc-and-quadrus-investment-services-ltd

---

## 2. Regulatory standing

- **Quadrus — current regulator:** Member / regulated **Dealer of CIRO (Canadian Investment Regulatory Organization)**, in the mutual fund dealer category. Formerly a Member of the MFDA (Mutual Fund Dealers Association of Canada). VERIFIED. *grounded-primary* — https://www.ciro.ca/investors/choosing-investment-advisor/dealers-we-regulate/quadrus-investment-services-ltd
  - SRO history context: MFDA and IIROC amalgamated into the **New SRO on Jan 1, 2023**, renamed **CIRO on June 1, 2023**; MFDA IPC and CIPF merged into a single CIPF. So Quadrus's regulator transitioned MFDA → CIRO automatically. *grounded-primary* — https://www.ciro.ca/newsroom/publications/new-self-regulatory-organization-canada-and-canadian-investor-protection-fund-officially-launch ; https://en.wikipedia.org/wiki/Canadian_Investment_Regulatory_Organization
  - Securities-law oversight by province: as a registered dealer, Quadrus is also subject to provincial securities commissions (CSA members) overseeing CIRO. *grounded-primary* — https://www.securities-administrators.ca/new-sro/

- **Canada Life — insurer regulation:** Federally regulated/supervised by **OSFI** (Office of the Superintendent of Financial Institutions) as a federally registered life insurer; also subject to provincial insurance regulators (e.g., AMF in Québec, FSRA in Ontario) and the Superintendent of Insurance (Saskatchewan) for market-conduct/consumer matters. *grounded-primary* — https://www.osfi-bsif.gc.ca/en/supervision/financial-institutions ; https://www.canadalife.com/support/consumer-information/customer-complaints-ombudsman.html

- **Disciplinary / enforcement history (Quadrus):** There IS public enforcement history at the MFDA/CIRO level.
  - **2021 MFDA settlement** (hearing by videoconference Nov 23, 2021): involved pre-signed/partially-completed client forms and discretionary trading; references a prior penalty (fine $75,000 + costs $20,000). *grounded-primary* — https://www.ciro.ca/media/5211/download ; https://www.ciro.ca/rules-and-enforcement/enforcement/quadrus-investment-services-ltd-pre-excel-0
  - **2016-era settlement**: fine $15,000 + costs $7,500. *grounded-primary* — https://www.ciro.ca/media/4652/download
  - Individual-rep enforcement matters also exist (e.g., proceedings naming dealing representatives at Quadrus). *grounded-primary* — CIRO enforcement index (above)
  - These are typical dealer-supervision/clerical-conduct matters (pre-signed forms is the single most common MFDA-era category), not systemic-fraud findings. Severity = moderate/routine for a large dealer. *grounded-secondary* (interpretation)

---

## 3. Business — what each actually does

- **Canada Life:** Full-line insurance & wealth/retirement provider — individual life & health insurance, group/workplace benefits and retirement (group pensions/benefits), individual wealth (segregated funds, annuities, mutual funds), and asset management. *grounded-primary* — https://www.greatwestlifeco.com/who-we-are/our-companies/canada-life.html

- **Quadrus:** A **mutual fund dealer / fund-distribution arm**. Distributes the **Canada Life Mutual Funds** shelf and the legacy **Quadrus Group of Funds**, through a network of dealing representatives (advisors). Described as one of Canada's larger mutual fund dealers. *grounded-primary* — https://www.quadrusinvestmentservices.com/about-us.html ; https://www.canadalife.com/investing-saving/mutual-funds/canada-life-mutual-funds.html

- **Fund-shelf restructuring (recent, important):**
  - **Sept 2023:** Canada Life launched a new **Canada Life Mutual Funds** shelf (18 new funds) that **rebrands the existing Quadrus Group of Funds** shelf. Funds managed/sub-advised via **Mackenzie Investments** (a sister Power-group asset manager); manager is **Canada Life Investment Management Ltd. (CLIML)**; distributed through Quadrus. *grounded-primary* — https://www.canadalife.com/about-us/news-highlights/news/canada-life-announces-launch-of-new-mutual-fund-shelf.html
  - **Nov 2023:** CLIML announced lineup changes — fund mergers, terminations, sub-advisory changes, fee reductions, name/strategy changes. *grounded-primary* — https://www.newswire.ca/news-releases/canada-life-investment-management-ltd-announces-changes-to-its-mutual-fund-lineup-839712325.html
  - **2024:** CLIML added **Investment Planning Counsel (IPC Investment Corporation & IPC Securities Corporation)** as additional affiliated principal distributors for certain funds, alongside Quadrus. *grounded-primary* — https://www.canadalife.com/about-us/news-highlights/news/canada-life-investment-management-ltd-announces-additional-affiliated-principal-distributors-for-certain-mutual-funds.html

- **Scale (parent-level; entity-specific Quadrus AUM not found in public sources):**
  - Great-West Lifeco **assets under administration > C$3.2 trillion** at Dec 31, 2024; ~33,250 employees; brands Canada Life / Empower / Irish Life serving 40M+ customer relationships. *grounded-primary* — https://www.greatwestlifeco.com/content/dam/gwlco/documents/reports/2025/lifeco-2024-annual-report.pdf
  - Quadrus-specific AUM / exact advisor count: **NOT FOUND** in primary sources during this pass — gap. *unverified*

---

## 4. Leadership & ownership chain

- **Great-West Lifeco CEO:** **Paul A. Mahon**, President & CEO. *grounded-primary* — https://www.greatwestlifeco.com/news-events/news/canada-life-announces-retirement-of-jeff-macoun.html
- **Canada Life (Canadian operations) President & COO:** **Fabrice Morin**, effective **Feb 16, 2024** (succeeding Jeff Macoun, who retired after 40+ yrs; was President & COO Canada for ~6 yrs). Morin joined Canada Life in 2019 from Power Corporation; sits on Lifeco's executive management committee. *grounded-primary* — https://www.canadalife.com/about-us/news-highlights/news/canada-life-announces-retirement-of-jeff-macoun.html ; https://www.greatwestlifeco.com/who-we-are/leadership/fabrice-morin.html
- **Ownership chain (repeat for clarity):** Desmarais family → Power Corporation of Canada → Power Financial Corporation → Great-West Lifeco Inc. (TSX: GWO) → The Canada Life Assurance Company → Quadrus Investment Services Ltd. *grounded-secondary* — https://en.wikipedia.org/wiki/Great-West_Lifeco

---

## 5. What a person dealing with them should know

- **Quadrus complaints process (investments):** First contact Quadrus internally (1-888-532-3322). Quadrus acknowledges within **5 business days**, responds in writing generally within **90 days**. If unsatisfied, escalate to **OBSI (Ombudsman for Banking Services and Investments)** and/or the regulator (CIRO). *grounded-primary* — https://www.quadrusinvestmentservices.com/customer-complaints.html
  - Context: as of **Nov 1, 2024** OBSI is the single statutory external dispute-resolution body for investments under CSA rules (worth verifying current OBSI binding-decision status). *grounded-secondary* — general CSA/OBSI framework.
- **Canada Life complaints process (insurance):** Internal complaint/ombudsman first; then escalate externally to **OLHI (OmbudService for Life and Health Insurance)** for life/health/disability/seg-fund/annuity products, or to **AMF** (Québec) / **Superintendent of Insurance (Saskatchewan)**. OLHI is free, independent, targets review within **120 days**; ~99% of Canadian L&H insurers are members. *grounded-primary* — https://www.canadalife.com/support/consumer-information/customer-complaints-ombudsman.html ; https://olhi.ca/complaints/
- **Investor protection:** Quadrus client assets fall under **CIPF** coverage (post-2023 merged fund). *grounded-primary* — https://www.ciro.ca/newsroom/publications/new-self-regulatory-organization-canada-and-canadian-investor-protection-fund-officially-launch
- **Recent changes (last ~2 yrs) to know:** (a) leadership transition to Fabrice Morin (Feb 2024); (b) Quadrus Group of Funds rebranded into Canada Life Mutual Funds, Mackenzie-managed (Sept 2023); (c) fund lineup rationalization / mergers (Nov 2023); (d) IPC added as co-distributor (2024); (e) Excel Private Wealth folded into Quadrus (Jan 2022). All *grounded-primary* per Section 3.

---

## Open gaps / to verify with full fetch
1. Quadrus standalone AUM and exact advisor headcount — not in public sources found.
2. Exact OBSI binding-decision authority status as of 2025/2026 — verify on OBSI site.
3. Halifax vs London, ON HQ — resolved to London, ON via registry, but worth a CIRO-page byte-confirm.
4. Full-page primary scrapes were blocked this session; if precision matters, re-run with WebFetch/crwl enabled.

## Contradictions flagged
- Quadrus HQ: "Halifax, NS" (AI-summary, likely wrong) vs "London, ON" (registry + Canada Life campus) → **London, ON**.
- "Lifeco owns 100% of Great-West Life Assurance Company" (secondary, pre-2020 framing) vs post-2020 reality (Great-West Life no longer separate; it is now Canada Life). → use post-2020 structure.
