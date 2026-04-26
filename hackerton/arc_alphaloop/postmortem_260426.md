# AlphaLoop — Post-Submission Postmortem (260426)

> Self-assessment after submitting to lablab.ai · Agentic Economy on Arc.
> Written before results announcement, based on a full scout of all 227 competing submissions.
> Goal: extract honest lessons for the next hackathon, not to pump or trash the project.

---

## 1. Competitive landscape (actual data)

Pulled directly from the lablab submission page on 2026-04-26 evening KST.

| Metric | Count |
|--------|-------|
| **Total submissions** | **227** |
| Agent-to-Agent (Track 2 — our track) | 25 |
| Projects using ERC-8004 | 11 |
| Projects in trading domain | 19 |
| **Intersection: ERC-8004 + trading** | **1 (= AlphaLoop only)** |

For context: the previous Arc hackathon (Agentic Commerce on Arc, Jan 2026) had 100+ submissions. This round more than doubled it.

---

## 2. Most threatening competitors (Top 5)

| Rank | Project | Why it's strong | Where they edge us |
|------|---------|-----------------|--------------------|
| 1 | **SwarmPay** | 6 agents + ERC-721 NFT identity + on-chain Reputation Registry (`giveFeedback()`) + EIP-712 `setAgentWallet` | Deepest ERC-8004 implementation in the field |
| 2 | **QuantMesh** | HFT trading-signal marketplace, x402-native, "$0.002 signal = -74,900% margin on Ethereum" framing, submitted Apr 21 (4 days head start) | Same domain as us + sharper margin narrative |
| 3 | **AgentMesh** | Real-time waterfall UI with truncated hashes + USDC + settlement latency; team of 2 ML engineers | Strongest visual UX in the field |
| 4 | **ARCEON** | 5 agents with "survival instinct" trading energy/compute/data/storage; from a trading-systems team (MAITS) | Similar agent count + trading background |
| 5 | **ArcAgent** | Buyer/Seller Gemini negotiation + "Nanopayment Storm" demo; selected **4 tracks** | Multi-track exposure |

Honorable threat: **Agent Payment Loop with Arc-Based USDC Simulation** — same naming theme but explicitly "simulation," not real on-chain. We beat them on actual settlements.

---

## 3. Weaknesses (8, in descending severity)

| # | Weakness | Severity | Who does it better |
|---|----------|----------|--------------------|
| 1 | **Selected only 1 track** (multi-select was available) | 🔴🔴🔴 | ArcAgent (4), QuantMesh (3), SwarmPay/AgentMesh (2) |
| 2 | **Shallow ERC-8004 use** — 5 registers, no reputation/auction layer | 🔴🔴🔴 | SwarmPay (NFT + Reputation + EIP-712) |
| 3 | **"Closed loop" business model is murky** — no obvious external buyer | 🔴🔴🔴 | QuantMesh (B2B), SwarmPay (two-sided), AgentMesh (B2C) |
| 4 | **Margin framing too soft** ("sub-cent pricing" doesn't shock) | 🔴🔴 | QuantMesh ("-74,900% margin" sticks in your head) |
| 5 | **Static dashboard** — no "wow moment" UX beat in the demo video | 🔴🔴 | AgentMesh (live waterfall feed) |
| 6 | **Single LLM** (Gemini 2.5 Flash only) | 🔴 | SwarmPay/AgentMesh route across 3–4 models |
| 7 | **Verification gap** — "backed by live v1.3 bot" can't be verified by a judge in 30 seconds | 🔴🔴 | Teams whose differentiator is just "look at the code" |
| 8 | **Trading domain = niche** — judges may prefer general agent infra (API marketplace, SDK) | 🔴🔴 | QuantMesh sidesteps this by being a marketplace |

### What survives — moats that nobody else has

- ✅ **ERC-8004 + trading intersection** (only us in the entire 227)
- ✅ **Live v1.3 production arb bot backing** (zero other teams have a real production system feeding the agents)
- ✅ **Variable per-action pricing tied to signal quality** (most teams use fixed prices)
- ✅ **Q-learning meta-allocator with empirical optimum** (genuine ML depth)
- ✅ **150 real on-chain tx + Merkle root** (verifiable, beyond minimum)
- ✅ **Circle Product Feedback (5 sections, ~750 words)** — separate $500 prize lane

---

## 4. Realistic outcome probabilities (after the scout)

| Outcome | Probability |
|---------|-------------|
| Track 2 — 1st place | 3–7 % |
| Track 2 — 2nd place | 8–12 % |
| Track 2 — 3rd place | 10–18 % |
| Honorable Mention | 20–30 % |
| **Circle Product Feedback ($500)** | **30–45 %** ⭐ |
| Nothing | 30–40 % |

The safest bet is the Product Feedback prize — nobody else seems to be filling all 5 sections in depth.

---

## 5. Lessons captured (for the next hackathon)

These are now baked into `~/.claude/skills/conv-hackathon/SKILL.md` so the next session triggers them automatically. The full reasoning lives in `해커톤_제출플레이북_종합_260426.md` §8.10–8.14.

### A. Multi-select tracks aggressively

If your project meets the definition of a track at ≥50 %, **select it**. Worst case, the judges remove it. Best case, you're a candidate in 3–4 lanes instead of 1.

For AlphaLoop, every one of these qualified and was missed:
- *Per-API Monetization Engine* — we have x402 APIs charging per request (90 % fit)
- *Real-Time Micro-Commerce Flow* — 150 micro-events with sub-second settlement (90 % fit)
- *Usage-Based Compute Billing* — LLM inference billed per signal (70 % fit)

### B. Shock-number margin framing

Soft (us): "Sub-cent pricing $0.0005–$0.010"
Hard (QuantMesh): "$0.002 signal × $1.50 Ethereum gas = -74,900 % margin"

Template: `On Ethereum, $X gas per $Y action = -Z % margin (impossible). On Arc, $0.0001 gas = +99.X % margin (viable).`

Use the same framing in description, video, and deck — repetition cements it in the judge's memory.

### C. One "wow moment" UX beat in the video

A static dashboard reads as a screenshot. A live waterfall of hashes / a real-time agent-to-agent transfer animation / a ticker of variable prices reads as motion. You need at least one 10-second window where the screen is alive.

### D. Name an external buyer, even for closed-loop projects

Even if the system runs end-to-end internally, add a one-paragraph "Future commercialization" section: who pays, how much, why. Otherwise the judge fills in the worst answer for you.

### E. Standards: depth over breadth (for solo / small teams)

5 shallow ERC-8004 registrations < 1 deep one (NFT identity + Reputation Registry + EIP-712 wallet binding). Pick one standard, exhaust its sub-components, combine it with one or two cryptographic primitives (EIP-712, ERC-4337, ERC-721).

### F. Multi-LLM orchestration is now table stakes

A 2026 agent-economy demo using a single LLM looks dated. Even a thin routing layer across Claude / Gemini / Groq / OpenAI raises the perceived sophistication.

### G. Make your differentiator verifiable in 30 seconds

If a judge can't confirm your strongest claim by clicking one link or watching one frame, the claim is doing 30 % of the work it could. "150 on-chain tx" is verifiable on arcscan. "Backed by a live production bot" is not. Either show the bot's live dashboard / PnL chart, or stop leading with that claim.

### H. Phase 0: open the submission form before you build the video

Always click through the lablab/devpost form once before video production. Field types (file upload vs. URL vs. both), description char limit, tag selectors, multi-track checkboxes, bonus fields — knowing these up-front saves hours of redo work and avoids the multi-track miss above.

---

## 6. Honest summary

What we got right:
- Real on-chain settlements, not simulations
- A genuinely unique intersection (ERC-8004 + trading)
- A real production system feeding the demo (rare in hackathons)
- Submission discipline (PDF deck, two videos, captions, evidence file)

What we got wrong:
- Treated tracks as single-select (free points left on the table)
- Pitched the closed-loop story without naming a buyer
- Underplayed the margin numbers
- Skipped a "wow" UX beat in favor of a clean but static dashboard
- Used a single LLM in an environment where multi-LLM is the norm

5 days, solo, from Korea, with a live arb bot backing it — meaningful differentiation in a 227-team field. Most of the weaknesses above are not about ability; they're about hackathon-craft choices, and they're now codified in the conventions for next time.

🏆 Whatever happens at the 2026-04-27 ceremony, the artifacts (videos, contracts, dashboard, deck) and the lessons here are the durable outputs.
