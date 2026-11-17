import asyncio
import datetime as dt
import json
import threading
import unittest
from zoneinfo import ZoneInfo

from advanced_mode import AdvancedModeController
from news_trading import (
    BookSnapshot,
    EconomicRelease,
    LiquidityGuard,
    MacroSMCAnalyzer,
    NewsMonitor,
    macro_bias_for_us_index,
    order_flow_side_from_confluences,
    parse_calendar_xml,
    read_book_snapshot_cdp,
)


class NewsTradingTests(unittest.TestCase):
    def release(self, event="CPI y/y", actual=3.4, forecast=3.2, currency="USD", now=1000):
        return EconomicRelease(event, currency, "High", actual, forecast, None, now, "fixture")

    def test_calendar_parser_requires_high_impact_actual_and_forecast(self):
        xml = """<weeklyevents>
          <event><title>CPI y/y</title><country>USD</country><date>09-30-2026</date><time>8:30am</time><impact>High</impact>
            <actual>3.4%</actual><forecast>3.2%</forecast><previous>3.1%</previous></event>
          <event><title>Retail Sales</title><country>USD</country><date>09-30-2026</date><time>8:30am</time><impact>High</impact>
            <actual>1.0%</actual></event>
          <event><title>Low impact</title><country>USD</country><date>09-30-2026</date><time>8:30am</time><impact>Low</impact>
            <actual>1</actual><forecast>2</forecast></event>
        </weeklyevents>"""
        releases = parse_calendar_xml(xml, source="fixture", now=500)
        self.assertEqual(len(releases), 1)
        self.assertEqual((releases[0].actual, releases[0].forecast), (3.4, 3.2))
        expected_time = dt.datetime(2026, 9, 30, 8, 30,
                                    tzinfo=ZoneInfo("America/New_York")).timestamp()
        self.assertEqual(releases[0].published_at, expected_time)

    def test_release_without_publication_or_scheduled_timestamp_is_ignored(self):
        xml = """<events><event><title>CPI y/y</title><country>USD</country>
          <impact>High</impact><actual>3.4</actual><forecast>3.2</forecast></event></events>"""
        self.assertEqual(parse_calendar_xml(xml, now=1000), [])

    def test_inflation_bias_is_directional_but_ambiguous_events_are_not(self):
        self.assertEqual(macro_bias_for_us_index(self.release()), "SELL")
        self.assertEqual(macro_bias_for_us_index(self.release(actual=3.0, forecast=3.2)), "BUY")
        self.assertIsNone(macro_bias_for_us_index(self.release(event="Nonfarm Payrolls")))
        self.assertIsNone(macro_bias_for_us_index(self.release(currency="EUR")))

    def test_order_flow_requires_explicit_unambiguous_direction(self):
        self.assertEqual(order_flow_side_from_confluences(["Order Flow: CVD comprador"]), "BUY")
        self.assertEqual(order_flow_side_from_confluences(["Absorção vendedora no topo"]), "SELL")
        self.assertIsNone(order_flow_side_from_confluences(["Order Flow presente"]))
        self.assertIsNone(order_flow_side_from_confluences([
            "CVD comprador", "Delta vendedor"
        ]))

    def test_advanced_secondary_is_validation_only_when_mode_is_enabled(self):
        controller = AdvancedModeController(
            enabled=True, secondary_asset="MNQU6", secondary_window="Chrome - MNQ")
        self.assertTrue(controller.is_secondary_validation_only(asset="MNQZ6"))
        self.assertTrue(controller.is_secondary_validation_only(window="chrome - mnq"))
        self.assertFalse(controller.is_secondary_validation_only(
            asset="MNQU6", window="Chrome - MES primary"))
        self.assertFalse(controller.is_secondary_validation_only(asset="MESU6"))
        controller.enabled = False
        self.assertFalse(controller.is_secondary_validation_only(asset="MNQZ6"))

    def test_liquidity_guard_uses_spread_depth_and_adjusted_rr(self):
        guard = LiquidityGuard(max_spread_ticks=2, min_risk_reward=1.2)
        good = BookSnapshot(((99.75, 5), (99.5, 5)), ((100, 5), (100.25, 5)), 1000)
        result = guard.assess(good, "BUY", 100, 99, 102, 1, 0.25, now=1000)
        self.assertTrue(result.allowed)
        self.assertAlmostEqual(result.spread_ticks, 1)
        self.assertGreaterEqual(result.risk_reward_after_costs, 1.2)

        wide = BookSnapshot(((99.25, 5),), ((100, 5),), 1000)
        self.assertFalse(guard.assess(wide, "BUY", 100, 99, 102, 1, 0.25, now=1000).allowed)
        thin = BookSnapshot(((99.75, 0.5),), ((100, 0.5),), 1000)
        self.assertIn("profundidade", guard.assess(
            thin, "BUY", 100, 99, 102, 1, 0.25, now=1000).reason)
        self.assertFalse(guard.assess(None, "BUY", 100, 99, 102, 1, 0.25, now=1000).allowed)

    def test_macro_smc_gate_requires_all_confluences_and_liquidity(self):
        analyzer = MacroSMCAnalyzer()
        release = self.release(now=1000)
        book = BookSnapshot(((99.75, 5),), ((100, 5),), 1000)
        args = dict(release=release, side="SELL", technical_side="SELL",
                    smc_trigger=True, order_flow_side="SELL", book=book,
                    entry=100, stop=101, target=98, quantity=1,
                    tick_size=0.25, now=1000)
        self.assertTrue(analyzer.evaluate(**args).allowed)
        self.assertFalse(analyzer.evaluate(**{**args, "side": "BUY"}).allowed)
        self.assertFalse(analyzer.evaluate(**{**args, "order_flow_side": None}).allowed)
        self.assertFalse(analyzer.evaluate(**{**args, "book": None}).allowed)

    def test_unknown_dom_layout_is_not_mistaken_for_book_depth(self):
        class Bot:
            def avaliar_js(self, _script):
                return json.dumps({"ok": False, "reason": "unknown"})

        self.assertIsNone(read_book_snapshot_cdp(Bot()))

    def test_cdp_reader_accepts_semantic_depth_levels(self):
        class Bot:
            def avaliar_js(self, _script):
                return json.dumps({
                    "ok": True,
                    "observed_at": 1000,
                    "bids": [[99.75, 4]],
                    "asks": [[100, 5]],
                })

        snapshot = read_book_snapshot_cdp(Bot())
        self.assertEqual(snapshot.bids, ((99.75, 4.0),))
        self.assertEqual(snapshot.asks, ((100.0, 5.0),))

    def test_monitor_polls_asynchronously_and_deduplicates_releases(self):
        xml = """<events><event><title>CPI y/y</title><country>USD</country><date>01-01-1970</date><time>8:30am</time>
          <impact>High</impact><actual>3.4</actual><forecast>3.2</forecast></event></events>"""
        monitor = NewsMonitor(feeds=(("fixture", "memory://calendar"),),
                              fetcher=lambda _url: xml)

        async def check():
            first = await monitor.poll_once(now=1000)
            second = await monitor.poll_once(now=1001)
            return first, second

        first, second = asyncio.run(check())
        self.assertEqual(len(first), 1)
        self.assertEqual(second, [])
        self.assertEqual(monitor.status()["last_success_at"], 1001)

    def test_monitor_toggle_and_shutdown_do_not_require_network(self):
        xml = """<events><event><title>CPI y/y</title><country>USD</country><date>01-01-1970</date><time>8:30am</time>
          <impact>High</impact><actual>3.4</actual><forecast>3.2</forecast></event></events>"""
        received = threading.Event()
        monitor = NewsMonitor(feeds=(("fixture", "memory://calendar"),),
                              on_release=lambda _release: received.set(),
                              fetcher=lambda _url: xml)
        monitor.start()
        try:
            self.assertTrue(received.wait(timeout=2))
            monitor.stop()
            self.assertFalse(monitor.status()["enabled"])
        finally:
            monitor.close()
            if monitor._thread:
                monitor._thread.join(timeout=1)
        self.assertFalse(monitor.status()["running"])


if __name__ == "__main__":
    unittest.main()
