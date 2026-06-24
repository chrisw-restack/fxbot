"""Inspect or cancel specific bot-owned MT5 pending orders.

Run this on the Windows/VPS machine where MetaTrader 5 is installed. The
default mode is read-only; pass --execute to submit cancellation requests.
"""

import argparse
import os

import MetaTrader5 as mt5
from dotenv import load_dotenv

import config
from data.mt5_data import connect, disconnect
from execution.mt5_execution import MT5Execution


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Inspect or cancel specific bot-owned MT5 pending orders."
    )
    parser.add_argument('tickets', nargs='+', type=int, help='MT5 pending-order ticket IDs')
    parser.add_argument(
        '--execute',
        action='store_true',
        help='Actually cancel matching orders. Without this flag the command is read-only.',
    )
    args = parser.parse_args()

    load_dotenv()
    required = ['MT5_LOGIN', 'MT5_PASSWORD', 'MT5_SERVER']
    missing = [name for name in required if not os.environ.get(name)]
    if missing:
        raise SystemExit(f"Missing required environment variables: {', '.join(missing)}")

    if not connect(
        int(os.environ['MT5_LOGIN']),
        os.environ['MT5_PASSWORD'],
        os.environ['MT5_SERVER'],
    ):
        return 1

    execution = MT5Execution(magic_numbers=config.MAGIC_NUMBERS)
    known_magic = set(config.MAGIC_NUMBERS.values())
    failed = False
    try:
        for ticket in args.tickets:
            orders = mt5.orders_get(ticket=ticket)
            if orders is None:
                print(f"{ticket}: MT5 lookup failed — {mt5.last_error()}")
                failed = True
                continue
            if not orders:
                print(f"{ticket}: not an active pending order")
                continue

            order = orders[0]
            if order.magic not in known_magic:
                print(
                    f"{ticket}: REFUSED — magic {order.magic} is not owned by this bot"
                )
                failed = True
                continue

            strategy_name = execution.strategy_name_for_magic(
                order.magic,
                order.comment,
            )
            print(
                f"{ticket}: {order.symbol} {strategy_name} "
                f"volume={order.volume_current} price={order.price_open}"
            )
            if not args.execute:
                print(f"{ticket}: dry run — no cancellation submitted")
                continue

            if execution.close_order(ticket):
                print(f"{ticket}: cancellation confirmed")
            else:
                print(
                    f"{ticket}: CANCELLATION FAILED — "
                    f"{execution.get_last_cancel_error()}"
                )
                failed = True
    finally:
        disconnect()

    return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main())
