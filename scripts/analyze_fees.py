import csv, glob

log_dir = '/home/ubuntu/arb/logs/v12/'
files = sorted(glob.glob(log_dir + 'trades_v2_xrp_20260414*.csv'))
if not files:
    files = sorted(glob.glob(log_dir + 'trades_v2_xrp_*.csv'))

print("Using file:", files[-1])
with open(files[-1]) as fp:
    reader = csv.DictReader(fp)
    rows = list(reader)

print(f"Total rows: {len(rows)}")
prev_bnb = None
total_gross = 0.0
total_bnb_fee = 0.0
total_real_net = 0.0

for i in range(min(15, len(rows))):
    row = rows[i]
    bnb = float(row.get('잔여BNB', 0) or 0)
    bnb_used = (prev_bnb - bnb) if prev_bnb is not None else 0
    bnb_val = bnb_used * 607
    invest = float(row.get('투입금액(USD)', 0) or 0)
    receive = float(row.get('수취금액(USD)', 0) or 0)
    gross = receive - invest
    est_fee = float(row.get('수수료추정(USD)', 0) or 0)
    real_net = gross - bnb_val
    pct = gross / invest * 100 if invest > 0 else 0
    if prev_bnb is not None:
        total_gross += gross
        total_bnb_fee += bnb_val
        total_real_net += real_net
    print(f"  Trade {row.get('거래번호','?')}: gross={gross:.4f} ({pct:.4f}%), est_fee={est_fee:.4f}, BNB_used={bnb_used:.6f}=${bnb_val:.4f}, real_net={real_net:.4f}")
    prev_bnb = bnb

print()
print(f"Summary (trades 2-15):")
print(f"  Total gross profit: {total_gross:.4f}")
print(f"  Total BNB fee cost: {total_bnb_fee:.4f}")
print(f"  Total real net:     {total_real_net:.4f}")
print(f"  Avg per trade: gross={total_gross/14:.4f}, bnb_fee={total_bnb_fee/14:.4f}, real_net={total_real_net/14:.4f}")

# Also analyze all coins
print()
print("=== ALL COINS ANALYSIS ===")
coins = ['trx', 'doge', 'xrp', 'sol', 'bnb', 'ada']
all_files = []
for coin in coins:
    all_files += sorted(glob.glob(log_dir + f'trades_v2_{coin}_*.csv'))

all_rows = []
for f in all_files:
    try:
        with open(f) as fp:
            reader = csv.DictReader(fp)
            for row in reader:
                try:
                    invest = float(row.get('투입금액(USD)', 0) or 0)
                    receive = float(row.get('수취금액(USD)', 0) or 0)
                    if invest > 0:
                        all_rows.append(row)
                except:
                    pass
    except:
        pass

csv_pnl_total = sum(float(r.get('순수익(USD)', 0) or 0) for r in all_rows)
est_fee_total = sum(float(r.get('수수료추정(USD)', 0) or 0) for r in all_rows)
gross_total = sum(float(r.get('수취금액(USD)', 0) or 0) - float(r.get('투입금액(USD)', 0) or 0) for r in all_rows)

print(f"Total trades: {len(all_rows)}")
print(f"Total gross (receive-invest): {gross_total:.4f}")
print(f"Total CSV-estimated fee: {est_fee_total:.4f}")
print(f"Total CSV순수익: {csv_pnl_total:.4f}")
print(f"If real BNB fee = 0.15% of trade_size:")
approx_real_fee = sum(float(r.get('투입금액(USD)', 0) or 0) * 0.0015 for r in all_rows)
print(f"  Estimated real fee total: {approx_real_fee:.4f}")
print(f"  Estimated real net total: {gross_total - approx_real_fee:.4f}")
