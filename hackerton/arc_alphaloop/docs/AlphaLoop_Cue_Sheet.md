# 🎬 AlphaLoop Cue Sheet — Loom 녹화 가이드 (v3 — 실측 기준)

**MP3**: `대본_reading_v2.mp3` (4:20)
**Lablab 한계**: ≤ 5분 — 4:20 = **40초 여유** ✅

## 🎯 측정된 핵심 시점 (사용자 실측)

```
0:28  Per-signal value (Problem 시작)
0:54  Arc makes USDC (Why Arc 시작)
1:20  no hidden operator (Seg 1 끝)
1:23  This is the AlphaLoop dashboard (Seg 2 시작)
3:19  the bridge demotes (Seg 2 끝)
3:23  This is not a chatbot (Seg 3 시작)
4:20  음성 끝
```

이걸 기준으로 내부 cue 들 비례 계산.

---

## 🔄 두 가지 녹화 방식 (선택)

### 방식 A: **연속 녹화** — 영상 1개 (간단)
MP3 ▶ → 끝까지 → Loom 정지. MP3 안 자동 호흡 (3-4초)을 그대로 흘려보냄.

### 방식 B: **3-segment 일시정지 녹화** — 영상 3개 (안전, 첫 녹화 추천)
각 segment 끝에서 MP3+Loom 정지 → 호흡 → 다음 segment.

---

## 사전 셋업

```
□ Loom 마이크 OFF (No Microphone)
□ 헤드폰 착용
□ 대시보드 탭 = signal-mesh.vercel.app (헤더 위치)
□ PDF 풀스크린 (F11) → p.1 (Cover)
□ arcscan 탭 = testnet.arcscan.app (빈 페이지)
□ 미디어 플레이어 = 대본_reading_v2.mp3 (일시정지, 0:00)
```

## 시작 시퀀스

```
1. Loom Start recording (Ctrl+Shift+L)
2. 1초 침묵
3. 미디어 플레이어 ▶ 재생
4. 아래 cue sheet 따라감
```

---

## 📋 정밀 큐 시트 (실측 4:20 기준)

### 🎬 SEGMENT 1 (0:00 - 1:20) — 도입부 80초

| 시간 | 들리는 멘트 (트리거) | 액션 |
|------|---------------------|------|
| **0:00** | (재생 시작) | 화면: **PDF p.1 Cover** 표시 |
| ~0:02 | "**USDC is the gas.**" | 화면 그대로 (p.1) |
| ~0:04 | "**On Arc.**" | `Page Down` → **p.2 The Hook** |
| ~0:06 | "**I run a live arb bot on EC2**" | `Alt+Tab` → **대시보드** (헤더 보임) |
| ~0:11 | "**And those signals flow**" | 마우스 → ProductionAnchor "**648 trades**" 호버 |
| ~0:16 | "**On every other chain**" | 화면 그대로 |
| ~0:20 | "**On Arc, USDC IS the gas.**" | 화면 그대로 |
| ~0:23 | "**Signal in, payment out**" | 화면 그대로 |
| ~0:26 | "**The agent closes its own books.**" | (1초 호흡) |
| **0:28** | "**Per-signal value**" | `Alt+Tab` → **PDF** → `Page Down` → **p.3 The Problem** |
| ~0:35 | "**On Base, Polygon, or Solana**" | 화면 그대로 |
| ~0:42 | "**And worse, agents earn in USDC**" | 화면 그대로 |
| ~0:48 | "**The agent has no way to self-balance.**" | 화면 그대로 |
| ~0:51 | "**Behind every agent-economy demo**" | 화면 그대로 |
| **0:54** | "**Arc makes USDC the native gas**" | `Page Down` → **p.4 Why Arc** |
| ~0:57 | "**One unit of account**" | 화면 그대로 |
| ~1:01 | "**That removes a whole layer**" | 화면 그대로 |
| ~1:09 | "**An agent stack that runs forever**" | 화면 그대로 |
| ~1:15 | "**That is the closed loop.**" | 화면 그대로 |
| ~1:17 | "**No paymaster, no subsidy, no hidden operator.**" | (1초 호흡) |
| **1:20** | (Seg 1 끝 — 호흡 마커 시작) | 화면 그대로 |

```
═══════════════════════════════════════════════════════════
🛑 SEGMENT 1 끝 — 1:20 시점
   방식 A: MP3 자동 호흡 3초 → 1:23 부터 자동 재개
   방식 B: ⏸️ MP3 일시정지 + Loom 정지 → 호흡 → 다음 segment
═══════════════════════════════════════════════════════════
```

---

### 🔴 SEGMENT 2 (1:23 - 3:19) — 본진 데모 + RL 116초

> 방식 A: 자동 재개  
> 방식 B: Loom 새 녹화 시작 → 1초 침묵 → MP3 1:23 부터 재생

| 시간 | 들리는 멘트 (트리거) | 액션 |
|------|---------------------|------|
| **1:23** | "**This is the AlphaLoop dashboard**" | `Alt+Tab` → **대시보드** (헤더 보임) |
| ~1:26 | "**signal mesh dot vercel dot app**" | URL 바 보이게 |
| ~1:30 | "**Bridge plus three strategy producers**" | 마우스 → **StrategyMixChip** (mix v1·v2·v3) |
| ~1:36 | "**backed by my v1.3 production arb bot**" | 화면 그대로 |
| ~1:40 | "**The mix chip shows v1, v2, v3 signals**" | 마우스 → mix chip 호버 |
| ~1:44 | "**I'm firing one hundred fifty**" | `Alt+Tab` → **터미널 T3** (리허설=흉내, 본 녹화=Enter) |
| ~1:48 | "**Real Arc testnet, real x402**" | 화면 그대로 (터미널) |
| ~1:53 | "**Each amount sampled from signal quality**" | 화면 그대로 |
| ~2:01 | "**Watch the tx counter climb**" | `Alt+Tab` → **대시보드** → ↓ 스크롤 → **Settlement TX 카드** |
| ~2:04 | "**real hashes on arcscan**" | 마우스 → 카드 안 hash 호버 |
| ~2:08 | "**That's what variable price x402 settler means**" | 마우스 → hash 목록 |
| ~2:12 | "**Low signal at one twentieth of a cent**" | 마우스 → 작은 금액 |
| ~2:15 | "**high confidence at the one cent cap**" | 마우스 → 큰 금액 |
| ~2:18 | "**Block confirmed**" | TX hash 1개 클릭 (또는 `Ctrl+Tab` → arcscan 탭) |
| ~2:23 | "**Meanwhile, the Gemini powered**" | `Ctrl+Shift+Tab` → **대시보드** → ↑ 스크롤 → **Strategy Cards 3장** |
| ~2:28 | "**V1 kimchi premium, Korean to Global**" | 마우스 → v1 카드 (amber) |
| ~2:31 | "**V2 dual quote spread**" | 마우스 → v2 카드 (cyan) |
| ~2:34 | "**V3 funding rate basis on perp**" | 마우스 → v3 카드 (purple) |
| ~2:37 | "**Real prices from a live production bot**" | (잠시 정지) |
| ~2:41 | "**Round one, this learner lost**" | ↑ 스크롤 → **RegimeMap 카드** |
| ~2:50 | "**Round two — it ties the empirical optimum**" | `Alt+Tab` → PDF → 페이지 8 입력 → **p.8 The Receipt** |
| ~2:57 | "**P equals zero point four nine**" | 화면 그대로 (p.8) |
| ~3:00 | "**The convergence IS the rigor signal**" | 화면 그대로 |
| ~3:03 | "**Nine regime states, seven actions**" | `Alt+Tab` → **대시보드** → **Policy Heatmap** 위치 |
| ~3:08 | "**ninety percent of history was cold funding**" | 화면 그대로 (Heatmap 보임) |
| ~3:12 | "**Persona switching is live**" | ↓ 스크롤 → **Fee Persona Explorer** → **Bybit 탭 클릭** |
| ~3:14 | "**note the retail tag**" | 마우스 → retail 녹색 태그 |
| ~3:17 | "**The bridge demotes incompatible venues**" | (잠시 정지) |
| **3:19** | (Seg 2 끝 — 호흡 마커 시작) | 화면 그대로 |

```
═══════════════════════════════════════════════════════════
🛑 SEGMENT 2 끝 — 3:19 시점
   방식 A: MP3 자동 호흡 4초 → 3:23 부터 자동 재개
   방식 B: ⏸️ MP3 일시정지 + Loom 정지 → 호흡 → 다음 segment
═══════════════════════════════════════════════════════════
```

---

### 🎬 SEGMENT 3 (3:23 - 4:20) — Originality + CTA 57초

> 방식 A: 자동 재개  
> 방식 B: Loom 새 녹화 시작 → 1초 침묵 → MP3 3:23 부터 재생

| 시간 | 들리는 멘트 (트리거) | 액션 |
|------|---------------------|------|
| **3:23** | "**This is not a chatbot wrapping a wallet**" | ↑ 스크롤 → **AgentIdentityCard** (5행 테이블) |
| ~3:27 | "**Each of our five agents**" | 마우스 → 5행 테이블 ROLE 컬럼 위→아래 |
| ~3:33 | "**Our AlphaLoopAgentRegistry on Arc testnet**" | 마우스 → 컨트랙트 주소 영역 |
| ~3:38 | "**emitted five AgentRegistered events**" | 마우스 → CARD 컬럼 (sha256 hash) |
| ~3:43 | "**Off chain document, on chain anchor**" | (1초 호흡) |
| ~3:46 | "**Variable price encodes signal quality**" | `Alt+Tab` → **PDF** → `Page Down` → **p.11 Originality** |
| ~3:49 | "**Outcome feedback re prices future signals**" | 화면 그대로 (p.11) |
| ~3:52 | "**A learned meta policy decides**" | 화면 그대로 |
| ~3:56 | "**A real market — verifiable end to end**" | (잠시 정지) |
| ~4:00 | "**One hundred fifty variably priced transactions**" | `Page Down` → **p.12 Close** |
| ~4:05 | "**One unit of account**" | 화면 그대로 (p.12) |
| ~4:07 | "**Zero humans in the gas tank**" | 화면 그대로 |
| ~4:10 | "**Open signal mesh dot vercel dot app**" | URL 강조 (Slide 자체에 큰 글씨) |
| ~4:14 | "**fire the demo, watch the allocator pick**" | 화면 그대로 |
| ~4:18 | "**AlphaLoop — on Arc.**" | (1초 호흡) |
| **4:20** | (음성 끝) | **Loom 정지** (`Ctrl+Shift+L`) |

```
═══════════════════════════════════════════════════════════
🛑 SEGMENT 3 끝 — 모든 녹화 완료!
   → CapCut import → 영상 + MP3 + 자막 합치기
═══════════════════════════════════════════════════════════
```

---

## 📌 핵심 — 음성이 트리거, 시간은 보조

```
✅ "들리는 멘트" 가 트리거 (정확)
🟡 "시간" 은 위치 추적용 (보조, ±2초 차이 OK)
```

---

## 🎯 첫 시도 팁

1. **시뮬 1번 먼저** — Loom 안 켜고 위 sheet 따라 화면만 조작
2. **시간 메모 정확화** — 시뮬 중 본인 들리는 정확한 초 수정 필요하면 메모
3. **그 메모 보면서 본 녹화**

---

## 🚦 Lablab 길이 한계

```
✅ 공식 한계: ≤ 5분 (300초)
✅ 현재 영상: 4:20 (260초)
✅ 여유: 40초

→ 5분 안에 충분히 들어감.
→ Loom 녹화 시 1-2초 추가 침묵 들어도 ~4:25
→ 통과 OK
```

---

## 📎 파일 위치

```
MP3:        C:\Users\user\hackerton\arc\대본_reading_v2.mp3 (4:20)
Cue Sheet:  C:\Users\user\hackerton\arc\docs\AlphaLoop_Cue_Sheet.md (이 문서)
SRT 자막:    C:\Users\user\hackerton\arc\docs\AlphaLoop_Video1.srt
PDF:        C:\Users\user\hackerton\arc\AlphaLoop Deck_v3.pdf
```
