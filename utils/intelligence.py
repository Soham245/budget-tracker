"""
Financial Intelligence Engine.

Architecture (single-pass design):
  1. gather_data(year_month, income)  →  raw signals dict
  2. compute_health_score(data)       →  score / status / color / reason bullets
  3. top_insights(data, currency, n)  →  prioritised (kind, text) list

All heavy lifting is isolated here so screens stay thin.
"""

import statistics as _stats


# ── Date helpers ──────────────────────────────────────────────────────────────

def _n_months_ago(year_month, n):
    y, m = int(year_month[:4]), int(year_month[5:])
    m -= n
    while m <= 0:
        m += 12
        y -= 1
    return f'{y}-{m:02d}'


# ── Data gathering ────────────────────────────────────────────────────────────

def gather_data(year_month, income):
    """Collect every signal needed for health score + insights in one place."""
    from db import queries as _q
    from utils.helpers import days_elapsed_in_month, days_remaining_in_month

    total      = _q.get_monthly_total(year_month)
    categories = _q.get_category_totals_for_month(year_month)
    days_elapsed = days_elapsed_in_month(year_month)
    days_left    = days_remaining_in_month(year_month)

    # 3-month rolling averages — 3 queries instead of N×3
    prev_cat_buckets = {}  # {cat_id: [t1, t2, t3]}
    prev_totals = []
    for i in range(1, 4):
        ym_i = _n_months_ago(year_month, i)
        prev_totals.append(_q.get_monthly_total(ym_i))
        for row in _q.get_category_totals_for_month(ym_i):
            prev_cat_buckets.setdefault(row['id'], []).append(row['spent'])

    rolling_avg = sum(prev_totals) / 3
    cat_rolling = {
        cid: sum(vals) / 3          # always divide by 3 to normalise absent months
        for cid, vals in prev_cat_buckets.items()
    }

    rec_total = _q.get_monthly_recurring_total()
    goals     = [g for g in _q.get_all_goals() if not g['is_complete']]
    daily     = _q.get_daily_totals_for_month(year_month)
    ww        = _q.get_weekday_vs_weekend_spending(year_month)

    return {
        'year_month':  year_month,
        'income':      income,
        'total':       total,
        'categories':  categories,
        'cat_rolling': cat_rolling,
        'rolling_avg': rolling_avg,
        'rec_total':   rec_total,
        'goals':       goals,
        'daily':       daily,
        'ww':          ww,
        'days_elapsed': days_elapsed,
        'days_left':    days_left,
    }


# ── Health score ──────────────────────────────────────────────────────────────

def compute_health_score(data):
    """Return {'score': int 0-100, 'status': str, 'color': list, 'reasons': [str]}."""
    income     = data['income']
    total      = data['total']
    categories = data['categories']
    rec_total  = data['rec_total']
    goals      = data['goals']
    daily      = data['daily']

    # ── Component 1: Budget adherence  (0–30) ─────────────────────────────────
    budgeted = [c for c in categories if c['budget'] > 0]
    if budgeted:
        adherence = 0.0
        for c in budgeted:
            if c['spent'] <= c['budget']:
                adherence += 1.0
            else:
                over_ratio = (c['spent'] - c['budget']) / c['budget']
                adherence += max(0.0, 1.0 - min(over_ratio, 1.0))
        score_budget = (adherence / len(budgeted)) * 30
    else:
        score_budget = 15  # neutral — no budgets configured

    # ── Component 2: Income ratio  (0–25) ────────────────────────────────────
    if income > 0:
        ratio = total / income
        if ratio < 0.60:
            score_income = 25
        elif ratio < 0.80:
            score_income = 25 - (ratio - 0.60) / 0.20 * 10
        elif ratio < 1.0:
            score_income = 15 - (ratio - 0.80) / 0.20 * 15
        else:
            score_income = 0
    else:
        score_income = 12  # neutral — income not set

    # ── Component 3: Recurring burden  (0–20) ────────────────────────────────
    if income > 0 and rec_total > 0:
        burden = rec_total / income
        if burden < 0.20:
            score_rec = 20
        elif burden < 0.30:
            score_rec = 15
        elif burden < 0.40:
            score_rec = 9
        elif burden < 0.50:
            score_rec = 4
        else:
            score_rec = 0
    else:
        score_rec = 15  # neutral

    # ── Component 4: Savings progress  (0–15) ────────────────────────────────
    if goals:
        progress_vals = [
            g['saved'] / g['target']
            for g in goals if g['target'] > 0
        ]
        avg_progress  = sum(progress_vals) / len(progress_vals) if progress_vals else 0
        score_savings = avg_progress * 15
    else:
        score_savings = 8  # neutral

    # ── Component 5: Spending consistency  (0–10) ────────────────────────────
    if len(daily) >= 5:
        vals     = [d['total'] for d in daily]
        mean_val = sum(vals) / len(vals)
        if mean_val > 0:
            std_val = _stats.stdev(vals) if len(vals) > 1 else 0
            cv      = std_val / mean_val
            if cv < 0.5:
                score_consistency = 10
            elif cv < 1.0:
                score_consistency = 7
            elif cv < 1.5:
                score_consistency = 4
            else:
                score_consistency = 2
        else:
            score_consistency = 5
    else:
        score_consistency = 5  # neutral — sparse data

    score = int(score_budget + score_income + score_rec + score_savings + score_consistency)
    score = max(0, min(100, score))

    if score >= 80:
        status = 'Excellent'
        color  = [0.42, 0.82, 0.52, 1]
    elif score >= 60:
        status = 'Stable'
        color  = [0.45, 0.85, 0.55, 1]
    elif score >= 40:
        status = 'Warning'
        color  = [0.95, 0.78, 0.45, 1]
    else:
        status = 'Risky'
        color  = [0.92, 0.50, 0.50, 1]

    reasons = _health_reasons(
        score_budget, score_rec, budgeted,
        income, total, rec_total, goals,
    )
    return {'score': score, 'status': status, 'color': color, 'reasons': reasons}


def _health_reasons(score_budget, score_rec, budgeted, income, total, rec_total, goals):
    """Return up to 2 short plain-English bullets for the health card."""
    candidates = []  # (priority, text)

    if income > 0 and total >= 0:
        pct = total / income * 100
        if pct < 60:
            candidates.append((10, "You're spending well below your income"))
        elif pct < 80:
            candidates.append((6,  f"Spending is at {pct:.0f}% of income — you're on track"))
        elif pct < 100:
            candidates.append((8,  f"You've used {pct:.0f}% of income — watch your pace"))
        else:
            candidates.append((10, "Your spending has crossed your income this month"))

    if income > 0 and rec_total > 0:
        pct = rec_total / income * 100
        if pct > 40:
            candidates.append((9, f"Recurring bills are taking {pct:.0f}% of your income"))
        elif pct > 25:
            candidates.append((5, f"Recurring expenses are a manageable {pct:.0f}% of income"))
        else:
            candidates.append((2, f"Recurring costs stay light at {pct:.0f}% of income"))

    if budgeted:
        if score_budget >= 25:
            candidates.append((7, "Every category is staying within budget"))
        elif score_budget < 15:
            over = [c['name'] for c in budgeted if c['spent'] > c['budget']]
            if over:
                if len(over) == 1:
                    candidates.append((8, f"{over[0]} is over its budget"))
                else:
                    candidates.append((8, f"{', '.join(over[:2])} are over budget"))

    if goals:
        best = max(
            (g for g in goals if g['target'] > 0),
            key=lambda g: g['saved'] / g['target'],
            default=None,
        )
        if best:
            pct = best['saved'] / best['target'] * 100
            if pct >= 75:
                candidates.append((5, f"You're {pct:.0f}% of the way to '{best['name']}' — almost there"))

    candidates.sort(key=lambda x: x[0], reverse=True)
    return [t for _, t in candidates[:2]]


# ── Insight generation ────────────────────────────────────────────────────────

def top_insights(data, currency, n=4):
    """Return up to n (kind, text) tuples, best-first, deduplicated by type."""
    candidates = list(_generate_all(data, currency))
    candidates.sort(key=lambda x: x[0], reverse=True)

    seen   = set()
    result = []
    for _priority, kind, tag, text in candidates:
        if tag not in seen:
            seen.add(tag)
            result.append((kind, text))
            if len(result) >= n:
                break

    if not result:
        result.append(('info', 'Add more expenses to unlock spending insights'))
    return result


def _generate_all(data, currency):
    """Yield (priority, kind, type_tag, text) for every plausible insight."""
    from utils.helpers import format_currency, predict_overspend_days

    income       = data['income']
    total        = data['total']
    categories   = data['categories']
    cat_rolling  = data['cat_rolling']
    rolling_avg  = data['rolling_avg']
    rec_total    = data['rec_total']
    goals        = data['goals']
    ww           = data['ww']
    days_elapsed = data['days_elapsed']
    days_left    = data['days_left']

    # ── Category trend vs 3-month rolling average ─────────────────────────────
    for cat in categories:
        if cat['spent'] <= 0:
            continue
        avg = cat_rolling.get(cat['id'], 0)
        if avg < 50:          # too sparse — skip
            continue
        change_pct = (cat['spent'] - avg) / avg * 100
        if abs(change_pct) < 15:
            continue
        if change_pct > 0:
            kind = 'warn' if change_pct > 30 else 'info'
            text = f"You're spending {change_pct:.0f}% more on {cat['name']} than usual"
            priority = min(9.5, 4.0 + abs(change_pct) / 15)
        else:
            kind = 'low'
            text = f"You spent {abs(change_pct):.0f}% less on {cat['name']} this month"
            priority = min(7.0, 3.0 + abs(change_pct) / 20)
        yield (priority, kind, f'cat_{cat["id"]}', text)

    # ── Overall vs 3-month rolling average ───────────────────────────────────
    if rolling_avg > 50 and total > 0:
        change_pct = (total - rolling_avg) / rolling_avg * 100
        if abs(change_pct) >= 20:
            if change_pct > 0:
                yield (5.0 + change_pct / 20, 'warn', 'total_trend',
                       f"Overall spending is {change_pct:.0f}% above your typical month")
            else:
                yield (4.0, 'low', 'total_trend',
                       f"You're spending {abs(change_pct):.0f}% less than a typical month")

    # ── Income ratio ──────────────────────────────────────────────────────────
    if income > 0 and total >= 0:
        pct = total / income * 100
        if pct < 40:
            yield (3.0, 'low',    'income_ratio',
                   f"Only {pct:.0f}% of income spent — excellent discipline")
        elif pct < 70:
            yield (3.0, 'ok',     'income_ratio',
                   f"You've used {pct:.0f}% of income — comfortably on track")
        elif pct < 100:
            yield (6.0, 'warn',   'income_ratio',
                   f"{pct:.0f}% of income spent with {days_left} days to go")
        else:
            yield (9.0, 'danger', 'income_ratio',
                   f"Spending has overshot income by {pct - 100:.0f}%")

    # ── Recurring burden ──────────────────────────────────────────────────────
    if income > 0 and rec_total > 0:
        pct = rec_total / income * 100
        if pct > 35:
            yield (7.0, 'warn', 'rec_burden',
                   f"Recurring bills are eating {pct:.0f}% of your income")
        elif pct > 20:
            yield (4.0, 'info', 'rec_burden',
                   f"Recurring costs sit at {pct:.0f}% of your income")

    # ── Budget pressure (worst category) ─────────────────────────────────────
    if days_left > 0 and days_elapsed > 0:
        for cat in sorted(categories, key=lambda c: c['spent'] / max(c['budget'], 1), reverse=True):
            if cat['budget'] <= 0 or cat['spent'] <= 0:
                continue
            d = predict_overspend_days(cat['spent'], cat['budget'], days_elapsed, days_left)
            if d is None:
                continue
            if d == 0:
                yield (10.0, 'danger', 'budget_pressure',
                       f"Your {cat['name']} budget is fully used up")
            elif d <= 5:
                yield (9.0, 'warn', 'budget_pressure',
                       f"At this pace, {cat['name']} will run out in ~{d} days")
            elif d <= 10:
                yield (6.0, 'warn', 'budget_pressure',
                       f"{cat['name']} may exceed its budget in about {d} days")
            break  # only surface the single most critical one

    # ── Month-end projection ──────────────────────────────────────────────────
    if days_left > 0 and days_elapsed > 0 and total > 0:
        daily_avg  = total / days_elapsed
        projected  = total + daily_avg * days_left
        if income > 0 and projected > income * 1.05:
            overage = projected - income
            yield (8.0, 'warn', 'projection',
                   f"On pace to overspend by {format_currency(overage, currency)} this month")
        elif income > 0 and projected < income * 0.75:
            yield (2.0, 'low', 'projection',
                   f"Projected to finish near {format_currency(projected, currency)} — well under income")

    # ── Weekend vs weekday ────────────────────────────────────────────────────
    wd_days  = ww.get('weekday_days',  0)
    we_days  = ww.get('weekend_days',  0)
    wd_total = ww.get('weekday_total', 0.0)
    we_total = ww.get('weekend_total', 0.0)
    if wd_days >= 5 and we_days >= 2 and wd_total > 0:
        wd_daily = wd_total / wd_days
        we_daily = we_total / we_days
        if we_daily > wd_daily * 1.5:
            ratio = we_daily / wd_daily
            yield (5.0, 'info', 'weekend',
                   f"Your weekends cost {ratio:.1f}× more than your weekdays")
        elif wd_daily > we_daily * 1.5 and we_days > 0:
            yield (3.0, 'info', 'weekend',
                   "Weekdays drive most of your spending this month")

    # ── Best savings goal highlight ───────────────────────────────────────────
    if goals:
        best = max(
            (g for g in goals if g['target'] > 0),
            key=lambda g: g['saved'] / g['target'],
            default=None,
        )
        if best:
            pct = best['saved'] / best['target'] * 100
            if pct >= 75:
                yield (4.0, 'low',  'goal',
                       f"You're {pct:.0f}% of the way to '{best['name']}' — almost there")
            elif pct >= 40:
                yield (2.0, 'info', 'goal',
                       f"'{best['name']}' is {pct:.0f}% funded — keep going")
