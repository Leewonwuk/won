# v1.2 라이브 (EC2) 운영 메모

`src.v12.live_v2` + `configs/v12/v12_btc_v2.yaml`. 전체 논의는 로컬 `.cursor/skills/arb-v12-binance-dual-quote/SKILL.md` 참고.

1. **바이낸스만** — 업비트 키/리밸런스 가이드(v1.1)와 전제가 다름.
2. **내부 인벤토리 복구** — 듀얼쿼트 백테스트 라인에서는 `max_daily_rebalances: 0`이면 첫 거래 후 거의 재진입 불가(진단: 2026-04-05). `live_v2`는 엔진이 스테이블/레그 복구 로직을 별도로 둠; 동작 이상 시 로그·잔고 확인.
3. **`entry_split_fraction`** — 올인(1.0) 금지 권장; 기본 0.25.
4. **프리미엄 편향** — 구조상 USDT 쪽(DT) 시그널이 대부분; 역방향은 드묾.
5. **systemd** — `ARB_SERVICE_LINE=v1.2`, `ARB_V12_LIVE=true` 일 때 실주문. 재배포 후 `*.sh` CRLF 깨지면:  
   `find ~/arb -name '*.sh' -exec sed -i 's/\r$//' {} + && sudo systemctl restart arb`
