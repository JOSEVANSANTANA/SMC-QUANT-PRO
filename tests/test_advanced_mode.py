import unittest

import math
import unittest

from advanced_mode import (
    AdvancedModeController,
    DirectionalMarketMaker,
    PairTradeEngine,
    PaperExecutionBook,
    PaperIntent,
    PaperLegIntent,
    allocate_pair_risk,
)
from news_trading import BookSnapshot


class AdvancedModeControllerTests(unittest.TestCase):
    def test_default_disabled_mode_keeps_system_safe(self):
        controller = AdvancedModeController(enabled=False)
        self.assertFalse(controller.enabled)
        self.assertTrue(controller.allow_trade())

    def test_kill_switch_blocks_trade_when_latency_exceeds_limit(self):
        controller = AdvancedModeController(enabled=True, max_latency_ms=150, risk_plan={"margem": 1000, "risco_pct": 1.0, "drawdown_maximo": 100})
        controller.observe_latency(180)
        self.assertTrue(controller.kill_switch)
        self.assertFalse(controller.allow_trade())

    def test_pairs_and_market_making_can_be_toggled_independently(self):
        controller = AdvancedModeController(enabled=True, risk_plan={"margem": 1000, "risco_pct": 1.0, "drawdown_maximo": 100})
        self.assertTrue(controller.pairs_enabled)
        self.assertTrue(controller.market_making_enabled)
        controller.set_strategy_flags(pairs=False, market_making=False)
        self.assertFalse(controller.pairs_enabled)
        self.assertFalse(controller.market_making_enabled)

    def test_mode_only_activates_with_valid_risk_plan(self):
        controller = AdvancedModeController(enabled=True, risk_plan={"margem": 0, "risco_pct": 0, "drawdown_maximo": 0})
        self.assertFalse(controller.plan_ready())
        self.assertFalse(controller.allow_trade())

    def test_pairs_needs_synchronized_history_and_detects_a_spread_deviation_once(self):
        engine = PairTradeEngine(zscore_threshold=1.5, min_observations=20,
                                 max_sample_skew_seconds=3, min_return_correlation=0.5,
                                 lookback=60)
        for index in range(200):
            secondary = 100.0 * math.exp(index * 0.0005 + 0.01 * math.sin(index * 0.37)
                                         + 0.001 * math.sin(index * 0.13))
            primary = 50.0 * math.exp(
                index * 0.0005 + 0.012 * math.sin(index * 0.37)
                + 0.0012 * math.sin(index * 0.13))
            engine.observe_price("MESU6", primary, timestamp=1000 + index)
            engine.observe_price("MNQU6", secondary, timestamp=1001 + index)
        engine.observe_price(
            "MESU6", 50.0 * math.exp(0.1 + 0.012 * math.sin(200 * 0.37)
                                      + 0.0012 * math.sin(200 * 0.13) + 0.008),
            timestamp=1200)
        engine.observe_price(
            "MNQU6", 100.0 * math.exp(0.1 + 0.01 * math.sin(200 * 0.37)
                                       + 0.001 * math.sin(200 * 0.13)),
            timestamp=1201)

        candidate = engine.evaluate_assets("MES", "MNQ", now=1201)
        self.assertIsNotNone(candidate)
        self.assertEqual(candidate["strategy"], "PAIRS_PAPER")
        self.assertGreaterEqual(candidate["observations"], 20)
        self.assertEqual((candidate["primary_side"], candidate["secondary_side"]),
                         ("SELL", "BUY"))
        self.assertIsNone(engine.evaluate_assets("MES", "MNQ", now=1201))

    def test_pairs_rejects_stale_or_unsynchronized_samples(self):
        engine = PairTradeEngine(min_observations=10, max_sample_skew_seconds=2)
        for index in range(12):
            engine.observe_price("MESU6", 5000 + index, timestamp=index)
            engine.observe_price("MNQU6", 18000 + index, timestamp=index + 10)
        self.assertIsNone(engine.evaluate_assets("MES", "MNQ", now=30))

        for index in range(12):
            engine.observe_price("MESU6", 5100 + index, timestamp=100 + index)
            engine.observe_price("MNQU6", 18100 + index, timestamp=100 + index)
        self.assertIsNone(engine.evaluate_assets("MES", "MNQ", now=1000))

    def test_market_maker_paper_candidate_requires_fresh_book_flow_and_imbalance(self):
        maker = DirectionalMarketMaker()
        book = BookSnapshot(((99.75, 8), (99.5, 5)), ((100.0, 2), (100.25, 1)), 1000)
        candidate = maker.evaluate_book(
            price=99.75, support=99.75, resistance=101.0, order_flow_bias=1,
            book=book, tick_size=0.25, min_depth=1, max_spread_ticks=2,
            level_distance_ticks=2, imbalance_threshold=1.25, now=1000)
        self.assertEqual(candidate["side"], "BUY")
        self.assertEqual(candidate["entry"], 99.75)
        self.assertIsNone(maker.evaluate_book(
            price=99.75, support=99.75, resistance=101.0, order_flow_bias=1,
            book=None, tick_size=0.25))
        stale = BookSnapshot(book.bids, book.asks, 1)
        self.assertIsNone(maker.evaluate_book(
            price=99.75, support=99.75, resistance=101.0, order_flow_bias=1,
            book=stale, tick_size=0.25, now=1000))

    def test_paper_book_enforces_aggregate_risk_and_simulates_two_legs_atomically(self):
        paper = PaperExecutionBook(slippage_ticks=0, max_pair_skew_seconds=2)
        intent = PaperIntent(
            intent_id="pair-1", strategy="PAIRS_PAPER",
            legs=(
                PaperLegIntent("MESU6", "BUY", 100, 99, 102, 1, 5, 0.25),
                PaperLegIntent("MNQU6", "SELL", 200, 202, 196, 1, 2, 0.25),
            ), reason="spread convergente", created_at=1000,
            metadata={"entry_zscore": 2.5, "target_zscore": 0.25, "stop_zscore": 3.5})
        self.assertEqual(intent.planned_risk_usd, 9)
        self.assertEqual(paper.submit(intent, max_total_risk_usd=10),
                         (True, "paper trade aberto sob o orçamento de risco"))
        blocked = PaperIntent(
            intent_id="pair-2", strategy="PAIRS_PAPER", legs=intent.legs,
            reason="another pair", created_at=1000)
        self.assertFalse(paper.submit(blocked, max_total_risk_usd=10)[0])
        self.assertEqual(paper.mark_prices({"MESU6": 100}, timestamp=1001), [])
        self.assertEqual(paper.mark_prices({"MESU6": 100, "MNQU6": 200}, timestamp=1001), [])
        closed = paper.mark_pair_zscore("MES", "MNQ", 0.1, timestamp=1001)
        self.assertEqual(len(closed), 1)
        self.assertEqual(closed[0].status, "CLOSED")
        self.assertEqual(closed[0].exit_reason, "PAIR_MEAN")

    def test_paper_passive_fill_and_trailing_stop(self):
        paper = PaperExecutionBook(slippage_ticks=1)
        intent = PaperIntent(
            intent_id="mm-1", strategy="MM_PAPER",
            legs=(PaperLegIntent("MESU6", "BUY", 100, 99, 110, 1, 5, 0.25,
                                 trailing={"stop": 4, "acionar": 4}),),
            reason="liquidity wall", created_at=1000, entry_mode="PASSIVE")
        self.assertTrue(paper.submit(intent, max_total_risk_usd=10)[0])
        self.assertEqual(paper.status()["pending"], 1)
        self.assertEqual(paper.status()["open_risk_usd"], 6.25)
        self.assertEqual(paper.mark_prices({"MESU6": 99.9}, timestamp=1001), [])
        self.assertEqual(paper.status()["open"], 0)
        self.assertEqual(paper.mark_prices({"MESU6": 99.5}, timestamp=1002), [])
        self.assertEqual(paper.status()["open"], 1)
        paper.mark_prices({"MESU6": 101.0}, timestamp=1003)
        trade = paper.trades[0]
        self.assertTrue(trade.trailing_armed[0])
        closed = paper.mark_prices({"MESU6": 100.0}, timestamp=1004)
        self.assertEqual(len(closed), 1)
        self.assertEqual(closed[0].exit_reason, "STOP")

    def test_pair_risk_allocator_respects_notional_beta_and_slippage_cap(self):
        args = dict(
            beta=1.2, primary_entry=5000, primary_stop=4998,
            primary_point_value=5, primary_tick_size=0.25,
            secondary_entry=18000, secondary_stop=18010,
            secondary_point_value=2, secondary_tick_size=0.25,
            slippage_ticks=1)
        allocation = allocate_pair_risk(max_risk_usd=100, **args)
        self.assertEqual(allocation["primary_quantity"], 2)
        self.assertEqual(allocation["secondary_quantity"], 2)
        self.assertLessEqual(allocation["reserved_risk_usd"], 100)
        self.assertEqual(allocation["slippage_reserve_usd"], 7)
        self.assertIsNone(allocate_pair_risk(max_risk_usd=30, **args))

    def test_pair_risk_allocator_refuses_unrepresentable_contract_hedge(self):
        allocation = allocate_pair_risk(
            max_risk_usd=1000, beta=0.1,
            primary_entry=5000, primary_stop=4998,
            primary_point_value=5, primary_tick_size=0.25,
            secondary_entry=18000, secondary_stop=18010,
            secondary_point_value=2, secondary_tick_size=0.25)
        self.assertIsNone(allocation)

    def test_paper_quotes_expire_and_reentry_is_cooled_down(self):
        paper = PaperExecutionBook(slippage_ticks=0, pending_ttl_seconds=5,
                                   reentry_cooldown_seconds=30)
        leg = PaperLegIntent("MESU6", "BUY", 100, 99, 102, 1, 5, 0.25)
        first = PaperIntent("quote-1", "MM_PAPER", (leg,), "support", 100,
                            entry_mode="PASSIVE")
        self.assertTrue(paper.submit(first, 10)[0])
        second = PaperIntent("quote-2", "MM_PAPER", (leg,), "support", 110,
                             entry_mode="PASSIVE")
        self.assertIn("cooldown", paper.submit(second, 10)[1])
        paper.mark_prices({}, timestamp=106)
        self.assertEqual(paper.status()["pending"], 0)
        self.assertEqual(paper.status()["cancelled"], 1)
        self.assertEqual(paper.status()["open_risk_usd"], 0)
        third = PaperIntent("quote-3", "MM_PAPER", (leg,), "support", 131,
                            entry_mode="PASSIVE")
        self.assertTrue(paper.submit(third, 10)[0])


if __name__ == "__main__":
    unittest.main()
