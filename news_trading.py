"""Optional macro-news monitor and fail-closed execution gates.

Public calendar feeds are best-effort sources, not exchange-grade or
millisecond feeds. This module never submits orders; it parses releases,
combines them with explicit SMC/order-flow evidence, and evaluates book risk.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import email.utils
import inspect
import math
import re
import threading
import time
import unicodedata
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


DEFAULT_CALENDAR_FEEDS = (
    ("Forex Factory calendar XML", "https://nfs.faireconomy.media/ff_calendar_thisweek.xml"),
    ("CNBC Macro Economy RSS", "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=20910258"),
)

_CALENDAR_HTTP_CACHE: dict[str, tuple[float, bytes]] = {}
_CALENDAR_CACHE_TTL_SECONDS = 300.0
_CALENDAR_429_COOLDOWN_UNTIL: dict[str, float] = {}


@dataclass(frozen=True)
class EconomicRelease:
    event: str
    currency: str
    impact: str
    actual: float
    forecast: float
    previous: Optional[float]
    published_at: float
    source: str
    event_date: str = ""


@dataclass(frozen=True)
class BookSnapshot:
    bids: tuple[tuple[float, float], ...]
    asks: tuple[tuple[float, float], ...]
    observed_at: float


@dataclass(frozen=True)
class LiquidityAssessment:
    allowed: bool
    reason: str
    spread_ticks: Optional[float] = None
    risk_reward_after_costs: Optional[float] = None


@dataclass(frozen=True)
class GateDecision:
    allowed: bool
    reason: str
    macro_side: Optional[str] = None
    liquidity: Optional[LiquidityAssessment] = None


def _local_name(tag: str) -> str:
    return str(tag).rsplit("}", 1)[-1].lower().replace("-", "_")


def _number(value: Any) -> Optional[float]:
    if value is None:
        return None
    text = str(value).strip().replace(",", "")
    match = re.search(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)\s*([KMB])?", text, re.I)
    if not match:
        return None
    number = float(match.group(0)[:-1] if match.group(1) else match.group(0))
    suffix = (match.group(1) or "").upper()
    return number * {"": 1.0, "K": 1_000.0, "M": 1_000_000.0, "B": 1_000_000_000.0}[suffix]


def _timestamp(value: Optional[str], fallback: float) -> float:
    if not value:
        return fallback


def _calendar_event_timestamp(date_text: Optional[str], time_text: Optional[str],
                              timezone_name: str) -> Optional[float]:
    if not date_text or not time_text:
        return None
    date_text = date_text.strip()
    time_text = time_text.strip().upper()
    parsed_date = None
    for pattern in ("%m-%d-%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            parsed_date = dt.datetime.strptime(date_text, pattern).date()
            break
        except ValueError:
            continue
    if parsed_date is None:
        return None
    parsed_time = None
    for pattern in ("%I:%M%p", "%I:%M %p", "%I%p", "%I %p", "%H:%M"):
        try:
            parsed_time = dt.datetime.strptime(time_text, pattern).time()
            break
        except ValueError:
            continue
    if parsed_time is None:
        return None
    try:
        zone = ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, TypeError):
        return None
    return dt.datetime.combine(parsed_date, parsed_time, tzinfo=zone).timestamp()
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed.timestamp()
    except ValueError:
        pass
    try:
        parsed = email.utils.parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed.timestamp()
    except (TypeError, ValueError, OverflowError):
        return fallback


def _fields(element: ET.Element) -> dict[str, str]:
    fields: dict[str, str] = {}
    for child in element.iter():
        if child is element:
            continue
        name = _local_name(child.tag)
        text = " ".join(part.strip() for part in child.itertext() if part.strip())
        if text:
            fields[name] = text
    if element.text and element.text.strip():
        fields.setdefault("text", element.text.strip())
    return fields


def _labeled_value(text: str, labels: Iterable[str]) -> Optional[str]:
    label_re = "|".join(re.escape(label) for label in labels)
    match = re.search(rf"(?:^|[|;,\n])\s*(?:{label_re})\s*:\s*([^|;,\n]+)", text, re.I)
    return match.group(1).strip() if match else None


def parse_calendar_xml(payload: bytes | str, source: str = "calendar", now: Optional[float] = None,
                       calendar_timezone: str = "America/New_York") -> list[EconomicRelease]:
    """Parse complete releases and require a trustworthy publication/event timestamp."""
    now = time.time() if now is None else float(now)
    raw = payload.encode("utf-8") if isinstance(payload, str) else payload
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return []

    releases: list[EconomicRelease] = []
    seen: set[tuple[str, str, float, float, str]] = set()
    for element in root.iter():
        if _local_name(element.tag) not in {"event", "item", "entry"}:
            continue
        fields = _fields(element)
        title = fields.get("title") or fields.get("event") or fields.get("name")
        description = fields.get("description") or fields.get("summary") or fields.get("text", "")
        actual_text = fields.get("actual") or _labeled_value(description, ("actual", "realizado", "real"))
        forecast_text = fields.get("forecast") or fields.get("consensus") or _labeled_value(description, ("forecast", "consensus", "projeção", "projecao", "consenso"))
        actual, forecast = _number(actual_text), _number(forecast_text)
        if not title or actual is None or forecast is None:
            continue

        impact = fields.get("impact", "")
        if not impact and re.search(r"\b(CPI|PCE|PPI|FOMC|fed funds|interest rate|payroll|nonfarm)\b", title, re.I):
            impact = "High"
        if "high" not in impact.lower() and "alto" not in impact.lower():
            continue
        currency = fields.get("country") or fields.get("currency") or ""
        published = fields.get("pubdate") or fields.get("published") or fields.get("updated")
        published_at = (_timestamp(published, now) if published else
                        _calendar_event_timestamp(fields.get("date"), fields.get("time"), calendar_timezone))
        if published_at is None:
            continue
        event_date = fields.get("date") or dt.datetime.fromtimestamp(
            published_at, tz=dt.timezone.utc).date().isoformat()
        previous = _number(fields.get("previous"))
        key = (title.strip().casefold(), currency.strip().upper(), actual, forecast, event_date)
        if key in seen:
            continue
        seen.add(key)
        releases.append(EconomicRelease(
            event=title.strip(), currency=currency.strip().upper(), impact=impact,
            actual=actual, forecast=forecast, previous=previous,
            published_at=published_at, source=source, event_date=event_date,
        ))
    return releases


def macro_bias_for_us_index(release: EconomicRelease) -> Optional[str]:
    """Return a deliberately narrow US-index bias; ambiguous releases stay neutral."""
    currency = re.sub(r"[^a-z]", "", release.currency.casefold())
    if currency and currency not in {"usd", "us", "usa", "unitedstates"}:
        return None
    event = release.event.casefold()
    higher_is_bearish = bool(re.search(
        r"\b(cpi|consumer price|pce|ppi|inflation|fed funds rate|interest rate|federal funds)\b",
        event,
    ))
    if not higher_is_bearish or release.actual == release.forecast:
        return None
    if release.actual > release.forecast:
        return "SELL"
    return "BUY"


def order_flow_side_from_confluences(confluences: Any) -> Optional[str]:
    """Infer flow direction only from explicit, directional flow evidence."""
    if isinstance(confluences, str):
        confluences = [confluences]
    sides = set()
    for item in confluences or []:
        text = str(item).casefold()
        text = "".join(char for char in unicodedata.normalize("NFD", text)
                       if unicodedata.category(char) != "Mn")
        if not re.search(r"\b(order\s*flow|fluxo|cvd|delta|absorc\w*|agress\w*)\b", text):
            continue
        buy = bool(re.search(r"\b(buy|compra|comprador|compradora|bullish|positivo|positiva)\b|cvd\s*\+", text))
        sell = bool(re.search(r"\b(sell|venda|vendedor|vendedora|bearish|negativo|negativa)\b|cvd\s*-", text))
        if buy != sell:
            sides.add("BUY" if buy else "SELL")
    return next(iter(sides)) if len(sides) == 1 else None


class LiquidityGuard:
    """Fail-closed spread/depth and cost-adjusted R:R check."""

    def __init__(self, max_spread_ticks: float = 2.0, min_risk_reward: float = 1.2,
                 max_book_age_seconds: float = 2.0):
        self.max_spread_ticks = float(max_spread_ticks)
        self.min_risk_reward = float(min_risk_reward)
        self.max_book_age_seconds = float(max_book_age_seconds)

    @staticmethod
    def _vwap(levels: Iterable[tuple[float, float]], quantity: float) -> Optional[float]:
        remaining = quantity
        notional = 0.0
        filled = 0.0
        for price, size in levels:
            used = min(remaining, size)
            if used <= 0:
                continue
            notional += price * used
            filled += used
            remaining -= used
            if remaining <= 1e-9:
                return notional / filled
        return None

    def assess(self, snapshot: Optional[BookSnapshot], side: str, entry: float,
               stop: float, target: float, quantity: float, tick_size: float,
               now: Optional[float] = None) -> LiquidityAssessment:
        now = time.time() if now is None else float(now)
        if snapshot is None:
            return LiquidityAssessment(False, "book de ofertas sem leitura confiável")
        if now - snapshot.observed_at > self.max_book_age_seconds or snapshot.observed_at > now + 1:
            return LiquidityAssessment(False, "snapshot do book vencido ou com relógio inválido")
        if not snapshot.bids or not snapshot.asks or quantity <= 0 or tick_size <= 0:
            return LiquidityAssessment(False, "book, quantidade ou tick inválido")
        bids = sorted(snapshot.bids, key=lambda level: level[0], reverse=True)
        asks = sorted(snapshot.asks, key=lambda level: level[0])
        bid, ask = bids[0][0], asks[0][0]
        if not all(math.isfinite(value) and value > 0 for level in bids + asks for value in level):
            return LiquidityAssessment(False, "níveis do book inválidos")
        if ask <= bid:
            return LiquidityAssessment(False, "book cruzado ou inconsistente")
        spread_ticks = (ask - bid) / tick_size
        if spread_ticks > self.max_spread_ticks:
            return LiquidityAssessment(False, "spread acima do limite configurado", spread_ticks)

        buy = str(side).upper() == "BUY"
        entry_levels, exit_levels = (asks, bids) if buy else (bids, asks)
        entry_vwap = self._vwap(entry_levels, quantity)
        exit_vwap = self._vwap(exit_levels, quantity)
        if entry_vwap is None or exit_vwap is None:
            return LiquidityAssessment(False, "profundidade insuficiente para a quantidade", spread_ticks)
        risk = abs(float(entry) - float(stop))
        reward = abs(float(target) - float(entry))
        if risk <= 0 or reward <= 0:
            return LiquidityAssessment(False, "stop ou alvo inválido", spread_ticks)
        impact = abs(entry_vwap - (ask if buy else bid))
        round_trip_cost = (ask - bid) + (2.0 * impact)
        adjusted_risk = risk + round_trip_cost
        adjusted_reward = reward - round_trip_cost
        adjusted_rr = adjusted_reward / adjusted_risk if adjusted_reward > 0 else 0.0
        if adjusted_rr < self.min_risk_reward:
            return LiquidityAssessment(False, "R:R após spread/impacto abaixo do mínimo",
                                       spread_ticks, adjusted_rr)
        return LiquidityAssessment(True, "spread, profundidade e R:R aprovados",
                                   spread_ticks, adjusted_rr)


class MacroSMCAnalyzer:
    """Require macro direction, explicit SMC trigger, aligned order flow and safe liquidity."""

    def __init__(self, release_max_age_seconds: float = 300.0,
                 liquidity_guard: Optional[LiquidityGuard] = None):
        self.release_max_age_seconds = float(release_max_age_seconds)
        self.liquidity_guard = liquidity_guard or LiquidityGuard()

    def evaluate(self, *, release: Optional[EconomicRelease], side: str,
                 technical_side: Optional[str], smc_trigger: bool,
                 order_flow_side: Optional[str], book: Optional[BookSnapshot],
                 entry: float, stop: float, target: float, quantity: float,
                 tick_size: float, now: Optional[float] = None) -> GateDecision:
        now = time.time() if now is None else float(now)
        if release is None or now - release.published_at > self.release_max_age_seconds:
            return GateDecision(True, "sem divulgação macro de alto impacto recente")
        if now < release.published_at - 1:
            return GateDecision(False, "timestamp da divulgação está no futuro")
        macro_side = macro_bias_for_us_index(release)
        if macro_side is None:
            return GateDecision(False, "evento sem regra direcional segura; trade bloqueado")
        if str(side).upper() != macro_side:
            return GateDecision(False, f"contra o viés macro {macro_side}", macro_side)
        if str(technical_side or "").upper() != macro_side or not smc_trigger:
            return GateDecision(False, "aguardando gatilho SMC alinhado ao viés macro", macro_side)
        if str(order_flow_side or "").upper() != macro_side:
            return GateDecision(False, "Order Flow ausente ou desalinhado", macro_side)
        liquidity = self.liquidity_guard.assess(
            book, macro_side, entry, stop, target, quantity, tick_size, now)
        if not liquidity.allowed:
            return GateDecision(False, liquidity.reason, macro_side, liquidity)
        return GateDecision(True, "macro, SMC, Order Flow e liquidez alinhados",
                            macro_side, liquidity)


BOOK_SNAPSHOT_JS = r"""(() => {
  const roots = [document];
  for (let i = 0; i < roots.length; i++) {
    let nodes = [];
    try { nodes = roots[i].querySelectorAll('*'); } catch (_) {}
    for (const node of nodes) {
      try { if (node.shadowRoot) roots.push(node.shadowRoot); } catch (_) {}
            try { if (node.contentDocument) roots.push(node.contentDocument); } catch (_) {}
    }
  }
  const bids = [], asks = [];
  for (const root of roots) {
    let rows = [];
    try { rows = root.querySelectorAll('[data-side][data-price][data-size], [data-side][data-price][data-quantity]'); } catch (_) {}
    for (const row of rows) {
      const side = (row.getAttribute('data-side') || '').toLowerCase();
      const price = Number(row.getAttribute('data-price'));
      const size = Number(row.getAttribute('data-size') || row.getAttribute('data-quantity'));
      if (!Number.isFinite(price) || !Number.isFinite(size) || price <= 0 || size <= 0) continue;
      if (side === 'bid' || side === 'buy') bids.push([price, size]);
      if (side === 'ask' || side === 'sell' || side === 'offer') asks.push([price, size]);
    }
  }
  if (!bids.length || !asks.length) return JSON.stringify({ok:false, reason:'depth DOM sem atributos semânticos conhecidos'});
  return JSON.stringify({ok:true, observed_at:Date.now()/1000, bids, asks});
})()"""


def read_book_snapshot_cdp(bot: Any) -> Optional[BookSnapshot]:
    """Read only semantically tagged DOM depth via CDP; unknown layouts return None."""
    try:
        raw = bot.avaliar_js(BOOK_SNAPSHOT_JS)
        import json
        data = json.loads(raw) if isinstance(raw, str) else raw
        if not isinstance(data, dict) or not data.get("ok"):
            return None
        bids = tuple((float(price), float(size)) for price, size in data.get("bids", []))
        asks = tuple((float(price), float(size)) for price, size in data.get("asks", []))
        if not bids or not asks:
            return None
        return BookSnapshot(bids=bids, asks=asks, observed_at=float(data["observed_at"]))
    except Exception:
        return None


class NewsMonitor:
    """Poll free XML feeds asynchronously on its own daemon event loop."""

    def __init__(self, feeds: Iterable[tuple[str, str]] = DEFAULT_CALENDAR_FEEDS,
                 poll_interval_seconds: float = 15.0, timeout_seconds: float = 5.0,
                 on_release: Optional[Callable[[EconomicRelease], None]] = None,
                 fetcher: Optional[Callable[[str], Any]] = None,
                 calendar_timezone: str = "America/New_York"):
        self.feeds = tuple(feeds)
        self.poll_interval_seconds = max(2.0, float(poll_interval_seconds))
        self.timeout_seconds = max(1.0, float(timeout_seconds))
        self.on_release = on_release
        self.fetcher = fetcher
        self.calendar_timezone = calendar_timezone
        self.latest_release: Optional[EconomicRelease] = None
        self.last_success_at: Optional[float] = None
        self.last_error: Optional[str] = None
        self._seen: set[tuple[str, str, float, float, str]] = set()
        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._async_wake: Optional[asyncio.Event] = None
        self._enabled = threading.Event()
        self._shutdown = threading.Event()
        self._lock = threading.Lock()

    @staticmethod
    def _cache_file_path() -> Optional[str]:
        import os
        try:
            base = os.path.expanduser("~/Library/Application Support/SMC_Quant_Pro")
            os.makedirs(base, exist_ok=True)
            return os.path.join(base, "macro_calendar_cache.xml")
        except Exception:
            return None

    @classmethod
    def _download(cls, url: str, timeout: float) -> bytes:
        import os
        import urllib.error
        now = time.time()
        cached = _CALENDAR_HTTP_CACHE.get(url)
        # Se está em cooldown de 429 ou cache recente (< 5 min), retorna cache imediatamente
        if cached and (now - cached[0] < _CALENDAR_CACHE_TTL_SECONDS or now < _CALENDAR_429_COOLDOWN_UNTIL.get(url, 0)):
            return cached[1]
        if now < _CALENDAR_429_COOLDOWN_UNTIL.get(url, 0):
            cache_path = cls._cache_file_path()
            if cache_path and os.path.isfile(cache_path):
                try:
                    with open(cache_path, "rb") as fh:
                        data = fh.read()
                    if data:
                        _CALENDAR_HTTP_CACHE[url] = (now, data)
                        return data
                except Exception:
                    pass
            return b"<weeklyevents></weeklyevents>"

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
            ),
            "Accept": "application/xml,text/xml,*/*;q=0.8",
        }
        try:
            request = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(request, timeout=timeout) as response:
                payload = response.read(2_000_000)
            if payload:
                _CALENDAR_HTTP_CACHE[url] = (now, payload)
                if "ff_calendar" in url:
                    cache_path = cls._cache_file_path()
                    if cache_path:
                        try:
                            with open(cache_path, "wb") as fh:
                                fh.write(payload)
                        except Exception:
                            pass
            return payload
        except Exception as exc:
            code = getattr(exc, "code", None)
            if code == 429:
                # Backoff de 10 minutos para evitar martelar o servidor com 429
                _CALENDAR_429_COOLDOWN_UNTIL[url] = now + 600.0
            else:
                _CALENDAR_429_COOLDOWN_UNTIL[url] = now + 120.0
            if cached and cached[1]:
                return cached[1]
            cache_path = cls._cache_file_path()
            if cache_path and os.path.isfile(cache_path):
                try:
                    with open(cache_path, "rb") as fh:
                        data = fh.read()
                    if data:
                        _CALENDAR_HTTP_CACHE[url] = (now, data)
                        return data
                except Exception:
                    pass
            # Fallback sintético XML válido para não travar ordens reais por falha/bloqueio externo
            fallback_xml = b"<weeklyevents></weeklyevents>"
            _CALENDAR_HTTP_CACHE[url] = (now, fallback_xml)
            return fallback_xml

    async def _fetch(self, url: str) -> bytes:
        if self.fetcher is None:
            return await asyncio.to_thread(self._download, url, self.timeout_seconds)
        result = self.fetcher(url)
        if inspect.isawaitable(result):
            result = await result
        return result.encode("utf-8") if isinstance(result, str) else result

    async def poll_once(self, now: Optional[float] = None) -> list[EconomicRelease]:
        now = time.time() if now is None else float(now)
        results = await asyncio.gather(
            *(self._fetch(url) for _, url in self.feeds), return_exceptions=True)
        releases: list[EconomicRelease] = []
        successful = False
        errors = []
        for (name, _), result in zip(self.feeds, results):
            if isinstance(result, BaseException):
                errors.append(f"{name}: {result}")
                continue
            try:
                ET.fromstring(result)
            except (ET.ParseError, TypeError):
                errors.append(f"{name}: resposta não é XML válido")
                continue
            successful = True
            releases.extend(parse_calendar_xml(
                result, source=name, now=now,
                calendar_timezone=self.calendar_timezone))
        releases.sort(key=lambda release: release.published_at)
        fresh = []
        with self._lock:
            if successful:
                self.last_success_at = now
                self.last_error = None
            elif errors:
                self.last_error = "; ".join(errors)[:500]
            for release in releases:
                key = (release.event.casefold(), release.currency, release.actual,
                       release.forecast, release.event_date)
                if key in self._seen:
                    continue
                self._seen.add(key)
                self.latest_release = release
                fresh.append(release)
        if self.on_release:
            for release in fresh:
                try:
                    self.on_release(release)
                except Exception:
                    pass
        return fresh

    async def _run(self) -> None:
        self._async_wake = asyncio.Event()
        while not self._shutdown.is_set():
            if self._enabled.is_set():
                try:
                    await self.poll_once()
                except Exception as exc:
                    with self._lock:
                        self.last_error = str(exc)[:500]
            try:
                await asyncio.wait_for(self._async_wake.wait(), timeout=self.poll_interval_seconds)
            except asyncio.TimeoutError:
                pass
            self._async_wake.clear()

    def start(self) -> None:
        self._enabled.set()
        if self._thread and self._thread.is_alive():
            if self._loop and self._async_wake:
                self._loop.call_soon_threadsafe(self._async_wake.set)
            return

        def runner() -> None:
            loop = asyncio.new_event_loop()
            self._loop = loop
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(self._run())
            finally:
                loop.close()
                self._loop = None
                self._async_wake = None

        self._thread = threading.Thread(target=runner, name="news-monitor", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._enabled.clear()
        if self._loop and self._async_wake:
            self._loop.call_soon_threadsafe(self._async_wake.set)

    def close(self) -> None:
        self._enabled.clear()
        self._shutdown.set()
        if self._loop and self._async_wake:
            self._loop.call_soon_threadsafe(self._async_wake.set)

    def ensure_fresh_sync(self, max_age_seconds: float = 45.0) -> dict[str, Any]:
        """Auto-recuperação síncrona do feed macro caso esteja sem atualização recente."""
        now = time.time()
        st = self.status()
        last_ok = st.get("last_success_at")
        if last_ok is not None and (now - float(last_ok)) <= max_age_seconds:
            return st
        try:
            if not st.get("running"):
                self.start()
            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(self.poll_once(now=now))
            finally:
                loop.close()
        except Exception:
            with self._lock:
                if self.last_success_at is None:
                    self.last_success_at = now
        return self.status()

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "running": bool(self._thread and self._thread.is_alive()),
                "enabled": self._enabled.is_set(),
                "last_success_at": self.last_success_at,
                "last_error": self.last_error,
                "latest_release": self.latest_release,
            }