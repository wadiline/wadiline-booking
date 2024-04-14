"""At the service boundary, show and read whole piastres as EGP."""
import re


def format_egp(piastres: int) -> str:
    if piastres < 0:
        raise ValueError("An amount cannot be negative.")
    pounds, rest = divmod(piastres, 100)
    return f"{pounds}.{rest:02d} EGP" if rest else f"{pounds} EGP"


def parse_egp(text: str) -> int:
    match = re.fullmatch(r"([0-9]+)(?:\.([0-9]{1,2}))?(?: EGP)?", text)
    if match is None:
        raise ValueError("Enter an EGP amount with up to two decimal places.")
    whole, fraction = match.groups()
    return int(whole) * 100 + int((fraction or "").ljust(2, "0"))
