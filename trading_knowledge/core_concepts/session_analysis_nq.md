# Session Analysis for NQ Futures

This document maps the NQ (E-mini Nasdaq) trading day into liquidity regimes, then layers the macro calendar and day-of-week patterns on top. Use it alongside `market_structure.md` for `ICT` technical reading; this doc focuses on when to trade, not how price delivers.

The repo trades `NQ=F` (continuous front-month) on Rithmic and `MNQ` micro contracts. ES is the related equity index that drives NQ via arbitrage, so the two are treated as a pair throughout.

## The 24-Hour Globex Day

NQ trades nearly continuously from Sunday 18:00 ET through Friday 17:00 ET on CME Globex. Liquidity is not constant. The 24-hour day splits into four regimes.

### Asia / Pre-Market Thin: 18:00 ET (prev day) to 04:00 ET

Globex reopens Sunday at 18:00 ET (23:00 UTC during US DST). Through 04:00 ET the next morning, Asia desks dominate. The book is thin, spreads are wide, and moves tend to be choppy rather than directional. Treat this window as no-trade unless a specific Asia session setup applies. `kill_zone` definitions in `market_structure.md` assume you have already filtered this window out.

### European Build: 04:00 ET to 09:30 ET

Frankfurt opens at 03:00 ET (08:00 UTC DST). London follows at 04:00 ET. European volume builds through the morning but stays light relative to New York. Most institutional desks do not initiate US index positions until the 08:30 ET economic data window opens.

### NYSE Regular Session: 09:30 ET to 16:00 ET

This is where roughly two-thirds of the day's NQ volume concentrates. The first five minutes (09:30-09:35 ET) print the opening range. The 09:30 ET to 15:30 ET core window has the tightest spreads and deepest book of the day. If you only have one window to trade, this is it.

### After-Hours Decline: 16:00 ET to 20:00 ET

Liquidity tapers after the NYSE close. Spreads widen and moves become news-driven rather than flow-driven. Most day traders flatten here. The market_24/7 framing applies to crypto, not NQ.

## ES Rebalance Burst at 09:30 ET

ES (E-mini S&P 500) and NQ arbitrage tightly. At the 09:30 ET NYSE bell, ES requires rebalancing against S&P 500 constituent weights. This translates into a predictable NQ volume burst in the first 5-15 minutes of the regular session. Expect the opening range to set the tone for the morning; let it print before committing size.

## Scheduled Macro Events

### FOMC (Federal Reserve Rate Decision)

Scheduled eight times per year, typically at 14:00 ET (18:00 UTC DST) on Wednesday. The 30 minutes before and after the release are wildly volatile on rate expectations. Markets can move 200-400+ NQ points in the minutes after the statement. Avoid holding non-trivial size through FOMC unless the trade is specifically designed for the event.

### NFP (Non-Farm Payrolls)

First Friday of every month at 08:30 ET (12:30 UTC standard / 13:30 UTC DST). This is the single highest-impact data print for the dollar and rates. NQ routinely moves 100-300 points on the release. Stay flat from 08:00 ET through 09:00 ET on NFP Fridays.

### CPI and PCE

CPI releases monthly around the 10th-13th at 08:30 ET (12:30/13:30 UTC). PCE (the Fed's preferred inflation gauge) follows later in the month, also at 08:30 ET. Both move rate expectations and hit tech-heavy NQ disproportionately. Avoid trading the 08:00-09:00 ET window on release days.

## Month-End and Quarter-End Rebalancing

Institutional managers rebalance on the last trading day of each month, and again on the last trading day of each quarter. The final hour (15:00-16:00 ET) sees "window dressing" flows as performance gets marked. Quarter-end is more pronounced than month-end. NQ tends to drift in the direction of quarter-to-date performance into the close as pension and mutual fund flows cross. `contango` and `basis` dynamics in the futures curve can also amplify these rebalancing flows at month-end.

## Friday Afternoon Dynamics

Friday 15:00-16:00 ET carries two competing forces. First, profit-taking into the weekend flattens positions. Second, weekly equity options expiry at 17:00 ET (and standard monthly expiry the third Friday) pulls NQ toward large options strikes as market makers gamma-hedge into the close. Expiry week amplifies the pinning effect. Avoid breakout trades in the final 30 minutes of Friday.

## Crypto Funding Windows and Cross-Asset Spillover

BTC and ETH `perpetual_futures` on this platform fund at 00:00, 08:00, and 16:00 UTC. In ET terms, that lands at 19:00 / 04:00 / 12:00 ET (standard time) or 20:00 / 03:00 / 11:00 ET (DST). Around `funding_rate` timestamps, BTC and altcoins tend to move in correlated waves as leveraged positions rebalance and arbitrage desks adjust.

The 16:00 UTC funding print (= 12:00 ET standard / 11:00 ET DST) overlaps with the European close and US pre-market, so cross-asset correlation spikes are most visible there. If BTC gets a funding-driven move into the 08:30 ET data window, NQ's reaction often gets amplified in the same direction. Watch both.

## Day-of-Week Tendencies

### Monday

NQ often gaps at the 18:00 ET Globex reopen on weekend news. The first 15-30 minutes of cash session are gap-fill or gap-extend territory. Wait for the opening range to complete before committing. Monday trend signals are lower conviction than mid-week ones.

### Tuesday and Wednesday

Statistical mid-week. Trends established on Monday tend to continue. Highest probability window for continuation setups. Tuesday and Wednesday also host most scheduled Fed speeches outside FOMC weeks, so news flow is heavier.

### Thursday

Weekly jobless claims release lands at 08:30 ET (13:30 UTC DST). Otherwise a quieter session. Profit-taking can start Thursday afternoon ahead of Friday flows. Less institutional aggression than Tuesday/Wednesday.

### Friday

Profit-taking risk into close. Weekly options expiry at 17:00 ET creates gamma pinning that pulls NQ toward large strikes. The last hour (15:00-16:00 ET) is structurally noisy. Expiry-week and month-end Fridays are the most distorted. Reduce size and favor mean-reversion over breakout into the bell.

## Events to Flatten Through

Do not hold non-trivial size through any of these windows:

- FOMC release and the 30 minutes around it (14:00 ET, eight times per year, Wednesday)
- NFP release and the 30 minutes around it (08:30 ET, first Friday monthly)
- CPI / PCE releases (08:30 ET, monthly)
- Month-end final hour (15:00-16:00 ET on last trading day of month)
- Quarter-end final hour (15:00-16:00 ET on last trading day of quarter)
- Options expiry Friday final hour (15:00-16:00 ET on the third Friday, plus every Friday's 17:00 ET weekly print)

For all of these, the action is the same: reduce size, widen stops, or step aside entirely. The edge from holding through scheduled volatility is rarely worth the tail risk on a single contract `ticker`.

## Summary Table

| Session / Event | ET Window | Primary Features | Typical Trader Action |
|---|---|---|---|
| Asia / Pre-market thin | 18:00 ET (prev day) to 04:00 ET | Thin book, wide spreads, choppy | Avoid |
| European build | 04:00 ET to 09:30 ET | Building volume, light until 08:30 ET | Watch for 08:30 ET data |
| NYSE regular session | 09:30 ET to 16:00 ET | Highest volume, tightest spreads | Primary trading window |
| After-hours decline | 16:00 ET to 20:00 ET | Declining liquidity, news-driven | Flatten day trades |
| FOMC | 14:00 ET (8x/year, Wed) | High volatility, statement + presser | Flatten 13:30-14:30 ET |
| NFP | 08:30 ET (first Friday) | Largest macro print of the month | Flatten 08:00-09:00 ET |
| CPI / PCE | 08:30 ET (monthly) | Rates-driven volatility, tech-heavy | Flatten 08:00-09:00 ET |
| Month-end | 15:00-16:00 ET last day | Rebalancing flows, window dressing | Reduce size |
| Quarter-end | 15:00-16:00 ET last day | Pension rebalancing, amplified pinning | Reduce size, expect pinning |
| Friday expiry | 15:00-16:00 ET (weekly) | Gamma pinning into 17:00 ET | Avoid breakouts |
| Crypto funding | 12:00 ET std / 11:00 ET DST | Cross-asset correlation spikes | Watch BTC/ETH for spillover |
