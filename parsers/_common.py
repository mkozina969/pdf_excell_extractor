
import re
from typing import Optional, Dict, List

EU_NUM = r"(?:\d{1,3}(?:\.\d{3})*|\d+)(?:,\d+)?"

EU_RE = re.compile(rf"^{EU_NUM}$")
UOM_RE = re.compile(r"^[A-Za-zČĆŽŠĐ]{1,8}$")
INT_RE = re.compile(r"^\d{1,4}$")

def parse_eu_number(s: Optional[str]) -> Optional[float]:
    """
    Parse European number format (1.234,56) to float.
    
    Args:
        s: String representation of number in European format
        
    Returns:
        Float value or None if parsing fails
    """
    if s is None:
        return None
    s = str(s).strip()
    if not s:
        return None
    s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except (ValueError, TypeError):
        return None

def grab(pattern: str, text: str, flags=0, idx: int = 0):
    """
    Extract text using regex pattern.
    
    Args:
        pattern: Regular expression pattern
        text: Text to search in
        flags: Regex flags (default: 0)
        idx: Index of match to return (default: 0)
        
    Returns:
        Matched text or None if no match found
    """
    m = re.findall(pattern, text, flags)
    if m:
        if isinstance(m[0], tuple):
            return m[idx][0]
        return m[idx]
    return None

def to_erp_item(item: Dict) -> Dict:
    """
    Convert parsed item data to ERP format.
    
    Args:
        item: Dictionary containing item data
        
    Returns:
        Dictionary with standardized ERP fields
    """
    return {
        "Item": item.get("Item"),
        "Qty": item.get("Qty"),
        "UoM": item.get("UoM"),
        "Unit Price": item.get("Unit Price"),
        "Amount": item.get("Amount"),
        "VAT": item.get("VAT"),
    }
