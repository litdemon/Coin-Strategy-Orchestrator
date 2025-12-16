class Emoji:
    """
    Standardized Emojis for Logging and UI.
    """
    # Basic Level
    INFO = "ℹ️"
    WARN = "⚠️"
    ERROR = "❌"
    FATAL = "🚨"
    DEBUG = "🐞"

    # System / Process
    START = "🚀"
    STOP = "🛑"
    RETRY = "🔄"
    INIT = "⚙️"
    LOAD = "🧩"
    CLEAN = "🧹"

    # Trade Flow
    BUY = "🟢"
    SELL = "🔴"
    ORDER = "🧾"
    FILL = "�"
    PENDING = "⏳"
    CANCEL = "❌"
    WAIT = "🔄"
    DONE = "✅"

    # Price / Market Event
    PRICE_UP = "📈"
    PRICE_DOWN = "�📉"
    TICK = "📊"
    VOLATILE = "⚡"

    # Asset / Account
    BALANCE = "🪙"
    PROFIT = "💰"
    LOSS = "💸"
    ACCOUNT = "🏦"
    WALLET = "🔒"

    # Auto Trading / Strategy
    BOT = "🤖"
    STRATEGY = "🧠"
    TARGET = "🎯"
    TRAILING = "🪜"
    STOP_LOSS = "🧯"

    # Network / External
    API = "🌐"
    MQTT = "📡"
    CONNECT = "🔌"
    DISCONNECT = "🔌❌"
    TIMEOUT = "⏱️"

    @classmethod
    def get(cls, key: str) -> str:
        """
        Get emoji by name (case-insensitive).
        Example: Emoji.get('buy') -> '🟢'
        """
        return getattr(cls, key.upper(), "")