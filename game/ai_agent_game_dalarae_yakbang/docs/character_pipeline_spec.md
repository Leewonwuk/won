# 달아래약방 — 캐릭터 일러스트 생성 규약 (2026-04-20)

> 이 문서는 새 캐릭터를 추가하거나 기존 캐릭터를 수정할 때 반드시 따를 **표준 절차(SOP)**.
> `scripts/palette_transfer.py` 의 자동 재조립 + 팔레트 전이 + NEAREST 축소 파이프라인을 전제로 함.
> 이전 문서 `ai_regen_spec.md` / `ai_prompt_musuri.md` 는 "원본 그리드 결함 → AI 재생성 필요" 를 전제했으나,
> 2026-04-20 connected-component 자동 재조립이 통합되면서 **재생성 불필요**. 본 문서가 유효 규약.

---

## 1. 파이프라인 개요

```
[원본 PNG]  →  [recompose_via_components]  →  [per-cell flood-fill 배경 제거]
                       ↓                                ↓
              [12개 캐릭터 자동 검출 +              [가장 큰 연결 성분 유지]
                동일 cell 재배치]                         ↓
                                              [팔레트 12색 추출 (MAXCOVERAGE)]
                                                          ↓
                                              [팔레트 전이 (int32 L2 거리)]
                                                          ↓
                                              [NEAREST 축소 → 64×64 프레임]
                                                          ↓
                                              [시트 조립 → palette_out/<name>.png]
                                                          ↓
                                              [src-v0.6/assets/chars/ 에 복사]
```

- **실행**: `python scripts/palette_transfer.py`                (전체 10종 일괄)
- **개별**: `python scripts/palette_transfer.py --names 무수리`  (특정 캐릭터만)
- **의녀 같은 단일 친필**: `python scripts/palette_transfer.py --single 의녀`

---

## 2. 원본 일러스트 요구사항

### 2-A. AI 생성 (무수리·노비·상인 등 — `생성그림_꼉/캐릭터도트버전/`)

| 항목 | 요구치 | 비고 |
|---|---|---|
| **해상도** | 1024×1024 이상 권장 (3:4 비율) | 파이프라인이 cell 240×400 로 재조립 → 최종 64×64 로 NEAREST 축소 |
| **레이아웃** | 3열 × 4행 = 12 프레임 | Row 0=정면, 1=좌측, 2=우측, 3=후면 / Col 0=left-step, 1=idle, 2=right-step |
| **프레임 정렬** | **느슨해도 OK** | ⚠️ 과거엔 "cell 경계 정확 정렬" 이 필수였으나, 현재는 connected-component 로 자동 검출/재배치함 |
| **캐릭터 분리** | **⚠️ 각 캐릭터는 서로 겹치지 않는 독립 연결 성분이어야 함** | 두 캐릭터 팔이나 치마가 서로 닿으면 1개 덩어리로 검출됨 → **검출 ≠ 12 → 재조립 실패 → fallback 고정 분할** |
| **배경** | 체커보드·단색 회색·흰색 (RGB≥200 & 채도≤35) | flood-fill 로 자동 제거. 마젠타·체커보드 둘 다 허용 |
| **배경 침범** | 격자선·글씨·워터마크 금지 | 배경 후보 밖의 색이면 캐릭터로 오인됨 |
| **스타일** | 하드 엣지 픽셀 아트 | AA·그라디언트·블러는 quantize 가 처리하지만 원본이 깨끗할수록 결과 선명 |

### 2-B. 친필 원본 (의녀·침구·의관 — `생성그림_꼉/캐릭터원본/`)

| 항목 | 요구치 | 비고 |
|---|---|---|
| **해상도** | 64×64 단일 프레임 (현재 의녀) OR 192×256 시트 (확장 시) | 단일 프레임은 `--single` 모드로 12프레임 정지 복제 |
| **배경** | 완전 투명 (alpha=0) | 친필은 PSD/PNG 로 투명 유지 가능 |
| **팔레트** | **의녀 12색 글로벌 시드** 우선 사용 | `#000000 #eedde4 #d64766 #1132b0 #9d0a0a #47413b #b09fa6 #f6ad6b #f785b7 #051a69 #d28844 #f9cba1` |
| **아웃라인** | 1px 검정 `#000000` | Pedro [P3] |
| **걷기 확장** | 4방향 × 3프레임 (총 12개) | Pedro [P4] 발 기준선 ±1px 일정 |

---

## 3. 워크플로 — 신규 캐릭터 추가

```bash
# 1) 원본 PNG 을 해당 폴더에 투입
#    AI 생성: 생성그림_꼉/캐릭터도트버전/<한글명>.png
#    친필:    생성그림_꼉/캐릭터원본/<한글명>.png

# 2) palette_transfer.py 의 mapping 에 영문 키 추가
#    (AI): mapping = { ..., '새캐릭터명': 'newchar_m', }
#    (친필): single_mapping = { ..., '새캐릭터명': 'newchar', }

# 3) 파이프라인 실행
python scripts/palette_transfer.py --names 새캐릭터명

# 4) 결과 확인
#    palette_out/newchar_m.png               — 최종 64×64 시트
#    palette_out/_compare/newchar_m_ba.png   — before/after 비교 (3배 확대)

# 5) 게임 투입
cp scripts/palette_out/newchar_m.png src-v0.6/assets/chars/
#    BootScene.js 의 CHAR_SHEETS 배열에 'char_newchar_m' 추가
#    Patient.js / StaffSystem.js 에 role-to-sheet 매핑 추가
```

---

## 4. 워크플로 — 기존 캐릭터 수정

```bash
# 1) 원본 PNG 을 새 버전으로 덮어쓰기 (기존 파일명 유지)
#    예: 생성그림_꼉/캐릭터도트버전/무수리.png <- 새_무수리.png

# 2) 백업 권장
cp 생성그림_꼉/캐릭터도트버전/무수리.png 생성그림_꼉/캐릭터도트버전/무수리_old.png

# 3) 파이프라인 재실행 (단일 캐릭터)
python scripts/palette_transfer.py --names 무수리

# 4) 결과 비교 & 투입
#    palette_out/_compare/staff_ba.png 로 before/after 확인
cp scripts/palette_out/staff.png src-v0.6/assets/chars/

# 5) 브라우저에서 Ctrl+F5 강력 새로고침 (캐시 무효화)
```

---

## 5. 검증 — Pedro [P1]~[P5] 체크리스트

파이프라인 출력이 자동으로 통과해야 할 기준:

- **[P1] 실루엣 가독성**: 계층·성별·직업 식별 가능 → 원본 디자인 책임
- **[P2] 12색 팔레트**: 파이프라인이 MAXCOVERAGE 로 자동 12색 quantize → **자동 PASS**
- **[P3] 1px 아웃라인**: 원본이 갖고 있다면 NEAREST 축소로 보존 → **원본 책임**
- **[P4] 발 정렬 ±1px**: `render_frame()` 의 `py = fh - pad - nh` (bottom-align) 로 자동 **PASS**
- **[P5] 셀 경계 여백**: `recompose_via_components()` 가 BOTTOM_PAD=30 여백 강제 → **자동 PASS**

> 수동 검증 불필요. 단 **실루엣·아웃라인 두 항목만 원본 품질에 의존** — 원본이 엉성하면 quantize 도 한계.

---

## 6. 트러블슈팅

### 증상: `[recompose] 12 components not found`

**원인**: AI 생성 원본에서 캐릭터들이 서로 닿아 연결됨 (팔·치마·머리가 인접 프레임과 붙음).

**대응**:
1. 원본 이미지를 이미지 편집기에서 열어 캐릭터 사이 **1px 이상 간격** 확보 (투명 or 배경색으로 칠해 끊기)
2. 재실행 `python scripts/palette_transfer.py --names <name>`
3. 그래도 실패하면 `--no-recompose` 로 고정 격자 분할 fallback (구버전 동작, 품질 저하 감수)

### 증상: 출력의 발이 잘림

**원인 확인 순서**:
1. `palette_out/_compare/<name>_ba.png` 에서 before/after 비교
2. `palette_transfer.py` 로그에서 `scale=X.XXX` 값 확인 — 0.1 이하로 작으면 어떤 cell 에 비정상 큰 bbox 있음
3. `keep_largest_component` 가 주 캐릭터 아닌 장식/소품을 살렸는지 체크
4. 필요 시 원본에서 장식 제거 or `recompose_via_components(bottom_pad=...)` 값 조정

### 증상: 색이 이상하게 매핑됨 (예: 파랑이 빨강으로)

**원인**: palette 색 수가 너무 적어 원본 다양 색이 잘못 수렴.

**대응**: `--colors 16` 으로 늘려 재실행.

---

## 7. 금지 사항 (회귀 방지)

- ❌ `resize_chars.py` 직접 실행 — **deprecated**. LANCZOS 축소로 AA 중간색 생성 → 도트 엣지 파괴. `palette_transfer.py` 만 사용.
- ❌ `src-v0.6/assets/chars/` 에 원본 PNG 직접 복사 — 반드시 파이프라인 경유.
- ❌ 프레임 크기 48×48 회귀 — 현재 64×64 고정 (Phase 7-A 결정). 변경 시 `BootScene.js` `CHAR_FRAME_W/H` + 본 문서 동시 개정.
- ❌ AI 에게 "cell 경계 여백 20px 필수" 강조 — **과거 스펙**. 현재는 불필요. 대신 "캐릭터끼리 겹치지 말 것" 만 명시.

---

## 8. 참고 파일

| 파일 | 역할 |
|---|---|
| `scripts/palette_transfer.py` | 메인 파이프라인 (재조립+팔레트+NEAREST) |
| `scripts/recompose_musuri.py` | 재조립 단독 테스트 스크립트 (디버그용) |
| `scripts/resize_chars.py` | **deprecated** (LANCZOS 버전) |
| `docs/GIANTS_SHOULDERS.md` | Pedro Medeiros [P1]~[P5] 체크리스트 정의 |
| `docs/pedro_review_uinyeo_musuri.md` | 초기 검수 (무수리 FAIL 판정은 파이프라인 오진이었음 — 2026-04-20 개선으로 해결) |
| `src-v0.6/game/scenes/BootScene.js` | Phaser 측 캐릭터 로딩 (`CHAR_SHEETS`, `CHAR_FRAME_W/H`, `_createCharAnims`) |
