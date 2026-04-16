# Go-Running (고라니 달리기)

> A side-scrolling runner game built entirely with **Claude Code Harness** — an AI agent framework that autonomously plans, implements, and reviews code step by step.

![gameplay](KakaoTalk_20260416_123146915.gif)

---

## What is Claude Code Harness?

**Claude Code Harness** is an agentic workflow tool built on top of Claude Code (Anthropic's AI CLI). Instead of writing code manually, you define a `phase → step` plan and the Harness agent:

1. Reads the step spec (`phases/*/step*.md`)
2. Autonomously writes, edits, and verifies the code
3. Outputs structured results (`step*-output.json`)
4. Moves to the next step

This entire game was built by describing *what* to build, not *how* — the Harness agent handled all implementation details.

---

## Game Overview

| Item | Detail |
|---|---|
| Genre | Infinite side-scrolling runner |
| Engine | Phaser 3 (CDN, no build step) |
| Audio | Tone.js (retro chiptune BGM & SFX) |
| Language | Vanilla JavaScript (ES6 modules) |
| Platform | PC browser |

### Story

A *gorani* (Korean water deer), labeled a pest and facing euthanasia, wakes up from tranquilizer and runs toward its home forest **"Supri"**. The city is full of environmental hazards — dodge them and make it home.

### Features

- **Infinite scrolling** background (city → suburbs → forest)
- **HP system** (3 hearts) — obstacles reduce HP, items restore it
- **Day/Night cycle** (60s) — sparrows help during the day, rats help at night
- **Retro chiptune** BGM generated procedurally with Tone.js
- **Score system** — distance + collected acorns

---

## How It Was Built (Harness Workflow)

```
phases/
└── 0-mvp/
    ├── step0.md   → Project scaffold & Phaser setup
    ├── step1.md   → Game loop, player movement, scrolling background
    ├── step2.md   → Obstacles, items, HP system
    ├── step3.md   → Day/Night system, helper characters
    └── step4.md   → Audio system, game over scene, polish
```

Each `.md` file is a spec given to the Harness agent. The agent reads it, writes all the code, runs syntax checks, and outputs results — no manual coding involved.

---

## Run Locally

```bash
npm install
npx serve src -l 3000
# Open http://localhost:3000
```

Controls: **Space** or **tap** to jump.

---

## Project Structure

```
src/
├── index.html              # Entry point (CDN imports only)
└── game/
    ├── main.js             # Phaser app init
    ├── config.js           # Phaser config
    ├── scenes/
    │   ├── BootScene.js    # Asset generation
    │   ├── IntroScene.js   # Story intro with typing effect
    │   ├── GameScene.js    # Main game loop
    │   └── GameOverScene.js
    ├── objects/
    │   ├── Gorani.js       # Player character
    │   ├── Obstacle.js     # Environmental hazards
    │   └── Item.js         # Acorns & leaves
    └── systems/
        ├── AudioSystem.js  # Tone.js chiptune engine
        ├── DayNightSystem.js
        └── HelperSystem.js # Sparrow / rat helpers
docs/
├── PRD.md          # Product Requirements
├── ARCHITECTURE.md # Technical architecture decisions
└── ADR.md          # Architecture Decision Records
```

---

## AI Agent Usage

This project demonstrates **fully agentic game development**:

- **Zero manual code** — all source files written by Claude Code Harness
- **Spec-driven** — developer writes what to build, agent decides how
- **Self-verifying** — agent runs `node --check` after each step to catch syntax errors
- **Iterative** — each phase builds on the previous output

> Built with [Claude Code](https://claude.ai/code) + Harness agentic workflow
