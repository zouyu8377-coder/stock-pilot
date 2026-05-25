# Sanitized Trial Run Guide

## 1. Recommendation

Start with a sanitized demo portfolio. Do not import a full real account yet.

Current system is suitable for checking whether the evidence layering and Analysis Packet format help decision-making. It is not yet cleared for full real account operation.

## 2. Trial Scenario

Use either the existing Phase 3 acceptance samples or manually enter a small demo portfolio.

Suggested demo structure:

| Item | Approx amount | Notes |
| --- | ---: | --- |
| Cash | 30000 | Display separately as cash available |
| Reverse repo | 20000 | Display separately from cash |
| AI/PCB holding | 20000 | One primary AI/PCB exposure |
| Metal resource holding | 20000 | One primary metal/resource exposure |
| Composite exposure holding | 10000 | `primary_theme` belongs to one theme; `theme_tags` include related risks and `COMPOSITE_EXPOSURE` |

Manual evidence:

- include=true: one sanitized shareholder-count note.
- include=true: one sanitized market observation.
- include=false: one private or irrelevant note that must not appear in Packet.

Recommended flow:

1. Enter or load the demo portfolio.
2. Add non-sensitive manual evidence only.
3. Generate a single-stock Packet.
4. Generate a portfolio Packet.
5. Copy Markdown to a blank plain-text editor.
6. Check readability, privacy notice, evidence layering, missing data, and boundaries.
7. If desired, the user may manually submit the sanitized Packet to an external LLM to observe analysis quality.

## 3. What to Observe

- Whether evidence is clearly separated into `auto_fact`, `auto_signal`, `manual_account`, `manual_evidence`, and `system_hypothesis`.
- Whether missing data is explicit enough.
- Whether theme relations help understand risk overlap.
- Whether the Packet is more useful than directly asking an AI without evidence.
- Which page steps are most inconvenient for real use.
- Whether Markdown copy is complete and readable.

## 4. Do Not Enter Yet

Do not enter the following during the sanitized trial:

- Full real cash balance.
- Full real costs.
- Full real holdings.
- Real account screenshots.
- Broker exports.
- Private attachments.
- Undesensitized trade plans.
- Token or API keys.

## 5. Conditions Before Small Real Portfolio Trial

Move from sanitized trial to a small real manually entered portfolio only after:

- Browser copy acceptance is completed by the user.
- User confirms risk limits and liquidity treatment.
- At least one real low-frequency fact enters Packet successfully under the user's Tushare environment, or the user accepts unavailable boundaries.
- User confirms Packet generation does not auto-send data externally.
- Git ignore and local data isolation remain stable.
- The first real trial uses only a small subset of holdings, not the full account.
