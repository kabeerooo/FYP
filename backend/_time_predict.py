import time, prediction_engine as pe
tickers = ['AAPL', 'NVDA', 'TSLA', 'GOLD']
for t in tickers:
    s = time.time()
    r = pe.predict_asset(t, '7d')
    conf = r['confidence_score']
    print(f"{t}: {time.time()-s:.2f}s  conf={conf:.0f}%")
