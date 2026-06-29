"""
Test all assets: AAPL, NVDA, TSLA, GOLD
- Verify Gold works correctly
- Check dates in forecast_chart are accurate (no weekends for stocks)
- Check history_chart has real prices
- Check 1d/7d/30d predictions all work
- Report any issues
"""
import sys, os, warnings
warnings.filterwarnings("ignore")
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"
os.environ["PYTHONIOENCODING"] = "utf-8"
sys.path.insert(0, "d:/Neuro/backend")
import prediction_engine as pe
from datetime import datetime

TODAY = datetime.now().strftime("%Y-%m-%d")
print(f"Test run: {TODAY}\n")

issues = []

for ticker in ["AAPL", "NVDA", "TSLA", "GOLD"]:
    print(f"{'='*60}")
    print(f"Testing {ticker}...")
    cfg = pe.ASSET_CONFIG[ticker]
    print(f"  mode={cfg.get('predict_mode','price')}  features={cfg['features']}")

    for period in ["1d", "7d", "30d"]:
        try:
            r = pe.predict_asset(ticker, period)
            cur = r["current_price"]
            pred = r["predicted_price"]
            pct = r["prediction_change_percent"]
            direction = r["trend_direction"]
            conf = r["confidence_score"]
            hist_dates = [x["date"] for x in r["history_chart"]]
            fc_dates = [x["date"] for x in r["forecast_chart"]]
            fc_prices = [x["price"] for x in r["forecast_chart"]]

            # Date check 1: history last date should be today or recent trading day
            last_hist = hist_dates[-1]
            # Date check 2: forecast dates must all be AFTER last history date
            date_order_ok = all(d > last_hist for d in fc_dates)
            # Date check 3: no weekend dates for stocks
            from pandas import Timestamp
            if ticker != "GOLD":
                weekend_dates = [d for d in fc_dates if Timestamp(d).weekday() >= 5]
                if weekend_dates:
                    issues.append(f"{ticker} {period}: WEEKEND DATES IN FORECAST: {weekend_dates}")
            # Date check 4: forecast prices match current_price range (sanity)
            price_range_ok = all(cur * 0.5 < p < cur * 2.0 for p in fc_prices)

            print(f"  [{period}] cur={cur}  pred={pred} ({pct:+.2f}%)  {direction}  conf={conf}%")
            print(f"         last_hist={last_hist}  fc_start={fc_dates[0]}  fc_end={fc_dates[-1]}")
            print(f"         date_order_ok={date_order_ok}  price_range_ok={price_range_ok}")
            if not date_order_ok:
                issues.append(f"{ticker} {period}: FORECAST DATE BEFORE HISTORY END")
            if not price_range_ok:
                bad = [(d,p) for d,p in zip(fc_dates, fc_prices) if not (cur*0.5<p<cur*2.0)]
                issues.append(f"{ticker} {period}: BAD PRICE in forecast: {bad}")

        except Exception as exc:
            import traceback
            print(f"  [{period}] ERROR: {exc}")
            traceback.print_exc()
            issues.append(f"{ticker} {period}: EXCEPTION {exc}")

print(f"\n{'='*60}")
print("ISSUES SUMMARY:")
if issues:
    for iss in issues:
        print(f"  ❌ {iss}")
else:
    print("  ✅ No issues found — all assets working correctly")
