import calendar
from datetime import datetime, timedelta

# Shared recurring interval caps — single source of truth for all screens
RECUR_MAX = {'day': 365, 'month': 12, 'year': 10}


def format_currency(amount, currency='₹'):
    return f'{currency}{amount:,.2f}'


def current_month():
    return datetime.now().strftime('%Y-%m')


def current_date():
    return datetime.now().strftime('%Y-%m-%d')


def display_date(iso_date):
    try:
        dt = datetime.strptime(iso_date, '%Y-%m-%d')
        return dt.strftime('%d %b %Y')
    except (ValueError, TypeError):
        return iso_date or ''


def relative_date_label(iso_date):
    """Friendly group header label: 'Today', 'Yesterday', weekday name within
    the past week, or 'Weekday, Mon DD' for older dates in the same year."""
    try:
        dt = datetime.strptime(iso_date, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return iso_date or ''
    today = datetime.now().date()
    delta = (today - dt).days
    if delta == 0:
        return 'Today'
    if delta == 1:
        return 'Yesterday'
    if 0 < delta < 7:
        return dt.strftime('%A')
    return dt.strftime('%A, %b %d').replace(' 0', ' ')


def display_month(year_month):
    try:
        dt = datetime.strptime(year_month, '%Y-%m')
        return dt.strftime('%B %Y')
    except (ValueError, TypeError):
        return year_month or ''


def days_remaining_in_month(month=None):
    """Returns days left in the given month (YYYY-MM) or the current month."""
    now = datetime.now()
    if month:
        year, mo = int(month[:4]), int(month[5:7])
        if not (year == now.year and mo == now.month):
            return 0  # past month: no days remaining
    if now.month == 12:
        next_month = now.replace(year=now.year + 1, month=1, day=1)
    else:
        next_month = now.replace(month=now.month + 1, day=1)
    return (next_month - now).days


def days_elapsed_in_month(month=None):
    """Returns days elapsed in the given month (YYYY-MM) or the current month."""
    now = datetime.now()
    if month:
        year, mo = int(month[:4]), int(month[5:7])
        if year == now.year and mo == now.month:
            return now.day
        import calendar as _cal
        return _cal.monthrange(year, mo)[1]  # past month: all days elapsed
    return now.day


def advance_months(date_str, months):
    """Advance a YYYY-MM-DD date by N whole months, clamping to last day of target month."""
    dt = datetime.strptime(date_str, '%Y-%m-%d')
    total = dt.month + months
    year = dt.year + (total - 1) // 12
    month = (total - 1) % 12 + 1
    day = min(dt.day, calendar.monthrange(year, month)[1])
    return f'{year}-{month:02d}-{day:02d}'


def advance_by_interval(date_str, value, unit):
    """Advance a YYYY-MM-DD date by `value` units of type day/month/year."""
    if unit == 'day':
        dt = datetime.strptime(date_str, '%Y-%m-%d')
        return (dt + timedelta(days=value)).strftime('%Y-%m-%d')
    elif unit == 'year':
        return advance_months(date_str, value * 12)
    else:
        return advance_months(date_str, value)


def advance_from_anchor(anchor_date_str, current_next_str, interval, unit):
    """
    Compute the next recurrence date after `current_next_str` using the
    anchor day-of-month so day-drift never accumulates.

    Example: anchor=2026-01-31, interval=1 month
      current_next=2026-01-31 → 2026-02-28  (clamped, correct)
      current_next=2026-02-28 → 2026-03-31  (back to anchor day, correct)
      Without this: 2026-02-28 + 1 month = 2026-03-28  (wrong)
    """
    if unit == 'day':
        # Days are exact — no drift possible
        return advance_by_interval(current_next_str, interval, unit)

    # For month and year: compute elapsed months from anchor, add one interval
    anchor_dt = datetime.strptime(anchor_date_str, '%Y-%m-%d')
    current_dt = datetime.strptime(current_next_str, '%Y-%m-%d')

    if unit == 'year':
        months_per_unit = interval * 12
    else:
        months_per_unit = interval

    # Months elapsed from anchor to current_next (using year/month only)
    elapsed = (current_dt.year - anchor_dt.year) * 12 + (current_dt.month - anchor_dt.month)
    # Next step: elapsed + one interval, applied to anchor
    return advance_months(anchor_date_str, elapsed + months_per_unit)



INTERVAL_LABELS = {
    1: 'monthly',
    2: 'every 2 months',
    3: 'quarterly',
    6: 'every 6 months',
    12: 'yearly',
}


def humanize_recur(interval, unit):
    """Render a (interval, unit) pair as a human-readable cadence label.

    Examples:
      (1, 'month')  -> 'Monthly'
      (2, 'month')  -> 'Every 2 months'
      (12, 'month') -> 'Yearly'
      (1, 'day')    -> 'Daily'
    """
    try:
        interval = int(interval or 1)
    except (TypeError, ValueError):
        interval = 1
    unit = unit or 'month'
    if unit == 'month' and interval in INTERVAL_LABELS:
        return INTERVAL_LABELS[interval].capitalize()
    if interval == 1:
        return {'day': 'Daily', 'week': 'Weekly', 'month': 'Monthly', 'year': 'Yearly'}.get(unit, f'Every {unit}')
    plural = 's' if interval > 1 else ''
    return f'Every {interval} {unit}{plural}'


def next_due_label(iso_date, paused=False):
    """Compact pill label for a recurring item's next due date.

    Returns one of: 'Paused', 'Today', 'Tomorrow', 'Overdue 3d', 'in 5d',
    or a 'DD MMM' fallback for distant dates."""
    if paused:
        return 'Paused'
    d = days_until(iso_date)
    if d is None:
        return '—'
    if d < 0:
        return f'Overdue {abs(d)}d'
    if d == 0:
        return 'Today'
    if d == 1:
        return 'Tomorrow'
    if d <= 14:
        return f'in {d}d'
    try:
        dt = datetime.strptime(iso_date, '%Y-%m-%d')
        return dt.strftime('%d %b')
    except (ValueError, TypeError):
        return iso_date


def days_until(iso_date):
    try:
        target = datetime.strptime(iso_date, '%Y-%m-%d').date()
        return (target - datetime.now().date()).days
    except (ValueError, TypeError):
        return None


def hex_to_kivy_color(hex_color, alpha=1.0):
    """Convert '#FF7043' to a Kivy RGBA tuple (values 0.0–1.0)."""
    h = hex_color.lstrip('#')
    return (int(h[0:2], 16) / 255.0, int(h[2:4], 16) / 255.0, int(h[4:6], 16) / 255.0, alpha)


def category_accent(hex_color, alpha=1.0):
    """Single source of truth for category color rendering.

    Returns a softened pastel RGBA derived from the raw category hex so every
    surface (progress bar, expense row accent, category chip, top-category
    label, analytics dot) renders the same category with the same tone.
    """
    r, g, b, _ = hex_to_kivy_color(hex_color)
    # Blend 70% original + 30% pastel-white tint → keeps hue identity but
    # desaturates enough to fit the dark/pastel aesthetic.
    return (r * 0.70 + 0.27, g * 0.70 + 0.27, b * 0.70 + 0.285, alpha)


def category_soft(hex_color, alpha=0.15):
    """Faint tinted fill for backgrounds/strips (cards, chips). Same hue as
    category_accent but at low alpha for surface tints."""
    r, g, b, _ = category_accent(hex_color, 1.0)
    return (r, g, b, alpha)


# ── Analytics / Intelligence helpers ──────────────────────────────────────────

def goal_weekly_needed(saved, target, deadline_str, currency='₹'):
    """
    Returns a human-readable forecast string.
    e.g. 'Need ₹500/week to stay on track'
    """
    remaining = target - saved
    if remaining <= 0:
        return ''
    d = days_until(deadline_str)
    if d is None:
        return ''
    if d < 0:
        return 'Deadline has passed'
    if d == 0:
        return 'Due today!'
    if d <= 7:
        return f'Due in {d} days — final push!'
    weeks = d / 7.0
    weekly = remaining / weeks
    return f'Need {format_currency(weekly, currency)}/week to stay on track'


def predict_overspend_days(spent, budget, days_elapsed, days_left):
    """
    Predicts how many days until `budget` is exceeded at current daily rate.
    Returns int (days from now) if overspend predicted, else None.
    days_elapsed: days already passed this month (use days_elapsed_in_month()).
    """
    if budget <= 0 or days_left <= 0 or days_elapsed <= 0 or spent <= 0:
        return None
    if spent >= budget:
        return 0
    daily_rate = spent / days_elapsed
    remaining_budget = budget - spent
    days_to_exceed = remaining_budget / daily_rate
    if days_to_exceed < days_left:
        return max(0, int(days_to_exceed))
    return None
