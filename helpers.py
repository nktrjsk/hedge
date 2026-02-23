# helpers.py
# Pomocné funkce pro extension

def sats_to_usd(sats: int, price: float) -> float:
    """Převede satoshi na USD."""
    return sats / 100_000_000 * price


def usd_to_sats(usd: float, price: float) -> int:
    """Převede USD na satoshi."""
    return int(usd / price * 100_000_000)
