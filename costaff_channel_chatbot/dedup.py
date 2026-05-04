"""Bounded message-id dedup. The set self-clears once it grows past the limit."""


class MessageDedup:
    def __init__(self, max_size: int = 2000) -> None:
        self.max_size = max_size
        self._seen: set[str] = set()

    def seen(self, message_id: str) -> bool:
        if message_id in self._seen:
            return True
        self._seen.add(message_id)
        if len(self._seen) > self.max_size:
            self._seen.clear()
        return False
