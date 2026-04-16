"""
실제 BNB 소비량 vs 설정 수수료율 비교 분석
"""
import csv, glob, os

log_dir = '/home/ubuntu/arb/logs/v12/'
coins = ['trx', 'doge', 'xrp', 'sol', 'bnb', 'ada']

# 가장 거래 많은 최신 CSV에서 연속 BNB 소비 분석
print("=== BNB 소비량 vs 설정 fee_rate 분석 ===\n")

# XRP 최대 파일에서 연속 거래 분석
xrp_files = sorted(glob.glob(log_dir + 'trades_v2_xrp_*.csv'))
biggest = max(xrp_files, key=os.path.getsize)
print(f"분석 파일: {biggest}")

with open(biggest) as fp:
    reader = csv.DictReader(fp)
    rows = list(reader)

print(f"총 거래수: {len(rows)}\n")

# 연속 거래 BNB 소비 분석 (BNB 변화로 실제 수수료 계산)
bnb_changes = []
for i in range(1, min(30, len(rows))):
    prev = rows[i-1]
    curr = rows[i]
    try:
        bnb_prev = float(prev.get('잔여BNB', 0) or 0)
        bnb_curr = float(curr.get('잔여BNB', 0) or 0)
        bnb_used = bnb_prev - bnb_curr
        invest = float(curr.get('투입금액(USD)', 0) or 0)
        receive = float(curr.get('수취금액(USD)', 0) or 0)
        gross = receive - invest
        est_fee = float(curr.get('수수료추정(USD)', 0) or 0)
        net_csv = float(curr.get('순수익(USD)', 0) or 0)

        if invest > 100 and bnb_used > 0:
            bnb_val = bnb_used * 607  # approx BNB price
            fee_rate_actual = bnb_val / invest
            real_net = gross - bnb_val
            bnb_changes.append({
                'trade': curr.get('거래번호'),
                'invest': invest,
                'gross': gross,
                'est_fee': est_fee,
                'bnb_used': bnb_used,
                'bnb_val': bnb_val,
                'fee_rate_actual': fee_rate_actual,
                'real_net': real_net,
                'net_csv': net_csv,
            })
            print(f"  Trade {curr.get('거래번호')}: invest={invest:.0f}, gross={gross:.4f}, "
                  f"bnb={bnb_used:.6f}=${bnb_val:.4f}, "
                  f"actual_fee_rate={fee_rate_actual*100:.4f}%, real_net={real_net:.4f}")
    except Exception as e:
        pass

if bnb_changes:
    avg_fee_rate = sum(x['fee_rate_actual'] for x in bnb_changes) / len(bnb_changes)
    avg_gross = sum(x['gross'] for x in bnb_changes) / len(bnb_changes)
    avg_bnb_val = sum(x['bnb_val'] for x in bnb_changes) / len(bnb_changes)
    avg_real_net = sum(x['real_net'] for x in bnb_changes) / len(bnb_changes)
    print(f"\n평균 실제 fee_rate: {avg_fee_rate*100:.4f}% (설정값: 0.04%)")
    print(f"평균 gross spread:  {avg_gross:.4f} USD")
    print(f"평균 실제 BNB비용:  {avg_bnb_val:.4f} USD")
    print(f"평균 실제 순수익:   {avg_real_net:.4f} USD (거래당)")

# 전체 현황
print("\n=== 전체 누적 현황 ===")
all_rows = []
for coin in coins:
    for f in sorted(glob.glob(log_dir + f'trades_v2_{coin}_*.csv')):
        try:
            with open(f) as fp:
                reader = csv.DictReader(fp)
                for row in reader:
                    invest = float(row.get('투입금액(USD)', 0) or 0)
                    if invest > 50:
                        all_rows.append(row)
        except:
            pass

total_csv_net = sum(float(r.get('순수익(USD)', 0) or 0) for r in all_rows)
total_invest = sum(float(r.get('투입금액(USD)', 0) or 0) for r in all_rows)
total_receive = sum(float(r.get('수취금액(USD)', 0) or 0) for r in all_rows)
total_gross = total_receive - total_invest

print(f"총 거래수: {len(all_rows)}")
print(f"총 CSV순수익 합계: +{total_csv_net:.2f} USD")
print(f"총 gross spread:   +{total_gross:.2f} USD")

# 실제 fee_rate가 0.075%라면:
real_fee_075 = total_invest * 0.00075 * 2  # 양 레그 합산
print(f"\n실제 수수료 추정 (0.075% × 2레그 = 0.15%):")
print(f"  수수료 총계: {real_fee_075:.2f} USD")
print(f"  실제 순수익: {total_gross - real_fee_075:.2f} USD")

# 설정 fee_rate 0.04% × 2
set_fee = total_invest * 0.0004 * 2
print(f"\n설정 수수료 (0.04% × 2레그):")
print(f"  수수료 총계: {set_fee:.2f} USD")
print(f"  예상 순수익: {total_gross - set_fee:.2f} USD (≈ CSV값)")

print(f"\n미계상 수수료 갭: {real_fee_075 - set_fee:.2f} USD (= 잔고 감소 추정치)")
