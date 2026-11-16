"""
NSE symbol to Yahoo Finance ticker mapper and vice versa.
Handles special characters like '&', '-', and explicit edge cases.
"""

from typing import Dict

# Explicit mapping for symbols requiring custom conversion
NSE_TO_YAHOO_SPECIAL: Dict[str, str] = {
    "M&M": "M&M.NS",
    "BAJAJ-AUTO": "BAJAJ-AUTO.NS",
    "MCDOWELL-N": "MCDOWELL-N.NS",
    "L&TFH": "L&TFH.NS",
    "NAM-INDIA": "NAM-INDIA.NS",
    "TATAMOTORS": "TATAMOTORS.NS",
    "LTIM": "LTIM.NS",
}

YAHOO_TO_NSE_SPECIAL: Dict[str, str] = {
    v: k for k, v in NSE_TO_YAHOO_SPECIAL.items()
}


def nse_to_yahoo_ticker(symbol: str) -> str:
    """
    Convert an NSE equity symbol to its corresponding Yahoo Finance ticker.
    Examples:
        RELIANCE -> RELIANCE.NS
        M&M -> M&M.NS
        BAJAJ-AUTO -> BAJAJ-AUTO.NS
    """
    clean_sym = symbol.strip().upper()
    if clean_sym in NSE_TO_YAHOO_SPECIAL:
        return NSE_TO_YAHOO_SPECIAL[clean_sym]
    
    # Standard format for Indian stocks on Yahoo Finance
    return f"{clean_sym}.NS"


def yahoo_to_nse_symbol(ticker: str) -> str:
    """
    Convert a Yahoo Finance ticker back to an NSE equity symbol.
    """
    clean_ticker = ticker.strip().upper()
    if clean_ticker in YAHOO_TO_NSE_SPECIAL:
        return YAHOO_TO_NSE_SPECIAL[clean_ticker]
    
    if clean_ticker.endswith(".NS"):
        return clean_ticker[:-3]
    return clean_ticker
