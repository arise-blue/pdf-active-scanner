import re
from typing import Tuple, Optional


def extract_service_type(text: str) -> str:
    """Extract service type from text using regex patterns."""
    text_lower = text.lower()

    if re.search(r'\bias\s+officer', text_lower, re.IGNORECASE):
        return "IAS"
    elif re.search(r'\bips\s+officer', text_lower, re.IGNORECASE):
        return "IPS"
    elif re.search(r'\birs\s+officer', text_lower, re.IGNORECASE):
        return "IRS"
    elif re.search(r'\bifs\s+officer', text_lower, re.IGNORECASE):
        return "IFS"
    elif re.search(r'\bcias\b', text_lower, re.IGNORECASE):
        return "CIAS"
    elif re.search(r'bureaucrat|civil\s+servant', text_lower, re.IGNORECASE):
        return "Unknown"

    return "Unknown"


def extract_status(text: str) -> str:
    """Extract officer status from text using keyword matching."""
    text_lower = text.lower()

    if re.search(r'\barrested\b', text_lower):
        return "Arrested"
    elif re.search(r'\bconvicted\b|\bsentenced\b', text_lower):
        return "Convicted"
    elif re.search(r'\bsuspended\b', text_lower):
        return "Suspended"
    elif re.search(r'\bchargesheeted\b|\bcharge\s+sheet\b', text_lower):
        return "Chargesheeted"
    elif re.search(r'\bdismissed\s+from\s+service\b|\bremoved\s+from\s+service\b', text_lower):
        return "Dismissed"
    elif re.search(r'\bbail\b|\breinstated\b', text_lower):
        return "Bail / Reinstated"

    return "Under inquiry"


def extract_investigating_agency(text: str) -> str:
    """Extract investigating agency from text."""
    text_lower = text.lower()

    agencies = {
        r'\bcbi\b': "CBI",
        r'\bed\s+raid\b|\benforcment\s+directorate\b|\be\.d\b': "ED",
        r'\bcvc\b': "CVC",
        r'\bacb\b': "ACB",
        r'\bvigilance\b': "Vigilance Bureau",
        r'\bincome\s+tax\b|\bit\b': "Income Tax",
        r'\bstate\s+police\b': "State Police",
    }

    for pattern, agency in agencies.items():
        if re.search(pattern, text_lower):
            return agency

    return None


def generate_charge_summary(text: str, officer_name: str = None) -> str:
    """Generate a charge summary from article text."""
    sentences = re.split(r'[.!?]+', text)
    corruption_keywords = [
        "arrested", "corruption", "bribery", "disproportionate",
        "money laundering", "embezzlement", "fraud", "suspended",
        "chargesheeted", "convicted", "misconduct"
    ]

    for sentence in sentences:
        sentence_lower = sentence.lower()
        if any(keyword in sentence_lower for keyword in corruption_keywords):
            summary = sentence.strip()
            if len(summary) > 200:
                summary = summary[:197] + "..."
            return summary if summary else None

    if len(text) > 200:
        return text[:197] + "..."
    return text[:200] if text else None


def extract_state_from_text(text: str) -> Optional[str]:
    """Extract Indian state name from text."""
    states = [
        "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chhattisgarh",
        "Goa", "Gujarat", "Haryana", "Himachal Pradesh", "Jharkhand", "Karnataka",
        "Kerala", "Madhya Pradesh", "Maharashtra", "Manipur", "Meghalaya", "Mizoram",
        "Nagaland", "Odisha", "Punjab", "Rajasthan", "Sikkim", "Tamil Nadu",
        "Telangana", "Tripura", "Uttar Pradesh", "Uttarakhand", "West Bengal",
        "Delhi", "Puducherry", "Chandigarh", "Andaman and Nicobar",
        "UP", "MP", "HP", "AP", "TS", "TN", "WB"
    ]

    text_lower = text.lower()
    for state in states:
        if re.search(r'\b' + state.lower() + r'\b', text_lower):
            return state

    return None


def sanitize_officer_name(name: str) -> str:
    """Sanitize officer name for deduplication."""
    if not name:
        return ""
    return re.sub(r'\s+', ' ', name.strip()).title()
