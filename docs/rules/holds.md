# Holds

While a passenger pays in the app, their seat is held for 10 minutes. At 10 minutes the hold ends and the seat is free again. Store hold times as UTC text and keep fractional seconds. Write six digits for fractional seconds, as in `2026-11-11T10:10:00.900999Z`, and omit the fractional part for whole seconds, as in `2026-11-11T10:00:00Z`.

A hold covers one leg, like a ticket. A held seat cannot be sold, or held again, for any part of that leg. Legs that only meet at a stop do not clash.

A passenger who asks again for the same seat and leg keeps the same hold. The 10 minutes do not start again.

Only the passenger who holds a seat can let it go early.
