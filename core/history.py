from collections import deque
import time


class MarketHistory:

    def __init__(self, max_history=10):
        self.history = {}
        self.max_history = max_history

    def update(self, key, odd):

        if key not in self.history:
            self.history[key] = deque(maxlen=self.max_history)

        self.history[key].append({
            "timestamp": time.time(),
            "odd": odd
        })

        return list(self.history[key])

    def get(self, key):
        return list(self.history.get(key, []))

    def clear(self):
        self.history.clear()