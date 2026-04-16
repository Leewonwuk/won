# 이 레포 알고리즘 구분 — 반드시 먼저 읽을 것

## ⚠️ v1.1과 v1.2는 완전히 다른 알고리즘이다

| 버전 | 전략 | 거래소 | 상태 |
|---|---|---|---|
| **v1.1 이하** | Upbit KRW ↔ Binance USDT 재정거래 | Upbit + Binance | **레거시 (사용 안 함)** |
| **v1.2 이상** | Binance 내 COINUSDT ↔ COINUSDC 스프레드 | **Binance 단일** | **봇 중지 (fee_rate 버그)** |
| **v2.0** | 현물 매수 + 선물 공매도 펀딩비 차익 | **Binance 단일** | **코드 완성, 상승장 대기** |

> **v1.2부터 업비트(Upbit)는 전혀 관계없다.**
> v1.1 코드(`src/main.py`, `src/backtest_main.py`, `configs/multi.yaml`)와
> v1.1 스킬(`arb-coin-trading-v1`, `upbit-binance-arb-ops`)을 v1.2 작업에 절대 참조하지 말 것.

---

## ★ 세션 시작 시 반드시 먼저 읽을 것

1. `.cursor/skills/` 안의 `arb-v*` 디렉토리를 확인하고, **버전 번호가 가장 높은** `SKILL.md`를 읽는다.
2. 해당 파일의 **"★ 현재 운영 상태"** 섹션을 파악한 뒤 요청을 처리한다.
3. 이유: 최신 스킬에 서버 IP·잔고·임계값·주의사항이 모두 집약되어 있어, 읽지 않으면 구버전 정보로 잘못 응답하게 된다.

> 규칙 전문: `.cursor/rules/latest-skill-first.mdc`

---

## Where the real playbooks live

- **라이브 운영 (현재)**: `.cursor/skills/arb-v128/SKILL.md` ← 항상 최신 버전 확인
- **Token & agent efficiency** (Claude Code / Cursor): `.cursor/skills/claude-code-token-efficiency/SKILL.md`
- v1.1 레거시 (참조 금지): `arb-coin-trading-v1`, `upbit-binance-arb-ops`, `arb-v2-backtest-validation`

---

## Context-saving habits (one-liners)

- **Always-apply rule**: `.cursor/rules/qmd-explore-first.mdc` — qmd MCP가 켜져 있으면 **코드 위치 찾기는 qmd `query` 먼저**, 그다음 필요한 파일만 Read; 전역 glob 금지(예외는 규칙 파일 참고).
- Setup: **qmd** in `.cursor/mcp.json` (Cursor: `npm install` + `scripts/qmd-mcp-launch.cjs`; see reference) and optionally `%USERPROFILE%\.claude\settings.json` → `mcpServers.qmd` (Claude Code CLI); one-time `scripts/qmd-index.ps1`. Details: `.cursor/skills/claude-code-token-efficiency/reference/qmd-cursor-mcp.md`.
- Large features: **Architect → Builder → Reviewer** (see claude-code-token-efficiency skill); Builder stays inside the written brief.
- Do not read paths ignored by **`.claudeignore`** unless the user explicitly asks for that path.

## Safety

- No real orders without documented live flags; secrets only in `.env` (never commit). See `README.md` and `.env.example`.
