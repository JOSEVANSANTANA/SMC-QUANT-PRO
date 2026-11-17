"""Modo avançado opcional para SMC Quant Pro.

Este módulo foi desenhado para ficar DESLIGADO por padrão e para manter o
robô atual funcionando sem qualquer mudança no comportamento existente.

Ele oferece um conjunto pequeno, mas realista, de componentes para:
- Arbitragem estatística (pairs trading / cointegração);
- Market making direcional em zonas istitucionais;
- Kill switch por latência e proteção de risco.

Não existe execução automática aqui sem o interruptor do app estar ligado.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
import math
import re
import statistics
from typing import Any, Deque, Dict, Iterable, Optional, Sequence


@dataclass
class LatencySnapshot:
    """Métrica simples de latência de leitura/execução."""

    timestamp: float
    latency_ms: float


class LatencyGuard:
    """Protege a estratégia avançada quando a latência dispara."""

    def __init__(self, max_latency_ms: float = 180.0, sample_size: int = 25):
        self.max_latency_ms = float(max_latency_ms)
        self.samples: Deque[LatencySnapshot] = deque(maxlen=max(sample_size, 5))
        self.kill_switch = False

    def observe(self, latency_ms: float) -> bool:
        self.samples.append(LatencySnapshot(timestamp=time_now(), latency_ms=float(latency_ms)))
        if not self.samples:
            self.kill_switch = False
            return False
        average = sum(item.latency_ms for item in self.samples) / len(self.samples)
        peak = max(item.latency_ms for item in self.samples)
        self.kill_switch = average > self.max_latency_ms or peak > self.max_latency_ms * 1.25
        return self.kill_switch

    def reset(self) -> None:
        self.samples.clear()
        self.kill_switch = False


class PairTradeEngine:
    """Paper evaluator for rolling, synchronized pair-spread candidates.

    It does not claim formal cointegration: candidates require a positive OLS
    hedge ratio, correlated returns, enough synchronized samples, and an
    out-of-band residual z-score. The caller must keep these candidates out of
    live routing until pair execution and fill handling are validated.
    """

    def __init__(self, zscore_threshold: float = 2.0, max_open_positions: int = 2,
                 min_observations: int = 30, max_sample_skew_seconds: float = 90.0,
                 min_return_correlation: float = 0.65, lookback: int = 60):
        self.zscore_threshold = float(zscore_threshold)
        self.max_open_positions = int(max_open_positions)
        self.min_observations = max(10, int(min_observations))
        self.max_sample_skew_seconds = max(1.0, float(max_sample_skew_seconds))
        self.min_return_correlation = float(min_return_correlation)
        self.lookback = max(self.min_observations, int(lookback))
        self.open_pairs = 0
        self.price_history: Dict[str, Deque[tuple[float, float]]] = {}
        self._active_spreads: Dict[tuple[str, str], str] = {}
        self._pair_metrics: Dict[tuple[str, str], Dict[str, Any]] = {}

    @staticmethod
    def _asset_key(asset: str) -> str:
        value = re.sub(r"[^A-Z0-9!]", "", str(asset or "").upper())
        match = re.fullmatch(r"([A-Z0-9]{1,5}?)(?:[FGHJKMNQUVXZ]\d{1,4}|1!)", value)
        return match.group(1) if match else value

    def observe_price(self, asset: str, price: float,
                      timestamp: Optional[float] = None) -> bool:
        key = self._asset_key(asset)
        try:
            value = float(price)
            ts = float(time_now() if timestamp is None else timestamp)
        except (TypeError, ValueError):
            return False
        if not key or not math.isfinite(value) or value <= 0 or not math.isfinite(ts):
            return False
        history = self.price_history.setdefault(key, deque(maxlen=240))
        if history and ts <= history[-1][0]:
            return False
        history.append((ts, value))
        return True
    def _synchronized_samples(self, primary: str, secondary: str,
                              now: float) -> list[tuple[float, float, float]]:
        first = list(self.price_history.get(self._asset_key(primary), ()))
        second = list(self.price_history.get(self._asset_key(secondary), ()))
        if not first or not second:
            return []
        if now - first[-1][0] > self.max_sample_skew_seconds or \
                now - second[-1][0] > self.max_sample_skew_seconds:
            return []
        paired = []
        i = j = 0
        while i < len(first) and j < len(second):
            first_ts, first_price = first[i]
            second_ts, second_price = second[j]
            skew = first_ts - second_ts
            if abs(skew) <= self.max_sample_skew_seconds:
                paired.append(((first_ts + second_ts) / 2, first_price, second_price))
                i += 1
                j += 1
            elif skew < 0:
                i += 1
            else:
                j += 1
        return paired[-(self.lookback + 1):]

    def evaluate_assets(self, primary_asset: str, secondary_asset: str,
                        now: Optional[float] = None) -> Optional[Dict[str, Any]]:
        """Return one mean-reversion pair candidate after all readiness checks."""
        if self.open_pairs >= self.max_open_positions:
            return None
        primary_key, secondary_key = self._asset_key(primary_asset), self._asset_key(secondary_asset)
        if not primary_key or not secondary_key or primary_key == secondary_key:
            return None
        now = time_now() if now is None else float(now)
        samples = self._synchronized_samples(primary_key, secondary_key, now)
        if len(samples) < self.min_observations + 1:
            return None

        primary_logs = [math.log(sample[1]) for sample in samples]
        secondary_logs = [math.log(sample[2]) for sample in samples]
        primary_mean = statistics.fmean(primary_logs)
        secondary_mean = statistics.fmean(secondary_logs)
        variance = sum((value - secondary_mean) ** 2 for value in secondary_logs)
        if variance <= 1e-12:
            return None
        beta = sum((x - secondary_mean) * (y - primary_mean)
                   for x, y in zip(secondary_logs, primary_logs)) / variance
        if not math.isfinite(beta) or beta <= 0:
            return None
        intercept = primary_mean - beta * secondary_mean

        primary_returns = [b - a for a, b in zip(primary_logs, primary_logs[1:])]
        secondary_returns = [b - a for a, b in zip(secondary_logs, secondary_logs[1:])]
        return_correlation = self._correlation(primary_returns, secondary_returns)
        if return_correlation is None or return_correlation < self.min_return_correlation:
            return None
        primary_volatility = statistics.pstdev(primary_returns[-self.lookback:])
        secondary_volatility = statistics.pstdev(secondary_returns[-self.lookback:])
        if primary_volatility <= 0 or secondary_volatility <= 0:
            return None

        residuals = [p - intercept - beta * s
                     for p, s in zip(primary_logs, secondary_logs)]
        baseline = residuals[-(self.lookback + 1):-1]
        if len(baseline) < self.min_observations:
            return None
        spread_mean = statistics.fmean(baseline)
        spread_std = statistics.pstdev(baseline)
        if not math.isfinite(spread_std) or spread_std <= 1e-8:
            return None
        zscore = (residuals[-1] - spread_mean) / spread_std
        pair_key = (primary_key, secondary_key)
        metrics = {
            "primary_asset": primary_key,
            "secondary_asset": secondary_key,
            "primary_price": samples[-1][1],
            "secondary_price": samples[-1][2],
            "beta": beta,
            "spread_zscore": zscore,
            "spread_mean": spread_mean,
            "spread_std": spread_std,
            "return_correlation": return_correlation,
            "primary_return_volatility": primary_volatility,
            "secondary_return_volatility": secondary_volatility,
            "observations": len(samples),
            "observed_at": samples[-1][0],
        }
        self._pair_metrics[pair_key] = metrics
        if abs(zscore) < self.zscore_threshold * 0.75:
            self._active_spreads.pop(pair_key, None)
            return None
        direction = "HIGH" if zscore > 0 else "LOW"
        if self._active_spreads.get(pair_key) == direction:
            return None
        self._active_spreads[pair_key] = direction
        primary_side, secondary_side = (("SELL", "BUY") if zscore > 0
                                        else ("BUY", "SELL"))
        return {**metrics, "strategy": "PAIRS_PAPER",
                "primary_side": primary_side, "secondary_side": secondary_side}

    def pair_state(self, primary_asset: str, secondary_asset: str,
                   now: Optional[float] = None) -> Optional[Dict[str, Any]]:
        key = (self._asset_key(primary_asset), self._asset_key(secondary_asset))
        metrics = self._pair_metrics.get(key)
        now = time_now() if now is None else float(now)
        if not metrics or now - float(metrics["observed_at"]) > self.max_sample_skew_seconds:
            return None
        return dict(metrics)

    @staticmethod
    def _correlation(first: Sequence[float], second: Sequence[float]) -> Optional[float]:
        if len(first) != len(second) or len(first) < 3:
            return None
        first_mean, second_mean = statistics.fmean(first), statistics.fmean(second)
        first_var = sum((value - first_mean) ** 2 for value in first)
        second_var = sum((value - second_mean) ** 2 for value in second)
        if first_var <= 1e-12 or second_var <= 1e-12:
            return None
        covariance = sum((a - first_mean) * (b - second_mean)
                         for a, b in zip(first, second))
        return covariance / math.sqrt(first_var * second_var)

    def evaluate(self, spread_zscore: float, spread_mean: float,
                 spread_std: float) -> Optional[Dict[str, Any]]:
        if self.open_pairs >= self.max_open_positions or spread_std <= 0:
            return None
        if spread_zscore > self.zscore_threshold:
            return {"strategy": "PAIR_LONG", "side": "BUY",
                    "reason": "spread acima do z-score de reversão",
                    "spread_zscore": spread_zscore, "spread_mean": spread_mean,
                    "spread_std": spread_std}
        if spread_zscore < -self.zscore_threshold:
            return {"strategy": "PAIR_SHORT", "side": "SELL",
                    "reason": "spread abaixo do z-score de reversão",
                    "spread_zscore": spread_zscore, "spread_mean": spread_mean,
                    "spread_std": spread_std}
        return None

    def on_fill(self, filled: bool = True) -> None:
        self.open_pairs = max(0, self.open_pairs + (1 if filled else -1))


def allocate_pair_risk(
    *,
    max_risk_usd: float,
    beta: float,
    primary_entry: float,
    primary_stop: float,
    primary_point_value: float,
    primary_tick_size: float,
    secondary_entry: float,
    secondary_stop: float,
    secondary_point_value: float,
    secondary_tick_size: float,
    slippage_ticks: float = 1.0,
) -> Optional[Dict[str, float | int]]:
    """Allocate one risk budget to both pair legs using log-beta notional ratio.

    Market-entry and exit slippage reserve are included before integer contract
    scaling. Returns None rather than forcing a minimum contract that exceeds
    the shared plan budget.
    """
    values = (max_risk_usd, beta, primary_entry, primary_stop,
              primary_point_value, primary_tick_size, secondary_entry,
              secondary_stop, secondary_point_value, secondary_tick_size,
              slippage_ticks)
    try:
        numeric_values = tuple(map(float, values))
        (risk_cap, hedge_beta, p_entry, p_stop, p_value, p_tick, s_entry,
         s_stop, s_value, s_tick, slip) = numeric_values
    except (TypeError, ValueError):
        return None
    if (not all(math.isfinite(value) for value in numeric_values)
            or risk_cap <= 0 or hedge_beta <= 0 or p_entry <= 0 or s_entry <= 0
            or p_value <= 0 or s_value <= 0 or p_tick <= 0 or s_tick <= 0
            or p_entry == p_stop or s_entry == s_stop or slip < 0):
        return None

    target_hedge_ratio = hedge_beta * p_entry * p_value / (s_entry * s_value)
    secondary_per_primary = round(target_hedge_ratio)
    if secondary_per_primary <= 0:
        return None
    hedge_error = abs(secondary_per_primary - target_hedge_ratio) / target_hedge_ratio
    if hedge_error > 0.25:
        return None
    p_risk = abs(p_entry - p_stop) * p_value
    s_risk = abs(s_entry - s_stop) * s_value * secondary_per_primary
    slip_reserve = 2 * slip * (p_tick * p_value + secondary_per_primary * s_tick * s_value)
    risk_per_bundle = p_risk + s_risk + slip_reserve
    scale = int(risk_cap // risk_per_bundle) if risk_per_bundle > 0 else 0
    if scale <= 0:
        return None
    primary_quantity = scale
    secondary_quantity = secondary_per_primary * scale
    return {
        "primary_quantity": primary_quantity,
        "secondary_quantity": secondary_quantity,
        "primary_risk_budget_usd": primary_quantity * p_risk,
        "secondary_risk_budget_usd": secondary_quantity * abs(s_entry - s_stop) * s_value,
        "slippage_reserve_usd": scale * slip_reserve,
        "reserved_risk_usd": scale * risk_per_bundle,
        "secondary_contracts_per_primary": secondary_per_primary,
        "hedge_ratio_error_pct": hedge_error * 100.0,
    }


class DirectionalMarketMaker:
    """Quotes em suporte/resistência institucional, com limitação de inventory."""

    def __init__(self, max_inventory: int = 3, min_spread_ticks: float = 0.5):
        self.max_inventory = int(max_inventory)
        self.min_spread_ticks = float(min_spread_ticks)
        self.inventory = 0

    def evaluate(self, price: float, support: float, resistance: float, order_flow_bias: float) -> Optional[Dict[str, Any]]:
        if abs(price - support) <= 0.0 and order_flow_bias <= 0:
            return {"strategy": "MM_BID", "side": "BUY", "reason": "zona de suporte institucional"}
        if abs(price - resistance) <= 0.0 and order_flow_bias >= 0:
            return {"strategy": "MM_ASK", "side": "SELL", "reason": "zona de resistência institucional"}
        if abs(price - support) <= 0.0 or abs(price - resistance) <= 0.0:
            if abs(self.inventory) >= self.max_inventory:
                return None
            return {"strategy": "MM_DIRECTIONAL", "side": "BUY" if order_flow_bias > 0 else "SELL", "reason": "bias de liquidez"}
        return None

    def on_fill(self, quantity: int) -> None:
        self.inventory = max(-self.max_inventory, min(self.max_inventory, self.inventory + quantity))

    def evaluate_book(self, *, price: float, support: float, resistance: float,
                      order_flow_bias: float, book: Any, tick_size: float,
                      min_depth: float = 1.0, max_spread_ticks: float = 2.0,
                      level_distance_ticks: float = 2.0,
                      imbalance_threshold: float = 1.25,
                      now: Optional[float] = None) -> Optional[Dict[str, Any]]:
        """Paper-only maker candidate using validated book levels and nearby structure."""
        try:
            bids = sorted(book.bids, key=lambda level: level[0], reverse=True)
            asks = sorted(book.asks, key=lambda level: level[0])
            tick = float(tick_size)
            current = float(price)
            flow = float(order_flow_bias)
            support_level, resistance_level = float(support), float(resistance)
        except (AttributeError, TypeError, ValueError):
            return None
        if not bids or not asks or tick <= 0 or asks[0][0] <= bids[0][0]:
            return None
        current_time = float(time_now() if now is None else now)
        if abs(current_time - float(book.observed_at)) > 2.0:
            return None
        if (asks[0][0] - bids[0][0]) / tick > max_spread_ticks:
            return None
        bid_depth = sum(float(size) for _, size in bids[:3])
        ask_depth = sum(float(size) for _, size in asks[:3])
        if bid_depth < min_depth or ask_depth < min_depth:
            return None
        if abs(current - support_level) <= level_distance_ticks * tick:
            if flow > 0 and bid_depth >= ask_depth * imbalance_threshold:
                if abs(self.inventory) >= self.max_inventory:
                    return None
                return {"strategy": "MM_BID", "side": "BUY", "entry": bids[0][0],
                        "support": support_level, "resistance": resistance_level,
                        "reason": "suporte próximo com fluxo e profundidade compradores"}
        if abs(current - resistance_level) <= level_distance_ticks * tick:
            if flow < 0 and ask_depth >= bid_depth * imbalance_threshold:
                if abs(self.inventory) >= self.max_inventory:
                    return None
                return {"strategy": "MM_ASK", "side": "SELL", "entry": asks[0][0],
                        "support": support_level, "resistance": resistance_level,
                        "reason": "resistência próxima com fluxo e profundidade vendedores"}
        return None


@dataclass(frozen=True)
class PaperLegIntent:
    asset: str
    side: str
    entry: float
    stop: float
    target: float
    quantity: int
    point_value: float
    tick_size: float
    trailing: Optional[Dict[str, Any]] = None

    @property
    def planned_risk_usd(self) -> float:
        return abs(float(self.entry) - float(self.stop)) * int(self.quantity) * float(self.point_value)


@dataclass(frozen=True)
class PaperIntent:
    intent_id: str
    strategy: str
    legs: tuple[PaperLegIntent, ...]
    reason: str
    created_at: float
    entry_mode: str = "MARKET"
    metadata: Optional[Dict[str, Any]] = None

    @property
    def planned_risk_usd(self) -> float:
        return sum(leg.planned_risk_usd for leg in self.legs)


@dataclass
class PaperTrade:
    intent: PaperIntent
    status: str
    current_stops: list[float]
    trailing_armed: list[bool]
    fill_prices: list[float]
    reserved_risk_usd: float
    closed_at: Optional[float] = None
    pnl_usd: float = 0.0
    exit_reason: Optional[str] = None


class PaperExecutionBook:
    """Replay/paper portfolio with atomic pair entry, aggregate risk, and bracket/trailing exits."""

    def __init__(self, *, slippage_ticks: float = 1.0, max_history: int = 1000,
                 max_pair_skew_seconds: float = 90.0,
                 pending_ttl_seconds: float = 120.0,
                 reentry_cooldown_seconds: float = 60.0):
        self.slippage_ticks = max(0.0, float(slippage_ticks))
        self.max_history = max(50, int(max_history))
        self.max_pair_skew_seconds = max(1.0, float(max_pair_skew_seconds))
        self.pending_ttl_seconds = max(1.0, float(pending_ttl_seconds))
        self.reentry_cooldown_seconds = max(0.0, float(reentry_cooldown_seconds))
        self.trades: list[PaperTrade] = []
        self._intent_ids: set[str] = set()
        self._last_prices: Dict[str, tuple[float, float]] = {}
        self._last_submit_by_key: Dict[tuple[str, tuple[str, ...]], float] = {}

    @staticmethod
    def _asset_key(asset: str) -> str:
        return PairTradeEngine._asset_key(asset)

    @property
    def open_risk_usd(self) -> float:
        return sum(trade.reserved_risk_usd for trade in self.trades
                   if trade.status in {"OPEN", "PENDING"})

    def submit(self, intent: PaperIntent, max_total_risk_usd: float) -> tuple[bool, str]:
        if intent.intent_id in self._intent_ids:
            return False, "paper intent duplicada"
        if intent.strategy.startswith("PAIRS") and len(intent.legs) != 2:
            return False, "um paper pair exige exatamente duas pernas"
        if len(intent.legs) not in (1, 2):
            return False, "quantidade de pernas não suportada no paper"
        if intent.entry_mode not in {"MARKET", "PASSIVE"}:
            return False, "modelo de execução paper desconhecido"
        if any(leg.side not in ("BUY", "SELL") or leg.quantity <= 0
               or leg.point_value <= 0 or leg.tick_size <= 0
               or leg.entry == leg.stop or leg.entry == leg.target
               for leg in intent.legs):
            return False, "perna paper inválida"
        keys = [self._asset_key(leg.asset) for leg in intent.legs]
        if len(keys) != len(set(keys)):
            return False, "as duas pernas do pair precisam ser ativos distintos"
        cooldown_key = (intent.strategy, tuple(sorted(keys)))
        last_submit = self._last_submit_by_key.get(cooldown_key)
        if (last_submit is not None and
                float(intent.created_at) - last_submit < self.reentry_cooldown_seconds):
            return False, "cooldown paper da estratégia/ativos ainda ativo"
        entry_slippage_ticks = self.slippage_ticks if intent.entry_mode == "MARKET" else 0.0
        risk = sum((abs(float(leg.entry) - float(leg.stop))
                + (entry_slippage_ticks + self.slippage_ticks) * leg.tick_size)
               * int(leg.quantity) * float(leg.point_value)
               for leg in intent.legs)
        if not math.isfinite(risk) or risk <= 0:
            return False, "risco paper inválido"
        if risk > float(max_total_risk_usd) or self.open_risk_usd + risk > float(max_total_risk_usd):
            return False, "risco agregado paper excede o orçamento do plano"
        self.trades.append(PaperTrade(
            intent=intent, status="PENDING" if intent.entry_mode == "PASSIVE" else "OPEN",
            current_stops=[float(leg.stop) for leg in intent.legs],
            trailing_armed=[False for _ in intent.legs],
            fill_prices=[float(leg.entry) +
                         (1.0 if leg.side == "BUY" else -1.0)
                         * entry_slippage_ticks * leg.tick_size
                         for leg in intent.legs],
            reserved_risk_usd=risk,
        ))
        self._intent_ids.add(intent.intent_id)
        self._last_submit_by_key[cooldown_key] = float(intent.created_at)
        if len(self.trades) > self.max_history:
            removed = self.trades.pop(0)
            self._intent_ids.discard(removed.intent.intent_id)
        return True, "paper trade aberto sob o orçamento de risco"

    def mark_prices(self, prices: Dict[str, float], timestamp: Optional[float] = None) -> list[PaperTrade]:
        now = float(time_now() if timestamp is None else timestamp)
        for asset, price in (prices or {}).items():
            try:
                value = float(price)
            except (TypeError, ValueError):
                continue
            if value > 0 and math.isfinite(value):
                self._last_prices[self._asset_key(asset)] = (value, now)

        closed = []
        for trade in self.trades:
            if trade.status not in {"OPEN", "PENDING"}:
                continue
            if (trade.status == "PENDING"
                    and now - trade.intent.created_at > self.pending_ttl_seconds):
                trade.status = "CANCELLED"
                trade.closed_at = now
                trade.exit_reason = "PENDING_EXPIRED"
                continue
            keys = [self._asset_key(leg.asset) for leg in trade.intent.legs]
            latest = [self._last_prices.get(key) for key in keys]
            if any(sample is None for sample in latest):
                continue
            if len(latest) == 2 and abs(latest[0][1] - latest[1][1]) > self.max_pair_skew_seconds:
                continue
            if trade.status == "PENDING":
                filled = []
                for leg, sample in zip(trade.intent.legs, latest):
                    price = sample[0]
                    through = (price <= leg.entry - leg.tick_size if leg.side == "BUY"
                               else price >= leg.entry + leg.tick_size)
                    filled.append(through)
                if all(filled):
                    trade.status = "OPEN"
                    trade.fill_prices = [leg.entry for leg in trade.intent.legs]
                continue
            exits = []
            reasons = []
            for index, (leg, sample) in enumerate(zip(trade.intent.legs, latest)):
                price = sample[0]
                fill_price = trade.fill_prices[index]
                stop = trade.current_stops[index]
                trailing = leg.trailing or {}
                favorable_ticks = ((price - fill_price) if leg.side == "BUY"
                                   else (fill_price - price)) / leg.tick_size
                activation = float(trailing.get("acionar", 0) or 0)
                trail_ticks = float(trailing.get("stop", 0) or 0)
                if trail_ticks > 0 and favorable_ticks >= activation:
                    candidate = (price - trail_ticks * leg.tick_size if leg.side == "BUY"
                                 else price + trail_ticks * leg.tick_size)
                    trade.current_stops[index] = (max(stop, candidate) if leg.side == "BUY"
                                                  else min(stop, candidate))
                    trade.trailing_armed[index] = True
                    stop = trade.current_stops[index]
                hit_stop = (price <= stop if leg.side == "BUY" else price >= stop)
                is_pair = trade.intent.strategy.startswith("PAIRS")
                hit_target = (not is_pair and
                              (price >= leg.target if leg.side == "BUY" else price <= leg.target))
                exits.append(price)
                reasons.append("STOP" if hit_stop else "TARGET" if hit_target else "")
            triggered = next((reason for reason in reasons if reason), None)
            if not triggered:
                continue
            pnl = 0.0
            for leg, fill_price, price in zip(trade.intent.legs, trade.fill_prices, exits):
                signed = 1.0 if leg.side == "BUY" else -1.0
                adverse_exit = price - signed * self.slippage_ticks * leg.tick_size
                pnl += (adverse_exit - fill_price) * signed * leg.quantity * leg.point_value
            trade.status = "CLOSED"
            trade.closed_at = now
            trade.pnl_usd = round(pnl, 2)
            trade.exit_reason = triggered
            closed.append(trade)
        return closed

    def mark_pair_zscore(self, primary_asset: str, secondary_asset: str,
                         zscore: float, timestamp: Optional[float] = None) -> list[PaperTrade]:
        """Close a pair atomically when its spread reverts or hits the z-stop."""
        now = float(time_now() if timestamp is None else timestamp)
        pair_assets = {self._asset_key(primary_asset), self._asset_key(secondary_asset)}
        latest_prices = {}
        for key in pair_assets:
            sample = self._last_prices.get(key)
            if sample is None or now - sample[1] > self.max_pair_skew_seconds:
                return []
            latest_prices[key] = sample[0]

        closed = []
        for trade in self.trades:
            if trade.status != "OPEN" or not trade.intent.strategy.startswith("PAIRS"):
                continue
            trade_assets = {self._asset_key(leg.asset) for leg in trade.intent.legs}
            if trade_assets != pair_assets:
                continue
            metadata = trade.intent.metadata or {}
            entry_z = float(metadata.get("entry_zscore", 0.0))
            target_z = abs(float(metadata.get("target_zscore", 0.25)))
            stop_z = abs(float(metadata.get("stop_zscore", 3.5)))
            target_hit = (zscore <= target_z if entry_z > 0 else zscore >= -target_z)
            stop_hit = (zscore >= stop_z if entry_z > 0 else zscore <= -stop_z)
            if not target_hit and not stop_hit:
                continue
            pnl = 0.0
            for leg, fill_price in zip(trade.intent.legs, trade.fill_prices):
                signed = 1.0 if leg.side == "BUY" else -1.0
                mark = latest_prices[self._asset_key(leg.asset)]
                adverse_exit = mark - signed * self.slippage_ticks * leg.tick_size
                pnl += (adverse_exit - fill_price) * signed * leg.quantity * leg.point_value
            trade.status = "CLOSED"
            trade.closed_at = now
            trade.pnl_usd = round(pnl, 2)
            trade.exit_reason = "PAIR_MEAN" if target_hit else "PAIR_Z_STOP"
            closed.append(trade)
        return closed

    def status(self) -> Dict[str, Any]:
        closed = [trade for trade in self.trades if trade.status == "CLOSED"]
        return {
            "open": sum(trade.status == "OPEN" for trade in self.trades),
            "pending": sum(trade.status == "PENDING" for trade in self.trades),
            "closed": len(closed),
            "cancelled": sum(trade.status == "CANCELLED" for trade in self.trades),
            "open_risk_usd": round(self.open_risk_usd, 2),
            "realized_pnl_usd": round(sum(trade.pnl_usd for trade in closed), 2),
            "trades": len(self.trades),
        }


class AdvancedModeController:
    """Controla o modo avançado de forma segura: desliga por padrão."""

    def __init__(
        self,
        enabled: bool = False,
        max_latency_ms: float = 180.0,
        pairs_enabled: bool = True,
        market_making_enabled: bool = True,
        paper_mode: bool = True,
        risk_plan: Optional[Dict[str, Any]] = None,
        primary_asset: Optional[str] = None,
        secondary_asset: Optional[str] = None,
        primary_window: Optional[str] = None,
        secondary_window: Optional[str] = None,
    ):
        self.enabled = bool(enabled)
        self.pairs_enabled = bool(pairs_enabled)
        self.market_making_enabled = bool(market_making_enabled)
        self.paper_mode = bool(paper_mode)
        self.max_latency_ms = float(max_latency_ms)
        self.risk_plan: Dict[str, Any] = dict(risk_plan or {})
        self.primary_asset = (primary_asset or "").strip()
        self.secondary_asset = (secondary_asset or "").strip()
        self.primary_window = (primary_window or "").strip()
        self.secondary_window = (secondary_window or "").strip()
        self.report_confluences = True
        self.latency_guard = LatencyGuard(max_latency_ms=self.max_latency_ms)
        self.pairs_engine = PairTradeEngine()
        self.market_maker = DirectionalMarketMaker()
        self.paper_book = PaperExecutionBook()
        self.kill_switch = False

    @property
    def active(self) -> bool:
        return self.enabled and (self.pairs_enabled or self.market_making_enabled)

    def set_risk_plan(self, risk_plan: Optional[Dict[str, Any]]) -> None:
        self.risk_plan = dict(risk_plan or {})

    def plan_ready(self) -> bool:
        if not self.enabled:
            return True
        if not isinstance(self.risk_plan, dict):
            return False
        margem = float(self.risk_plan.get("margem", 0) or 0)
        risco_pct = float(self.risk_plan.get("risco_pct", 1.0) or 1.0)
        drawdown = abs(float(self.risk_plan.get("drawdown_maximo", 0) or 0))
        return margem > 0 and risco_pct > 0 and drawdown > 0

    def set_strategy_flags(self, *, pairs: Optional[bool] = None, market_making: Optional[bool] = None) -> None:
        if pairs is not None:
            self.pairs_enabled = bool(pairs)
        if market_making is not None:
            self.market_making_enabled = bool(market_making)

    def configure_assets(
        self,
        *,
        primary_asset: Optional[str] = None,
        secondary_asset: Optional[str] = None,
        primary_window: Optional[str] = None,
        secondary_window: Optional[str] = None,
        report_confluences: Optional[bool] = None,
    ) -> None:
        if primary_asset is not None:
            self.primary_asset = str(primary_asset).strip()
        if secondary_asset is not None:
            self.secondary_asset = str(secondary_asset).strip()
        if primary_window is not None:
            self.primary_window = str(primary_window).strip()
        if secondary_window is not None:
            self.secondary_window = str(secondary_window).strip()
        if report_confluences is not None:
            self.report_confluences = bool(report_confluences)

    @staticmethod
    def _asset_key(asset: Optional[str]) -> str:
        value = re.sub(r"[^A-Z0-9!]", "", str(asset or "").upper())
        match = re.fullmatch(r"([A-Z0-9]{1,5}?)(?:[FGHJKMNQUVXZ]\d{1,4}|1!)", value)
        return match.group(1) if match else value

    def is_secondary_validation_only(self, asset: Optional[str] = None,
                                      window: Optional[str] = None) -> bool:
        """True when this analysis belongs to the configured standby asset/window."""
        if not self.enabled:
            return False
        secondary_window = (self.secondary_window or "").strip().casefold()
        current_window = (window or "").strip().casefold()
        if secondary_window and not secondary_window.startswith("(") and current_window:
            return current_window == secondary_window
        secondary_asset = self._asset_key(self.secondary_asset)
        current_asset = self._asset_key(asset)
        return bool(secondary_asset and current_asset and secondary_asset == current_asset)

    def observe_latency(self, latency_ms: float) -> bool:
        self.kill_switch = self.latency_guard.observe(latency_ms)
        return self.kill_switch

    def allow_trade(self) -> bool:
        if not self.enabled:
            return True
        if not self.plan_ready():
            return False
        return not self.kill_switch and self.active

    def status(self) -> Dict[str, Any]:
        return {
            "enabled": self.enabled,
            "active": self.active,
            "pairs_enabled": self.pairs_enabled,
            "market_making_enabled": self.market_making_enabled,
            "paper_mode": self.paper_mode,
            "kill_switch": self.kill_switch,
            "max_latency_ms": self.max_latency_ms,
            "plan_ready": self.plan_ready(),
            "risk_plan": dict(self.risk_plan),
            "primary_asset": self.primary_asset,
            "secondary_asset": self.secondary_asset,
            "primary_window": self.primary_window,
            "secondary_window": self.secondary_window,
            "paper_mode": self.paper_mode,
            "paper": self.paper_book.status(),
            "report_confluences": self.report_confluences,
        }


def time_now() -> float:
    import time

    return time.time()
