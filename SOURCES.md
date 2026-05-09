# Sources, Similar Projects & Research

This document collects all relevant sources, similar tools, community discussions, and reference material discovered during the planning phase of `finanzguru-to-gwwc`.

Last updated: 2026-05-09

---

## 1. Target platforms

### Giving What We Can / EffectiveAltruism.org

| Resource | URL | Notes |
|---|---|---|
| GWWC homepage | https://www.givingwhatwecan.org | Main site for the pledge and giving guidance |
| My Giving dashboard | https://www.givingwhatwecan.org/my-giving | Donation logging UI (now redirects to EA.org) |
| Take the Pledge | https://www.givingwhatwecan.org/pledge | GWWC 10% pledge information |
| GWWC API auth endpoint | https://www.givingwhatwecan.org/api/auth/login | Exists but no documented public API for donation submission |
| EA Forum – GWWC topic | https://forum.effectivealtruism.org/topics/giving-what-we-can | Community discussion hub for GWWC |
| EA Forum – Dashboard topic | https://forum.effectivealtruism.org/topics/dashboard | Dashboard-related EA Forum posts |

**Key finding:** GWWC's "My Giving" donation tracking functionality has been migrated from `givingwhatwecan.org` to `effectivealtruism.org`. Any automation must target the EA.org platform, not the legacy GWWC URL.

**Key finding:** No public REST API exists for individual members to programmatically log donations. The only path is browser automation or direct contact with the GWWC development team.

---

### Finanzguru

| Resource | URL | Notes |
|---|---|---|
| Export help article (German) | https://hilfe.finanzguru.de/de/articles/1491650 | Overview of export functionality |
| Export help article (German, newer) | https://hilfe.finanzguru.de/de/articles/3728782-exportiere-deine-umsatze-und-analysen | Step-by-step export guide |
| Account management help | https://hilfe.finanzguru.de/de/categories/291010 | General account and settings help |

**Key finding:** Finanzguru exports transactions as `.xlsx` (PLUS subscription required) or `.csv`. Columns include booking date, payee, memo, amount, main category (`Hauptkategorie`), subcategory (`Unterkategorie`), and a contract/recurring flag (`Vertrag`). Column names are in German.

---

## 2. Similar and adjacent projects

### Finanzguru export parsers

| Project | URL | Language | Notes |
|---|---|---|---|
| finanzguru2ynab (browser) | https://github.com/ayeks/finanzguru2ynab | JavaScript | Converts Finanzguru XLSX export to YNAB CSV, runs entirely in-browser. Most mature Finanzguru parser found. |
| finanzguru_to_ynab (Python) | https://github.com/ayeks/finanzguru_to_ynab | Python | CLI script to parse Finanzguru XLSX and produce YNAB-compatible CSV import files. Good reference for column mapping. |
| phpFinanzguru | https://github.com/b-water/phpFinanzguru | PHP | PHP library that reads Finanzguru Excel exports and exposes the data as a PHP API. Useful reference for understanding the export schema. |

**Key finding:** No existing project connects Finanzguru exports to any EA/GWWC platform. The YNAB converters are the closest technical analogues for the data parsing module.

### EA / GWWC community tools

| Project | URL | Notes |
|---|---|---|
| EAMT public gitbook | https://github.com/daaronr/eamt_gitbook_public | EA market testing data analysis repo |
| EA market testing data (GWWC) | https://daaronr.github.io/eamt_data_analysis/chapters/gwwc_gg.html | Data analysis of GWWC/GlobalGiving campaigns |
| GWWC Twitter network analysis | https://github.com/ProbablyFaiz/gwwc-twitter-network | Network analysis of GWWC Twitter community |

### Donation platforms with public APIs (reference only)

These platforms are **not** the target of this tool, but are useful reference implementations for what a well-designed donation API looks like.

| Platform | URL | Notes |
|---|---|---|
| Every.org Charity API | https://www.every.org/charity-api | Free API for charity lookup and donations |
| GlobalGiving API | https://www.globalgiving.org/api/overview/ | REST API for donation management |
| Daffy API | https://www.daffy.org/resources/api-for-developers | Donor-Advised Fund with developer API |
| 360Giving API | https://www.360giving.org/explore/technical/api/ | Open grants data API (UK-focused) |
| Adyen Giving API | https://docs.adyen.com/online-payments/donations/api-only/ | Payment processor donation API |
| Pledge.to APIs | https://www.pledge.to/products/apis | Embedded giving APIs |

---

## 3. Community discussions

### EA Forum

| Post | URL | Relevance |
|---|---|---|
| "How do you track your donations?" | https://forum.effectivealtruism.org/posts/uBLhAc9ensFY9hY4N/how-do-you-track-your-donations | 2021 thread showing most GWWC members use manual spreadsheets — confirms the gap this project fills |
| "How to stay motivated to donate?" | https://forum.effectivealtruism.org/posts/JCSDjAicym7rnH6dA/how-to-stay-motivated-to-donate | Touches on friction of donation tracking |
| "Recommitting to Giving" | https://forum.effectivealtruism.org/posts/3vcpERphsumgEzqeB/recommitting-to-giving-a-personal-update | Community member's reflection on giving tracking |
| "Expanding your impact beyond donations" | https://forum.effectivealtruism.org/posts/Lwr6GLhpLCjnRAKwX/expanding-your-impact-effective-giving-beyond-donations | Broader effective giving context |
| GWWC pledge discussion | https://forum.effectivealtruism.org/posts/ebyQSRqdZLBTzSDMT/contra-the-giving-what-we-can-pledge | Critical perspective on the pledge |

**Key finding:** The 2021 EA Forum thread on donation tracking attracted significant engagement and confirmed that the community widely uses spreadsheets or manual entry. No automated bank-import tool was mentioned. This project would be the first of its kind shared in this community.

### Reddit

| Thread | URL | Relevance |
|---|---|---|
| r/EffectiveAltruism – GWWC pledge pre/post tax | https://www.reddit.com/r/EffectiveAltruism/comments/m0kwiv/giving_what_we_can_pledge_do_you_donate_10_pretax/ | Community discussion on donation logistics |
| r/financialindependence – giving philosophy | https://www.reddit.com/r/financialindependence/comments/t7cfsc/what_is_your_philosophy_on_givingdonating/ | Broader giving and tracking discussion |

**Key finding:** No Reddit posts were found describing any automation or scripting tool for GWWC donation logging.

---

## 4. Browser automation references

| Resource | URL | Notes |
|---|---|---|
| Playwright for Python (official docs) | https://playwright.dev/python/ | Primary automation framework recommended for this project |
| r/Python – Playwright vs Selenium | https://www.reddit.com/r/Python/comments/yeuqw6/web_automation_dont_use_selenium_use_playwright/ | Community consensus strongly favours Playwright over Selenium for modern web automation |
| r/selenium – Playwright for production | https://www.reddit.com/r/selenium/comments/1n23a1j/selenium_vs_playwright_for_productionready_web/ | More recent comparison for production use cases |
| AI-powered browser testing library | https://www.reddit.com/r/Python/comments/1jpo96u/i_built_an_opensource_aipowered_library_for_web/ | Open source AI-powered Playwright wrapper, possibly relevant for resilient selector strategies |

---

## 5. Related tooling and infrastructure

| Tool | URL | Notes |
|---|---|---|
| Outbank – import from Finanzguru | https://help.outbankapp.com/en/kb/articles/wie-kann-ich-meine-ums-tze-aus-finanzguru-in-outbank-importieren | Shows that Finanzguru exports are already used for cross-app import workflows |
| GWWC engineering job post | https://www.facebook.com/givingwhatwecan/posts/giving-what-we-can-gwwc-is-looking-for-a-full-stack-software-engineer-to-help-ma/ | Confirms GWWC has an active engineering team that could be contacted about an official API |
| Urban Institute Giving Dashboard | https://github.com/UrbanInstitute/giving-dashboard | Open source giving dashboard (US-focused, unrelated to GWWC but architecturally interesting) |
| Gitcoin Tithing mechanism | https://gitcoin.co/mechanisms/tithing | Automated giving mechanism in web3 context, interesting reference for recurring giving automation |

---

## 6. Sharing and open source plan

When the tool is functional and tested, the intended distribution strategy is:

1. **GitHub** — Public repository at https://github.com/jannikwagner/finanzguru-to-gwwc
2. **EA Forum** — Post under the GWWC tag at https://forum.effectivealtruism.org/topics/giving-what-we-can (preferred over Reddit due to audience fit)
3. **GWWC / EA.org team** — Contact the development team directly to share the project as evidence of community demand for an official API or import feature
4. **Reddit** — Share in r/EffectiveAltruism and r/PersonalFinanceGermany as secondary distribution

---

## 7. Research gaps and unknowns

- **EA.org My Giving form structure:** The exact DOM selectors, field names, and submission flow of the EA.org donation entry form have not yet been inspected. This is required before Phase 4 implementation.
- **EA.org authentication:** It is not confirmed whether EA.org supports direct email/password login or exclusively OAuth. The `api/auth/login` endpoint exists but is undocumented publicly.
- **Finanzguru exact column names:** Column names may vary slightly depending on export locale, app version, or account type. Must be validated against the user's actual export file before finalizing the parser.
- **Official API plans:** It is unknown whether GWWC / EA.org has plans to release a public API for donation logging. Contacting their team is recommended.
