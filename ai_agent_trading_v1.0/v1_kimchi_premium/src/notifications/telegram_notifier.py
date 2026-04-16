"""텔레그램 봇 알림 (multi_main 등). 실패 시 예외 없이 무시."""
from __future__ import annotations

import html
import json
import logging
import mimetypes
import os
import re
import time
from pathlib import Path
import urllib.parse
import urllib.request
import uuid

logger = logging.getLogger(__name__)

_TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"
_TELEGRAM_DOC_API = "https://api.telegram.org/bot{token}/sendDocument"


def send_telegram(
    message: str,
    token: str | None = None,
    chat_id: str | None = None,
    parse_mode: str | None = "HTML",
) -> bool:
    """텔레그램 메시지 전송. 실패해도 예외를 올리지 않음.

    parse_mode=None 이면 일반 텍스트(HTML 파싱 없음). 임계값·% 기호가 있는 시작 알림 등에 사용.
    """
    token = token or os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID", "")

    if not token or not chat_id:
        return False

    try:
        payload: dict[str, str] = {"chat_id": chat_id, "text": message}
        if parse_mode:
            payload["parse_mode"] = parse_mode
        data = urllib.parse.urlencode(payload).encode("utf-8")
        req = urllib.request.Request(_TELEGRAM_API.format(token=token), data=data, method="POST")
        with urllib.request.urlopen(req, timeout=5) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            return bool(result.get("ok"))
    except Exception as exc:
        logger.warning("텔레그램 전송 실패 (무시): %s", exc)
        return False


def send_telegram_document(
    file_path: str,
    caption: str = "",
    token: str | None = None,
    chat_id: str | None = None,
) -> bool:
    """텔레그램 문서 전송. 실패해도 예외를 올리지 않음."""
    token = token or os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        return False
    path = Path(file_path)
    if not path.exists() or not path.is_file():
        logger.warning("텔레그램 문서 전송 실패 (파일 없음): %s", file_path)
        return False

    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    boundary = f"----cursor-{uuid.uuid4().hex}"
    eol = b"\r\n"

    try:
        file_bytes = path.read_bytes()
        body = bytearray()

        def _add_field(name: str, value: str) -> None:
            body.extend(f"--{boundary}".encode("utf-8") + eol)
            body.extend(
                f'Content-Disposition: form-data; name="{name}"'.encode("utf-8") + eol + eol
            )
            body.extend(value.encode("utf-8") + eol)

        _add_field("chat_id", chat_id)
        if caption:
            _add_field("caption", caption)
            _add_field("parse_mode", "HTML")

        body.extend(f"--{boundary}".encode("utf-8") + eol)
        body.extend(
            (
                f'Content-Disposition: form-data; name="document"; filename="{path.name}"'
            ).encode("utf-8")
            + eol
        )
        body.extend(f"Content-Type: {mime}".encode("utf-8") + eol + eol)
        body.extend(file_bytes + eol)
        body.extend(f"--{boundary}--".encode("utf-8") + eol)

        req = urllib.request.Request(
            _TELEGRAM_DOC_API.format(token=token),
            data=bytes(body),
            method="POST",
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            return bool(result.get("ok"))
    except Exception as exc:
        logger.warning("텔레그램 문서 전송 실패 (무시): %s", exc)
        return False


class TelegramNotifier:
    """매매 이벤트별 포맷된 알림."""

    def __init__(self, token: str | None = None, chat_id: str | None = None) -> None:
        self.token = token or os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID", "")
        self.enabled = bool(self.token and self.chat_id)
        # Same error can repeat every loop; suppress duplicates for a short window.
        self.error_cooldown_sec = float(os.getenv("TELEGRAM_ERROR_COOLDOWN_SEC", "180"))
        self._last_error_sent_at: dict[str, float] = {}
        if not self.enabled:
            logger.info("텔레그램 알림 비활성화 (TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID 미설정)")

    def _send(self, message: str) -> None:
        if self.enabled:
            send_telegram(message, self.token, self.chat_id)

    def _send_document(self, file_path: str, caption: str) -> bool:
        if not self.enabled:
            return False
        return send_telegram_document(file_path, caption, self.token, self.chat_id)

    def on_start(
        self,
        mode: str,
        coins: list[str],
        fx: float,
        *,
        app_version: str = "v1.1",
    ) -> None:
        coins_s = html.escape(", ".join(coins))
        mode_s = html.escape(mode)
        ver_s = html.escape((app_version or "v1.1").strip() or "v1.1")
        self._send(
            f"🚀 <b>아비트리지 시스템 시작</b> <code>{ver_s}</code>\n"
            f"모드: {mode_s}\n"
            f"코인: {coins_s}\n"
            f"초기 FX: {fx:,.0f} KRW/USDT"
        )

    def on_fatal_startup(self, title: str, detail: str) -> None:
        """잔고 API·사전점검 등으로 프로세스가 못 뜰 때 (401 등)."""
        t = html.escape(title)
        d = html.escape(detail[:800] + ("…" if len(detail) > 800 else ""))
        self._send(f"⛔️ <b>{t}</b>\n<pre>{d}</pre>")

    def on_cloud_deploy_ready(
        self,
        *,
        mode: str,
        coins: list[str],
        fx: float,
        feeds_ok: bool,
        host_hint: str = "",
        app_version: str = "v1.1",
        yaml_seed_total_krw: float | None = None,
    ) -> None:
        """클라우드(EC2 등) 기동 후 WS·FX 정상일 때만 호출. `on_trade` 등과 동일 `_send` 경로."""
        if not feeds_ok:
            return
        coins_s = html.escape(", ".join(coins))
        mode_s = html.escape(mode)
        ver_s = html.escape((app_version or "v1.1").strip() or "v1.1")
        host_s = html.escape(host_hint.strip()) if host_hint.strip() else ""
        host_line = f"\n호스트: <code>{host_s}</code>" if host_s else ""
        seed_line = ""
        if yaml_seed_total_krw is not None and yaml_seed_total_krw > 0:
            seed_line = f"\n설정 시드(YAML 4슬롯 합·참고): {yaml_seed_total_krw:,.0f} KRW"
        self._send(
            f"☁️ <b>클라우드 정상 연동</b> <code>{ver_s}</code>\n"
            f"업비트/바이낸스 WebSocket 및 KRW-USDT FX 수신 확인, 메인 루프 진입.{host_line}\n"
            f"모드: {mode_s}\n"
            f"코인: {coins_s}\n"
            f"FX: {fx:,.0f} KRW/USDT"
            f"{seed_line}"
        )

    def on_first_loop_mode(
        self,
        *,
        mode: str,
        enable_live_orders: bool,
        live_dry_run: bool,
        config_path: str,
        app_version: str = "v1.1",
        yaml_seed_total_krw: float | None = None,
        initial_asset_plan_text: str = "",
    ) -> None:
        """첫 루프 진입 시 테스트/실전 상태를 1회 알림."""
        mode_s = html.escape(mode)
        cfg_s = html.escape(config_path)
        ver_s = html.escape((app_version or "v1.1").strip() or "v1.1")
        is_real_live = (mode.lower() == "live") and enable_live_orders and (not live_dry_run)
        if is_real_live:
            title = "🔴 <b>실전 모드 첫 루프 진입</b>"
        else:
            title = "🧪 <b>테스트 모드 첫 루프 진입</b>"
        seed_line = ""
        if yaml_seed_total_krw is not None and yaml_seed_total_krw > 0:
            seed_line = f"\n설정 시드(YAML 4슬롯 합·참고): {yaml_seed_total_krw:,.0f} KRW"
        plan_line = (
            f"\n초기자산 계획(확인용)\n{html.escape(initial_asset_plan_text)}"
            if initial_asset_plan_text
            else ""
        )
        self._send(
            f"{title} <code>{ver_s}</code>\n"
            f"mode={mode_s}, enable_live_orders={enable_live_orders}, live_dry_run={live_dry_run}\n"
            f"config={cfg_s}"
            f"{seed_line}"
            f"{plan_line}"
        )

    def on_ops_heartbeat(
        self,
        *,
        ts_kst: str,
        loop_count: int,
        equity: float,
        baseline: float | None,
        realized: float,
        fees: float,
        gross_ref: float,
        yaml_seed_total_krw: float | None = None,
    ) -> None:
        """운영용 구동확인 (v1 스타일: 간결/실현손익 중심)."""
        ts_s = html.escape(ts_kst)
        eq = f"{equity:,.0f}"
        lines = [
            f"💓 <b>구동확인</b> <code>{ts_s}</code>",
            f"루프 {loop_count:,}회 | 총평가 {eq} KRW",
        ]
        if yaml_seed_total_krw is not None and yaml_seed_total_krw > 0:
            lines.append(f"설정 시드(YAML 4슬롯 합·참고): {yaml_seed_total_krw:,.0f} KRW")
        if baseline is not None and baseline > 0:
            net_roi = realized / baseline * 100
            lines.append(f"실현 기준 순수익률 {net_roi:+.2f}%")
        else:
            lines.append("실현 기준 순수익률 계산 대기")
        lines.append(
            f"실현손익 {realized:+,.0f} | 수수료·슬리피지 합 {fees:,.0f} | 참고이익 {gross_ref:+,.0f} KRW"
        )
        self._send("\n".join(lines))

    def on_stop(self, loop_count: int, total_pnl_krw: float) -> None:
        emoji = "✅" if total_pnl_krw >= 0 else "🔴"
        self._send(
            f"{emoji} <b>시스템 종료</b>\n"
            f"총 루프: {loop_count:,}회\n"
            f"누적 실현손익: {total_pnl_krw:+,.0f} KRW"
        )

    def on_trade(
        self,
        action: str,
        symbol: str,
        premium: float,
        pnl_krw: float,
        fee_krw: float,
        trade_qty: float,
        upbit_price: float,
        binance_price: float,
        fx: float,
        mode: str = "paper",
        round_trip_pnl_krw: float | None = None,
        round_trip_premium: float | None = None,
        hold_duration_sec: float | None = None,
    ) -> None:
        sym = html.escape(symbol)
        mode_s = html.escape(mode)
        if action == "TRADE_KIMCHI":
            title = "📈 <b>김프 체결</b>"
            leg = "업빗 매도 / 바낸 매수"
        else:
            title = "📉 <b>역프 체결</b>"
            leg = "업빗 매수 / 바낸 매도"
        pnl_emoji = "💰" if pnl_krw >= 0 else "🔻"
        lines = [
            f"{title} [{mode_s.upper()}] <b>{sym}</b>",
            f"방향: {leg}",
            f"프리미엄 {premium:.4%} | 수량 {trade_qty:.6f}",
            f"업빗 {upbit_price:,.2f} KRW | 바낸 {binance_price:.5f} USDT (={binance_price * fx:,.2f} KRW)",
            f"{pnl_emoji} 실현손익 {pnl_krw:+,.0f} KRW | 수수료 {fee_krw:,.0f} KRW",
        ]
        if round_trip_pnl_krw is not None:
            rt_emoji = "✅" if round_trip_pnl_krw >= 0 else "🔴"
            hold_str = ""
            if hold_duration_sec is not None:
                if hold_duration_sec < 60:
                    hold_str = f" | 보유 {hold_duration_sec:.0f}초"
                elif hold_duration_sec < 3600:
                    hold_str = f" | 보유 {hold_duration_sec / 60:.1f}분"
                else:
                    hold_str = f" | 보유 {hold_duration_sec / 3600:.1f}시간"
            prem_str = (
                f" | 왕복프리미엄 {round_trip_premium:.3%}"
                if round_trip_premium is not None
                else ""
            )
            lines.append(f"{rt_emoji} <b>왕복완성</b> {round_trip_pnl_krw:+,.0f} KRW{prem_str}{hold_str}")
        self._send("\n".join(lines))

    def on_rebalance_signal(self, symbol: str, direction: str, premium: float, note: str = "") -> None:
        sym = html.escape(symbol)
        dir_s = html.escape(direction)
        note_s = f"\n{html.escape(note)}" if note else ""
        self._send(
            f"🔄 <b>리밸런싱 시그널</b> [{sym}]\n"
            f"방향: {dir_s}\n"
            f"현재 프리미엄: {premium:.4%}\n"
            f"(온체인 이체 수동 필요){note_s}"
        )

    def on_error(self, symbol: str, error: str) -> None:
        key = self._error_key(symbol, error)
        if not self._should_send_error(key):
            return
        sym = html.escape(symbol)
        err = html.escape(error)
        self._send(
            f"🚨 <b>라이브 에러 발생!</b>\n"
            f"코인: {sym}\n"
            f"에러: {err}\n"
            f"⚠️ 해지 불완전 가능성 — 즉시 확인 요망"
        )

    def _error_key(self, symbol: str, error: str) -> str:
        # Normalize numbers/query noise so equivalent order errors share one key.
        norm = error.lower()
        norm = re.sub(r"\d+(?:\.\d+)?", "#", norm)
        norm = re.sub(r"\s+", " ", norm).strip()
        return f"{symbol.upper()}::{norm[:200]}"

    def _should_send_error(self, key: str) -> bool:
        now = time.monotonic()
        last = self._last_error_sent_at.get(key)
        if last is not None and (now - last) < self.error_cooldown_sec:
            return False
        self._last_error_sent_at[key] = now
        return True

    def on_hedge_incomplete(self, symbol: str, error: str, recovered: bool) -> None:
        key = self._error_key(symbol, f"hedge_incomplete:{'recovered' if recovered else 'failed'}:{error}")
        if not self._should_send_error(key):
            return
        sym = html.escape(symbol)
        err = html.escape(error)
        if recovered:
            title = "⚠️ <b>해지 불완전 (복구 시도 성공)</b>"
            tail = "업비트 역주문 복구는 성공했지만 체결 오차를 점검하세요."
        else:
            title = "🚨 <b>해지 불완전 (복구 실패)</b>"
            tail = "즉시 수동 점검 필요. 시스템 정지 예정/정지 상태입니다."
        self._send(
            f"{title}\n"
            f"코인: {sym}\n"
            f"원인: {err}\n"
            f"{tail}"
        )

    def on_live_halt(self, symbol: str, reason: str) -> None:
        sym = html.escape(symbol)
        rs = html.escape(reason)
        self._send(
            f"🛑 <b>긴급 정지(HALT)</b>\n"
            f"코인: {sym}\n"
            f"사유: {rs}\n"
            f"실주문 루프를 중단했습니다. 계정 잔고/미체결을 즉시 확인하세요."
        )

    def on_portfolio_imbalance(
        self,
        symbol: str,
        *,
        upbit_krw: float,
        upbit_coin: float,
        binance_usdt: float,
        binance_coin: float,
        elapsed_hours: float,
    ) -> None:
        sym = html.escape(symbol)
        self._send(
            f"⚠️ <b>포트폴리오 쏠림 지속</b> [{sym}]\n"
            f"지속시간: {elapsed_hours:.1f}시간\n"
            f"업비트 KRW: {upbit_krw:,.0f}\n"
            f"업비트 코인: {upbit_coin:.6f}\n"
            f"바이낸스 USDT: {binance_usdt:,.4f}\n"
            f"바이낸스 코인: {binance_coin:.6f}"
        )

    def on_hourly_summary(
        self,
        hour_bucket: str,
        loops: int,
        kimchi_cnt: int,
        reverse_cnt: int,
        rebalance_cnt: int,
        pnl_krw: float,
        fee_krw: float,
        fx: float,
        equity: float,
        *,
        health_status: str = "",
        health_detail: str = "",
        yaml_seed_total_krw: float | None = None,
        upbit_total_krw: float | None = None,
        binance_total_krw: float | None = None,
        baseline_upbit_total_krw: float | None = None,
        baseline_binance_total_krw: float | None = None,
        position_state: str = "",
    ) -> None:
        hb = html.escape(hour_bucket)
        hs = html.escape(health_status) if health_status else ""
        hd = html.escape(health_detail) if health_detail else ""
        head = f"📊 <b>시간당 요약</b> [{hb} KST]\n"
        if hs:
            head += f"<b>구동 상태</b>: {hs}\n"
            if hd:
                head += f"{hd}\n"
            head += "\n"
        seed_line = ""
        if yaml_seed_total_krw is not None and yaml_seed_total_krw > 0:
            seed_line = f"\n설정 시드(YAML 4슬롯 합·참고): {yaml_seed_total_krw:,.0f} KRW"
        exch_line = ""
        if upbit_total_krw is not None and binance_total_krw is not None:
            up_delta = None
            bn_delta = None
            up_roi = None
            bn_roi = None
            if baseline_upbit_total_krw is not None and baseline_upbit_total_krw > 0:
                up_delta = float(upbit_total_krw) - float(baseline_upbit_total_krw)
                up_roi = up_delta / float(baseline_upbit_total_krw) * 100.0
            if baseline_binance_total_krw is not None and baseline_binance_total_krw > 0:
                bn_delta = float(binance_total_krw) - float(baseline_binance_total_krw)
                bn_roi = bn_delta / float(baseline_binance_total_krw) * 100.0
            up_pnl = f"{up_delta:+,.0f}" if up_delta is not None else "n/a"
            bn_pnl = f"{bn_delta:+,.0f}" if bn_delta is not None else "n/a"
            up_r = f"{up_roi:+.2f}%" if up_roi is not None else "n/a"
            bn_r = f"{bn_roi:+.2f}%" if bn_roi is not None else "n/a"
            exch_line = (
                f"\n업비트: {upbit_total_krw:,.0f} KRW (손익 {up_pnl}, {up_r})"
                f"\n바이낸스: {binance_total_krw:,.0f} KRW (손익 {bn_pnl}, {bn_r})"
            )
        pos_line = f"\n포지션 상태: {html.escape(position_state)}" if position_state else ""
        self._send(
            f"{head}"
            f"구간 루프: {loops:,}회 | FX: {fx:,.0f}\n"
            f"김프: {kimchi_cnt}건 | 역프: {reverse_cnt}건 | 리밸런스: {rebalance_cnt}건\n"
            f"구간 실현손익: {pnl_krw:+,.0f} KRW\n"
            f"구간 수수료합: {fee_krw:,.0f} KRW\n"
            f"총평가(현재): {equity:,.0f} KRW"
            f"{exch_line}"
            f"{pos_line}"
            f"{seed_line}"
        )

    def on_daily_asset_snapshot(
        self,
        *,
        date_kst: str,
        upbit_total_krw: float,
        binance_total_krw: float,
        combined_total_krw: float,
        upbit_cash_krw: float,
        upbit_coin_krw: float,
        binance_usdt_krw: float,
        binance_coin_krw: float,
        fx: float,
        yaml_seed_total_krw: float | None = None,
    ) -> None:
        d = html.escape(date_kst)
        seed_line = ""
        if yaml_seed_total_krw is not None and yaml_seed_total_krw > 0:
            seed_line = f"\n설정 시드(YAML 4슬롯 합·참고): {yaml_seed_total_krw:,.0f} KRW"
        self._send(
            "🗓️ <b>일일 자산 스냅샷 (00시 KST)</b>\n"
            f"기준일: {d}\n"
            f"업비트 총자산: {upbit_total_krw:,.0f} KRW "
            f"(현금 {upbit_cash_krw:,.0f} + 코인평가 {upbit_coin_krw:,.0f})\n"
            f"바이낸스 총자산: {binance_total_krw:,.0f} KRW "
            f"(USDT평가 {binance_usdt_krw:,.0f} + 코인평가 {binance_coin_krw:,.0f})\n"
            f"합계: <b>{combined_total_krw:,.0f} KRW</b>\n"
            f"환율: {fx:,.0f} KRW/USDT"
            f"{seed_line}"
        )

    def on_trade_export_csv(self, file_path: str, rows: int, interval_sec: float) -> bool:
        """누적 거래 CSV(엑셀로 열 수 있는 동일 파일) 전송."""
        hours = interval_sec / 3600.0
        caption = (
            "📎 <b>누적 거래기록 CSV</b>\n"
            f"주기: {hours:.1f}시간\n"
            f"누적 거래 행수(헤더 제외): {rows:,}\n"
            "파일: multi_trades.csv (Excel 열기 가능)"
        )
        return self._send_document(file_path, caption)

    def on_trade_export_empty(self) -> None:
        self._send(
            "📎 <b>누적 거래기록 CSV</b>\n"
            "현재 누적 거래가 없어 파일 전송을 건너뜀 (행수 0)."
        )
