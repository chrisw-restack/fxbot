"""Failed2 market acceptance, recovery, and startup-history regressions."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from audit_failed2_logic import bars, prepared as audit_prepared
from backtest_engine import BacktestEngine
from models import BarEvent
from strategies.failed2 import Failed2Strategy
from utils.setup_ledger import SetupLedger
from utils.strategy_state import StrategyCheckpoint
from utils.warmup import warmup_counts
from test_review_regressions import fake_broker


def prepared():
    s = audit_prepared()
    s._d1_ema_count['USTEC'] = 61
    return s


def record(signal, ticket=123):
    return dict(symbol=signal.symbol, direction=signal.direction,
        strategy_name=signal.strategy_name, setup_id=signal.setup_id,
        attempt_id=signal.attempt_id, ticket=ticket, state='OPEN')


class Failed2TrackingTests(unittest.TestCase):
    def test_market_submission_persists_identity_before_broker_send(self):
        s = prepared()
        signal = s.generate_signal(bars()[-1])
        with TemporaryDirectory() as tmp, fake_broker() as (broker, execution_class, _):
            ledger = SetupLedger(Path(tmp)/'ledger.json', {'login':123})
            execution = execution_class({s.NAME:1010}, setup_ledger=ledger)
            broker.symbol_info_tick.return_value = SimpleNamespace(bid=112, ask=113)
            broker.order_calc_profit.side_effect = lambda direction, symbol, volume, entry, sl: -abs(entry-sl)*volume
            def send(request):
                self.assertEqual(ledger.pending_intents()[request['comment']]['setup_id'], signal.setup_id)
                return SimpleNamespace(retcode=10009, order=123, price=113, deal=456)
            broker.order_send.side_effect = send
            ticket=execution.place_order(symbol='USTEC', direction='BUY', order_type='MARKET',
                entry_price=112, lot_size=1, sl=95, tp=180, strategy_name=s.NAME,
                entry_timeframe='M5', tp_locked=True, risk_budget=50,
                setup_id=signal.setup_id, attempt_id=signal.attempt_id)
            self.assertEqual(ticket,123)
            self.assertFalse(ledger.pending_intents())
            cold=prepared()
            cold.sync_order_state(SetupLedger(ledger.path, {'login':123}).orders['123'])
            self.assertIsNone(cold.generate_signal(bars()[-1]))

    def test_fvg_keeps_legacy_occupied_slot_rejection_behavior(self):
        s = Failed2Strategy(entry_mode='fvg')
        self.assertIsNone(s.notify_proposal_rejected)

    def test_occupied_rejection_does_not_consume_new_setup(self):
        s = prepared()
        e = BacktestEngine()
        e.add_strategy(s, ['USTEC'])
        e.portfolio.record_existing('USTEC', s.NAME, 999)
        signal = s.generate_signal(bars()[-1])
        e.event_engine.reject_signal(signal)
        self.assertFalse(s._consumed_market_setups)
        self.assertFalse(s._market_proposals)
        self.assertIsNotNone(s.generate_signal(bars()[-1]))

    def test_accept_close_and_new_h4_do_not_release_original_setup(self):
        s = prepared()
        signal = s.generate_signal(bars()[-1])
        s.notify_order_accepted(signal, 123)
        s.notify_trade_closed(dict(record(signal), result='LOSS'))
        s._clear_bias('USTEC')
        replacement = prepared()
        s._bias['USTEC'] = replacement._bias['USTEC']
        s._itf_setup['USTEC'] = replacement._itf_setup['USTEC']
        s._entry_bars['USTEC'] = replacement._entry_bars['USTEC']
        self.assertIsNone(s.generate_signal(bars()[-1]))

    def test_late_rejection_cannot_release_accepted_setup(self):
        s = prepared()
        signal = s.generate_signal(bars()[-1])
        s.notify_order_accepted(signal, 123)
        s.notify_proposal_rejected(signal)
        s.notify_signal_rejected('USTEC')
        self.assertIn(signal.setup_id, s._consumed_market_setups)

    def test_unfilled_market_fill_rejection_releases_only_that_attempt(self):
        s = prepared()
        signal = s.generate_signal(bars()[-1])
        s.notify_order_accepted(signal, 123)
        s._consumed_market_setups.add('another setup')
        s.notify_proposal_rejected(SimpleNamespace(**record(signal)))
        self.assertNotIn(signal.setup_id, s._consumed_market_setups)
        self.assertIn('another setup', s._consumed_market_setups)
        self.assertIsNotNone(s.generate_signal(bars()[-1]))

    def test_ledger_closed_trade_recovers_consumption_without_checkpoint(self):
        s = prepared()
        signal = s.generate_signal(bars()[-1])
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / 'ledger.json'
            ledger = SetupLedger(path, {'login': 123})
            row = record(signal)
            ledger.accept(row.pop('ticket'), **row)
            ledger.close(dict(record(signal), close_time=datetime(2024, 1, 8, 16), result='WIN'))
            cold = prepared()
            engine = BacktestEngine()
            engine.add_strategy(cold, ['USTEC'])
            for trade in SetupLedger(path, {'login': 123}).closed_trades():
                engine.event_engine.notify_trade_closed(trade)
            self.assertIsNone(cold.generate_signal(bars()[-1]))

    def test_open_order_recovery_is_idempotent_and_rejects_bad_attribution(self):
        s = prepared()
        signal = s.generate_signal(bars()[-1])
        cold = prepared()
        for row in (dict(record(signal), symbol='EURUSD'),
                    dict(record(signal), direction='SELL'),
                    dict(record(signal), strategy_name='other'),
                    dict(record(signal), setup_id=None)):
            cold.sync_order_state(row)
        self.assertFalse(cold._consumed_market_setups)
        cold.sync_order_state(record(signal))
        cold.sync_order_state(record(signal))
        self.assertEqual(cold._consumed_market_setups, {signal.setup_id})

    def test_new_h1_setup_is_available_after_previous_trade(self):
        s = prepared()
        signal = s.generate_signal(bars()[-1])
        s.notify_order_accepted(signal, 123)
        s._itf_setup['USTEC']['timestamp'] += timedelta(hours=1)
        s._itf_setup['USTEC']['close_time'] += timedelta(hours=1)
        next_bar = deepcopy(bars()[-1])
        next_bar.timestamp += timedelta(hours=1)
        signal2 = s.generate_signal(next_bar)
        self.assertIsNotNone(signal2)
        self.assertNotEqual(signal.setup_id, signal2.setup_id)

    def test_setup_identity_is_utc_normalized_and_survives_checkpoint(self):
        s = prepared()
        signal = s.generate_signal(bars()[-1])
        setup = deepcopy(s._itf_setup['USTEC'])
        setup['timestamp'] = setup['timestamp'].replace(tzinfo=timezone.utc).astimezone(timezone(timedelta(hours=2)))
        self.assertEqual(signal.setup_id, s._market_setup_id('USTEC', setup))
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / 'state.json'
            source = prepared()
            checkpoint = StrategyCheckpoint(path, [(source, ['USTEC'])], {})
            source.sync_order_state(record(signal))
            checkpoint.save({('USTEC', 'M5'): bars()[-1].timestamp})
            cold = prepared()
            self.assertIsNotNone(StrategyCheckpoint(path, [(cold, ['USTEC'])], {}).load())
            self.assertIsNone(cold.generate_signal(bars()[-1]))

    def test_next_bar_gap_rejection_can_retry_through_engine(self):
        s = prepared()
        e = BacktestEngine(spread_pips=1)
        e.add_strategy(s, ['USTEC'])
        e.process_bar(bars()[-1])
        attempt = next(iter(s._accepted_market_attempts))
        self.assertTrue(s._consumed_market_setups)
        # A quote above the locked target rejects this unfilled queued order.
        e.process_bar(BarEvent('USTEC', 'M5', datetime(2024,1,8,13,5), 190,191,189,190,1))
        self.assertNotIn(attempt, s._accepted_market_attempts)
        original = s._market_setup_id('USTEC', s._itf_setup['USTEC'])
        # A fresh proposal can be emitted on that bar; only accepted orders consume it.
        if not e.execution.get_open_positions():
            self.assertNotIn(original, s._consumed_market_setups)
        self.assertFalse(e.execution._positions)


class Failed2WarmupTests(unittest.TestCase):
    def test_full_range_history_is_required_even_if_partial_rank_allows(self):
        s = prepared()
        s._d1_ema_count['USTEC'] = 50
        self.assertFalse(s._passes_entry_filters('USTEC', 'BUY'))
        s._d1_ema_count['USTEC'] = 61
        self.assertTrue(s._passes_entry_filters('USTEC', 'BUY'))

    def test_requirements_are_per_pair_and_cover_range_and_ema(self):
        s = prepared()
        plain = Failed2Strategy(name='plain')
        counts = warmup_counts([(s, ['USTEC']), (plain, ['EURUSD'])])
        self.assertEqual(counts['USTEC', 'D1'], 250)
        self.assertEqual(counts['EURUSD', 'H4'], 100)
        self.assertNotIn(('EURUSD', 'D1'), counts)
        s.d1_range_lookback = 300
        self.assertEqual(warmup_counts([(s, ['USTEC'])])['USTEC', 'D1'], 301)

    def test_range_filter_blocks_reproduced_july_threshold(self):
        ranges = [1]*42 + [100]*18 + [2]
        s = prepared()
        s.reset()
        for i, value in enumerate(ranges):
            s.generate_signal(BarEvent('USTEC', 'D1', datetime(2023,1,1)+timedelta(days=i),
                100,100+value/2,100-value/2,100,1))
        self.assertEqual(s._d1_range_percentile['USTEC'], .7)
        self.assertFalse(s._passes_entry_filters('USTEC', 'BUY'))


if __name__ == '__main__':
    unittest.main()
