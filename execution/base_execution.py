from abc import ABC, abstractmethod


class BaseExecution(ABC):

    @abstractmethod
    def place_order(
        self,
        symbol: str,
        direction: str,
        order_type: str,
        entry_price: float,
        lot_size: float,
        sl: float,
        tp: float,
        strategy_name: str,
    ) -> int:
        """Place an order. Returns ticket ID (> 0) on success, 0 on failure."""
        ...

    @abstractmethod
    def close_order(self, ticket_id: int) -> bool:
        """Close an open order by ticket ID."""
        ...

    @abstractmethod
    def get_open_positions(self) -> list[dict]:
        """Return a list of open position dicts."""
        ...

    @abstractmethod
    def get_account_balance(self) -> float:
        """Return the current account balance in account currency."""
        ...
