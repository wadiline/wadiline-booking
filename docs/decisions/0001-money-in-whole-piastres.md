# 0001 Money in whole piastres

Status: Accepted
Date: 2024-04-14

**Context.** Floating-point amounts lost piastres on receipts.

**Decision.** Store and calculate all money in whole piastres.

**Consequences.** Format amounts as EGP at the API and command-line boundaries.
