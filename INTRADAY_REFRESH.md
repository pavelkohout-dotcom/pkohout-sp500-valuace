# Intraday refresh — 5 November 2026

VIX and S&P 500 are collected at most once per 30 minutes during the regular US equity session and for one hour after close, allowing the delayed final VIX observation to arrive. Quote timestamps are never replaced by download timestamps. Browser checks remain once per minute; they do not query Yahoo directly.

A bounded worker stays alive for 300 minutes, including overnight/weekends, checking its calendar once per minute. On successful completion it explicitly dispatches its successor using the repository GITHUB_TOKEN (actions:write). A push bootstrap lasts one minute so handoff can be verified. Concurrency serializes workers; the four-hour cron is a recovery mechanism, not the primary clock. Existing checked_at prevents duplicate market downloads across handoffs. This intentionally occupies a runner even when the market is closed; it does not require a running user computer or a personal token. Disable the workflow in Actions to stop the chain.

GitHub service/runner outages can still interrupt the chain. Failures are reported by Actions; a failed collector is not silently marked successful and does not immediately self-retry forever. Cron can recover later. This is not a guaranteed-availability market data service.

Freshness budget is 60 minutes during trading: 30-minute collection, approximately 15-minute VIX source delay, and delivery allowance. During the first hour after open, a previous-session quote is explicitly labelled waiting for the first quote. Outside the session plus final-delivery window, only a quote at or after the latest session close is labelled market closed. Missing final quotes remain stale. Holidays and early closes follow the bundled official NYSE 2026–2028 calendar; unknown future dates fail conservatively. Unexpected exchange closures require a calendar update.

Equity valuation uses the latest S&P 500 observation and the latest validated MZM denominator, preserving the 0.15 reference ratio. MZM remains a slower economic series.

The public Wix page embeds its own HTML copy. Repository/data updates do not replace that copy. Replace the HTML embed with investicni_pristrojova_deska.html and publish Wix to activate new labels.

References:
- https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow
- https://www.nyse.com/trade/hours-calendars
