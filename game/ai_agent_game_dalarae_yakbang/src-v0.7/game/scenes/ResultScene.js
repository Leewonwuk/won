import { GAME_WIDTH, GAME_HEIGHT, HUD_TOP_H, HUD_BOT_H } from '../config.js';
import { audioSystem } from '../systems/AudioSystem.js';

// v0.6 스텁 — Phase 1-E 에서 주간/월간 결산 팝업으로 채워 넣음.
// 현재는 scene.start('ResultScene', { summary }) 가 호출돼도 크래시하지 않도록
// 기본 구조 + '다음 주로' 버튼만 제공한다.
export class ResultScene extends Phaser.Scene {
  constructor() { super({ key: 'ResultScene' }); }

  init(data) {
    const d = data || {};
    this.summary = d.summary || { kind: 'week', week: 1, gold: 0, income: 0, myeongui: 0 };
  }

  create() {
    // 배경 오버레이
    const overlay = this.add.graphics();
    overlay.fillStyle(0x000000, 0.55);
    overlay.fillRect(0, 0, GAME_WIDTH, GAME_HEIGHT);

    // 패널 (크림색).
    // Phase 4-A: 만족도 라인 1줄 추가로 높이 +36.
    // 2차 M1 보정: 마지막 row 와 버튼 descender 겹침 여유 확보 (+12).
    // 2차 FM-N1 보정: pending>0 일 때 "보류 N명" 라인 조건부 추가 → 가변 높이.
    // Phase 4-B ⑨B + ⑧C: rejected>0 (row +38) / nextTier 존재 (하단 라벨 +22) 가변.
    // Phase 4-B 보정-2: ph 를 HUD 제외 가용 높이로 clamp + py 는 최소 HUD_TOP_H+8 보장.
    //   scale FIT 모드에서 뷰포트 축소 시 패널이 버튼까지 잘리는 시나리오 방어(상한 가드).
    // Phase 4-B 보정-3: "다음 계층" 라벨 폰트 12px 로 줄여 ph 증분 30→22.
    const hasPending = (this.summary.pending || 0) > 0;
    const hasRejected = (this.summary.rejected || 0) > 0;
    const hasNextTier = !!this.summary.nextTier;
    const hasUpkeep = (this.summary.upkeep || 0) > 0;
    const hasHalfYear = !!this.summary.halfYear;
    // Phase 7-A2: 방별 수입 breakdown — incomeByBuilding 에 0보다 큰 값이 있을 때만 표시.
    const incomeByBuilding = this.summary.incomeByBuilding || {};
    const breakdownEntries = Object.entries(incomeByBuilding)
      .filter(([, v]) => v > 0)
      .sort((a, b) => b[1] - a[1]);
    const hasBreakdown = breakdownEntries.length > 0;
    const BREAKDOWN_H = 56;  // title(14) + bar(14) + gap(4) + legend(14) + 여유(10).
    let ph = 328;
    if (hasUpkeep) ph += 38;
    if (hasPending) ph += 38;
    if (hasRejected) ph += 38;
    if (hasBreakdown) ph += BREAKDOWN_H;
    if (hasNextTier) ph += 22;
    if (hasHalfYear) ph += 180;
    const phMax = GAME_HEIGHT - HUD_TOP_H - HUD_BOT_H - 16;
    if (ph > phMax) ph = phMax;
    const pw = 480;
    const px = (GAME_WIDTH - pw) / 2;
    const py = Math.max(HUD_TOP_H + 8, (GAME_HEIGHT - ph) / 2);
    const panel = this.add.graphics();
    panel.fillStyle(0xfdf0d0, 1);
    panel.fillRoundedRect(px, py, pw, ph, 12);
    panel.fillStyle(0xd08020, 1);
    panel.fillRoundedRect(px, py, pw, 44, 12);
    panel.fillRect(px, py + 32, pw, 12);
    panel.lineStyle(3, 0xd08020);
    panel.strokeRoundedRect(px, py, pw, ph, 12);

    // 제목
    const title = this.summary.kind === 'month'
      ? `第 ${this.summary.month || 1} 月 결산`
      : `第 ${this.summary.week || 1} 週 결산`;
    this.add.text(GAME_WIDTH / 2, py + 22, title, {
      fontFamily: 'Noto Serif KR, serif',
      fontSize: '28px', fontStyle: 'bold',
      color: '#ffffff', stroke: '#8b4010', strokeThickness: 4
    }).setOrigin(0.5);

    // 항목 — 이번 주 net 수입이 음수면 적자(빨강), 0 이상이면 흑자(주황)
    const inc = this.summary.income || 0;
    const incText  = inc >= 0 ? `+${inc} 전` : `${inc} 전`;
    const incColor = inc >= 0 ? '#c06000' : '#c02020';
    const wage = this.summary.wage || 0;
    const upkeep = this.summary.upkeep || 0;
    // Phase 4-A ③A: 월간 만족도 라인. totalJudged===0 가드로 NaN% 방지(S10).
    const tj = this.summary.totalJudged || 0;
    const sat = this.summary.satisfied || 0;
    const neu = this.summary.neutral || 0;
    const dis = this.summary.dissatisfied || 0;
    const pending = this.summary.pending || 0;
    const satText = tj === 0
      ? '— (집계 중)'
      : `${sat} / ${tj}  (만족 ${sat} · 보통 ${neu} · 불만 ${dis})`;
    const satColor = tj === 0 ? '#806040' : (sat * 2 >= tj ? '#4ac06a' : '#c06060');
    const rows = [
      ['수입',     incText,                                 incColor],
      ['급료',     wage > 0 ? `-${wage} 전` : '-',          wage > 0 ? '#c02020' : '#806040']
    ];
    if (hasUpkeep) {
      rows.push(['유지비', `-${upkeep} 전`, '#c02020']);
    }
    rows.push(
      ['보유',     `${this.summary.gold || 0} 전`,          '#604010'],
      ['명의',     `${(this.summary.myeongui || 0).toFixed(1)}`, '#208030'],
      ['만족도',   satText,                                 satColor]
    );
    // 2차 FM-N1 보정: 선비·양반 보류는 Phase 6 해금 전 기능이라 유저에게 명시.
    if (pending > 0) {
      rows.push(['보류', `${pending} 명 — 상위 계층은 추후 해금`, '#8090b0']);
    }
    // Phase 4-B ⑨B: 거절 환자 — 계층별 breakdown 문자열로 압축. 0 이면 라인 자체 생략.
    //   직원 고용 압력의 크기를 "어느 계층이 돌려보내졌는지"로 구체화 — nobi·양반 분리 인식.
    const rejected = this.summary.rejected || 0;
    if (rejected > 0) {
      const byTier = this.summary.rejectedByTier || {};
      const labels = { nobi: '노비', nongmin: '농민', sangin: '상인', seonbi: '선비', yangban: '양반' };
      const order = ['yangban', 'seonbi', 'sangin', 'nongmin', 'nobi'];
      const parts = [];
      for (const t of order) {
        const n = byTier[t] || 0;
        if (n > 0) parts.push(`${labels[t] || t} ${n}`);
      }
      const breakdown = parts.length > 0 ? ` (${parts.join(' · ')})` : '';
      rows.push(['거절', `${rejected} 명${breakdown}`, '#c08040']);
    }
    rows.forEach(([k, v, c], i) => {
      const ry = py + 100 + i * 38;
      this.add.text(px + 60, ry, k, {
        fontFamily: 'Noto Serif KR, serif', fontSize: '17px', color: '#604010'
      }).setOrigin(0, 0.5);
      this.add.text(px + pw - 60, ry, v, {
        fontFamily: 'Noto Serif KR, serif', fontSize: '20px', color: c, fontStyle: 'bold'
      }).setOrigin(1, 0.5);
    });

    const rowsBottomY = py + 100 + rows.length * 38 + 4;

    // Phase 7-A2: 방별 수입 — 가로 스택바 + 범례. "어느 방이 벌었나" 즉시 보이게.
    //   색상: 건물 키 표준 팔레트 (Patient.js ILLNESS_COLOR 와 일치 — 도트 색과 매칭).
    if (hasBreakdown) {
      const COLORS = {
        moxa: 0xd06020, acu: 0x3080d0, herb: 0x50a030,
        haewoso: 0x808080, gukbap: 0xc87040, well: 0x3ca0e0
      };
      const LABELS = {
        moxa: '뜸방', acu: '침방', herb: '약방',
        haewoso: '해우소', gukbap: '국밥집', well: '우물'
      };
      const totalBreak = breakdownEntries.reduce((s, [, v]) => s + v, 0);
      const titleY = rowsBottomY;
      this.add.text(px + 30, titleY, '방별 수입', {
        fontFamily: 'Noto Serif KR, serif', fontSize: '13px', color: '#604010', fontStyle: 'bold'
      }).setOrigin(0, 0);
      const barX = px + 30, barY = titleY + 16, barW = pw - 60, barH = 14;
      const bg = this.add.graphics();
      bg.fillStyle(0xfae6b8, 1);
      bg.fillRoundedRect(barX, barY, barW, barH, 4);
      const seg = this.add.graphics();
      let cursor = barX;
      for (let i = 0; i < breakdownEntries.length; i++) {
        const [key, val] = breakdownEntries[i];
        const isLast = i === breakdownEntries.length - 1;
        // 마지막 세그먼트는 cursor → barX+barW 끝까지 (반올림 누적 오차 흡수).
        const w = isLast ? (barX + barW - cursor) : Math.max(2, Math.round((val / totalBreak) * barW));
        seg.fillStyle(COLORS[key] || 0xa08060, 1);
        seg.fillRect(cursor, barY, w, barH);
        cursor += w;
      }
      const border = this.add.graphics();
      border.lineStyle(1, 0xc89048);
      border.strokeRoundedRect(barX, barY, barW, barH, 4);
      // 범례: 도트 + 라벨 N전. 한 줄 — 항목 ≤6개라 barW(420) 안에 들어감.
      const legendY = barY + barH + 4;
      let lx = barX;
      for (const [key, val] of breakdownEntries) {
        const dot = this.add.graphics();
        dot.fillStyle(COLORS[key] || 0xa08060, 1);
        dot.fillRect(lx, legendY + 4, 8, 8);
        const txt = this.add.text(lx + 12, legendY, `${LABELS[key] || key} ${val}전`, {
          fontFamily: 'Noto Serif KR, serif', fontSize: '11px', color: '#604010'
        });
        lx += 12 + Math.ceil(txt.width) + 10;
      }
    }

    const sectionY = rowsBottomY + (hasBreakdown ? BREAKDOWN_H : 0);

    // Phase 4-B ⑧C: 다음 계층 해금 진행률 — K1 장기 목표 축. rows 아래 가로폭 전체 라벨.
    //   현재 명의 / 임계값 으로 "앞으로 얼마나 걸릴지" 가시화.
    if (hasNextTier) {
      const nt = this.summary.nextTier;
      const labels = { nongmin: '농민', sangin: '상인', seonbi: '선비', yangban: '양반' };
      const label = labels[nt.tier] || nt.tier;
      const cur = (this.summary.myeongui || 0).toFixed(1);
      const need = nt.threshold;
      this.add.text(GAME_WIDTH / 2, sectionY, `→ 다음 계층: ${label}  (명의 ${cur} / ${need})`, {
        fontFamily: 'Noto Serif KR, serif', fontSize: '12px',
        color: '#a08060'
      }).setOrigin(0.5, 0.5);
    }

    // Phase 6: 6개월 결산 — 막대 그래프 + 순이익 꺾은선.
    //   x축 6달, 좌측 수입(초록)/우측 급료+유지비(빨강) 쌍 막대, 위에 월 순이익 라벨.
    if (hasHalfYear) {
      const hy = this.summary.halfYear;
      const baseY = hasNextTier ? sectionY + 22 : sectionY;
      const hyY = baseY + 6;
      const hyH = 168;
      const hyW = pw - 60;
      const hyX = px + 30;
      this.add.graphics()
        .fillStyle(0xfae6b8, 1)
        .fillRoundedRect(hyX, hyY, hyW, hyH, 6)
        .lineStyle(2, 0xc89048)
        .strokeRoundedRect(hyX, hyY, hyW, hyH, 6);
      this.add.text(hyX + 10, hyY + 8, '◆ 6개월 결산', {
        fontFamily: 'Noto Serif KR, serif', fontSize: '14px', color: '#7a4010', fontStyle: 'bold'
      });
      const netColor = hy.net >= 0 ? '#208030' : '#c02020';
      this.add.text(hyX + hyW - 10, hyY + 8,
        `순이익 ${hy.net >= 0 ? '+' : ''}${hy.net} 전`, {
          fontFamily: 'Noto Serif KR, serif', fontSize: '13px',
          color: netColor, fontStyle: 'bold'
        }).setOrigin(1, 0);

      // 차트 영역.
      const chartX = hyX + 28, chartY = hyY + 32;
      const chartW = hyW - 48, chartH = 100;
      const hist = (Array.isArray(hy.history) ? hy.history : []).filter(Boolean);
      const maxV = Math.max(
        1,
        ...hist.map((m) => Math.max(m.income || 0, (m.wage || 0) + (m.upkeep || 0)))
      );
      const cg = this.add.graphics();
      // 베이스라인.
      cg.lineStyle(1, 0xb08050, 0.7);
      cg.lineBetween(chartX, chartY + chartH, chartX + chartW, chartY + chartH);

      const slotW = hist.length > 0 ? chartW / hist.length : 0;
      const barW = Math.max(4, Math.min(18, slotW * 0.35));
      const netPoints = [];
      // K2: 호버 툴팁 단일 인스턴스 — 모든 슬롯이 공유. shutdown cleanup 위해 멤버화.
      const tooltipBg = this.add.graphics().setDepth(60).setVisible(false);
      const tooltipTxt = this.add.text(0, 0, '', {
        fontFamily: 'Noto Serif KR, serif', fontSize: '11px', color: '#fdf0d0',
        align: 'left', padding: { x: 6, y: 4 }
      }).setDepth(61).setOrigin(0, 1).setVisible(false);
      // K2-Gap3: 슬롯 호버 어포던스 — 단일 그래픽 재사용으로 alpha 하이라이트.
      const slotHl = this.add.graphics().setDepth(58).setVisible(false);
      this._tooltipBg = tooltipBg;
      this._tooltipTxt = tooltipTxt;
      this._slotHl = slotHl;
      this._slotZones = [];
      // K2-Gap3: 피크/저점 월 사전 산출 — 같은 값 동률 시 가장 빠른 달 선택.
      let peakIdx = -1, troughIdx = -1;
      let peakNet = -Infinity, troughNet = Infinity;
      for (let i = 0; i < hist.length; i++) {
        const m = hist[i];
        const n = (m.income || 0) - ((m.wage || 0) + (m.upkeep || 0));
        if (n > peakNet) { peakNet = n; peakIdx = i; }
        if (n < troughNet) { troughNet = n; troughIdx = i; }
      }
      // 동일 인덱스 (히스토리 1개월) 면 ★ 1개만.
      const samePeakTrough = peakIdx === troughIdx;
      for (let i = 0; i < hist.length; i++) {
        const m = hist[i];
        const cx = chartX + slotW * (i + 0.5);
        const incV = m.income || 0;
        const incH = Math.round((incV / maxV) * chartH);
        const outV = (m.wage || 0) + (m.upkeep || 0);
        const outH = Math.round((outV / maxV) * chartH);
        // 수입 막대 (녹색, 왼쪽).
        cg.fillStyle(0x3aa85a, 1);
        cg.fillRect(cx - barW - 1, chartY + chartH - incH, barW, incH);
        // 지출 막대 (적색, 오른쪽).
        cg.fillStyle(0xc85040, 1);
        cg.fillRect(cx + 1, chartY + chartH - outH, barW, outH);
        // x축 라벨.
        this.add.text(cx, chartY + chartH + 4, `${m.month || i + 1}월`, {
          fontFamily: 'Noto Serif KR, serif', fontSize: '10px', color: '#604010'
        }).setOrigin(0.5, 0);
        // 순이익 점.
        const net = incV - outV;
        const ny = chartY + chartH - Math.round((net / maxV) * chartH);
        const nyClamped = Math.max(chartY - 2, Math.min(chartY + chartH + 2, ny));
        netPoints.push({ x: cx, y: nyClamped });
        // K2: 막대 위 항상 표시되는 순이익 라벨. 피크/저점은 ★ 뱃지.
        // #17: netLabelY 양방 클램프 — 헤더(chartY 위)·x축 라벨(chartY+chartH 아래) 모두와 분리.
        const isPeak = !samePeakTrough && i === peakIdx;
        const isTrough = !samePeakTrough && i === troughIdx;
        const star = isPeak ? '★ ' : (isTrough ? '☆ ' : '');
        const netLabel = `${star}${net >= 0 ? '+' : ''}${net}`;
        const netLabelY = Math.max(chartY + 2, Math.min(chartY + chartH - 12, nyClamped - 12));
        this.add.text(cx, netLabelY, netLabel, {
          fontFamily: 'Noto Serif KR, serif', fontSize: '10px',
          color: net >= 0 ? '#208030' : '#c02020', fontStyle: 'bold'
        }).setOrigin(0.5, 0);
        // K2: 슬롯 호버 영역 — 상세 툴팁 + 어포던스 하이라이트.
        const slotMonth = m.month || i + 1;
        const slotLeft = cx - slotW / 2;
        const zone = this.add.zone(cx, chartY + chartH / 2, slotW, chartH)
          .setOrigin(0.5).setInteractive();
        this._slotZones.push(zone);
        zone.on('pointerover', () => {
          // 슬롯 배경 알파 하이라이트 (어포던스).
          slotHl.clear();
          slotHl.fillStyle(0xd08020, 0.10);
          slotHl.fillRect(slotLeft, chartY, slotW, chartH);
          slotHl.setVisible(true);
          const lines = [
            `${slotMonth}월${isPeak ? '  ★ 최대 흑자' : (isTrough ? '  ☆ 최대 적자' : '')}`,
            `수입 +${incV}`,
            `지출 -${outV}`,
            `순이익 ${net >= 0 ? '+' : ''}${net}`
          ].join('\n');
          tooltipTxt.setText(lines);
          const tw = tooltipTxt.width;
          const th = tooltipTxt.height;
          // 패널 안쪽으로 클램프.
          const tx = Math.max(hyX + 4, Math.min(hyX + hyW - tw - 4, cx - tw / 2));
          const ty = Math.max(hyY + 22 + th, nyClamped - 6);
          tooltipTxt.setPosition(tx, ty);
          tooltipBg.clear();
          tooltipBg.fillStyle(0x402010, 0.92);
          tooltipBg.fillRoundedRect(tx, ty - th, tw, th, 4);
          tooltipBg.lineStyle(1, 0xd08020, 1);
          tooltipBg.strokeRoundedRect(tx, ty - th, tw, th, 4);
          tooltipBg.setVisible(true);
          tooltipTxt.setVisible(true);
        });
        zone.on('pointerout', () => {
          slotHl.setVisible(false);
          tooltipBg.setVisible(false);
          tooltipTxt.setVisible(false);
        });
      }
      // 순이익 꺾은선.
      if (netPoints.length >= 2) {
        cg.lineStyle(2, 0x6040c0, 1);
        for (let i = 1; i < netPoints.length; i++) {
          cg.lineBetween(netPoints[i - 1].x, netPoints[i - 1].y, netPoints[i].x, netPoints[i].y);
        }
      }
      cg.fillStyle(0x6040c0, 1);
      for (const p of netPoints) cg.fillCircle(p.x, p.y, 3);

      // 범례 (하단 한 줄).
      const legY = hyY + hyH - 18;
      const lg = this.add.graphics();
      lg.fillStyle(0x3aa85a, 1); lg.fillRect(hyX + 12, legY + 3, 10, 8);
      this.add.text(hyX + 26, legY, '수입', {
        fontFamily: 'Noto Serif KR, serif', fontSize: '11px', color: '#604010'
      });
      lg.fillStyle(0xc85040, 1); lg.fillRect(hyX + 70, legY + 3, 10, 8);
      this.add.text(hyX + 84, legY, '급료+유지비', {
        fontFamily: 'Noto Serif KR, serif', fontSize: '11px', color: '#604010'
      });
      lg.fillStyle(0x6040c0, 1); lg.fillCircle(hyX + 170, legY + 7, 4);
      this.add.text(hyX + 178, legY, '순이익', {
        fontFamily: 'Noto Serif KR, serif', fontSize: '11px', color: '#604010'
      });
      this.add.text(hyX + hyW - 10, legY,
        `누계 수입 ${hy.income} / 급료 ${hy.wage} / 유지비 ${hy.upkeep}`, {
          fontFamily: 'Noto Serif KR, serif', fontSize: '10px', color: '#604010'
        }).setOrigin(1, 0);
    }

    // 계속 버튼
    const btnY = py + ph - 52;
    const btnW = 200, btnH = 40;
    const btnX = GAME_WIDTH / 2 - btnW / 2;
    const btnBg = this.add.graphics();
    btnBg.fillStyle(0xd08010, 1);
    btnBg.fillRoundedRect(btnX, btnY, btnW, btnH, 8);
    btnBg.lineStyle(2, 0x804000, 1);
    btnBg.strokeRoundedRect(btnX, btnY, btnW, btnH, 8);
    this.add.text(GAME_WIDTH / 2, btnY + btnH / 2, '계속 →', {
      fontFamily: 'Noto Serif KR, serif', fontSize: '18px', color: '#ffffff', fontStyle: 'bold',
      stroke: '#804000', strokeThickness: 3
    }).setOrigin(0.5);

    const hit = this.add.zone(GAME_WIDTH / 2, btnY + btnH / 2, btnW, btnH)
      .setOrigin(0.5).setInteractive({ useHandCursor: true });
    hit.on('pointerdown', () => this._resume());

    // BGM — switchTheme 가 Promise 를 반환하지 않을 수도 있어 safe wrap
    if (audioSystem && typeof audioSystem.switchTheme === 'function') {
      Promise.resolve(audioSystem.switchTheme('result')).catch(() => {});
    }

    // CRIT-01: 씬 종료 시 tooltip / zone 리스너 정리. visible=true 잔상 방지.
    this.events.once(Phaser.Scenes.Events.SHUTDOWN, this._cleanup, this);
  }

  _cleanup() {
    if (this._tooltipBg)  { this._tooltipBg.setVisible(false); }
    if (this._tooltipTxt) { this._tooltipTxt.setVisible(false); }
    if (this._slotHl)     { this._slotHl.setVisible(false); }
    if (this._slotZones) {
      for (const z of this._slotZones) {
        if (z && z.removeAllListeners) z.removeAllListeners();
      }
      this._slotZones = null;
    }
    this._tooltipBg = null;
    this._tooltipTxt = null;
    this._slotHl = null;
  }

  _resume() {
    // Phase 1-E 결정: GameScene 은 launch 호출 직후 pause 됨.
    // 계속 버튼 → GameScene resume (RESUME 이벤트 → BGM 복귀) → ResultScene stop.
    // audio 전환은 GameScene._onResumed 에서 처리하므로 여기선 호출하지 않음(중복 방지).
    this.scene.resume('GameScene');
    this.scene.stop();
  }
}
