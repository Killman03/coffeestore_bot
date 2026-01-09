from decimal import Decimal, InvalidOperation
import re
from typing import Optional, Tuple, List


def parse_arrival_message(text: str) -> Tuple[List[str], Optional[Decimal], Optional[Decimal]]:
    """Parse delivery arrival message and extract tracking numbers, total weight, and total cost.

    Returns a tuple: (tracking_numbers, total_weight, total_cost)
    """
    tracking_numbers: List[str] = []
    total_weight: Optional[Decimal] = None
    total_cost: Optional[Decimal] = None

    lines = [line.strip() for line in text.splitlines() if line.strip()]

    # Extract tracking numbers from lines starting with a bullet like '📌'
    for line in lines:
        if line.startswith("📌"):
            # remove leading icon and spaces
            candidate = line[1:].strip()
            # sometimes lines like "📌 777343103777925" or "📌 YT879..."
            token = candidate.split()[0]
            # basic sanity: alnum and length >= 8
            if re.fullmatch(r"[A-Za-z0-9]{8,}", token):
                tracking_numbers.append(token)

    # Fallback: if none found, try to find alnum codes on their own lines
    if not tracking_numbers:
        for line in lines:
            if re.fullmatch(r"[A-Za-z0-9]{8,}", line):
                tracking_numbers.append(line)

    # Extract weight
    weight_regex = re.compile(r"Вес\s*(?:посылок\s*ИТОГО|посылки)?\s*:\s*([0-9]+(?:[\.,][0-9]+)?)\s*кг", re.IGNORECASE)
    for line in lines:
        m = weight_regex.search(line)
        if m:
            try:
                total_weight = Decimal(m.group(1).replace(",", "."))
                break
            except (InvalidOperation, ValueError):
                pass

    # Extract cost
    cost_regex = re.compile(r"(?:Стоимость\s*ИТОГО|Оплата)\s*:\s*([0-9]+(?:[\.,][0-9]+)?)\s*[cс]", re.IGNORECASE)
    for line in lines:
        m = cost_regex.search(line)
        if m:
            try:
                total_cost = Decimal(m.group(1).replace(",", "."))
                break
            except (InvalidOperation, ValueError):
                pass

    # Deduplicate while preserving order
    seen = set()
    unique_tracking: List[str] = []
    for t in tracking_numbers:
        if t not in seen:
            seen.add(t)
            unique_tracking.append(t)

    return unique_tracking, total_weight, total_cost




