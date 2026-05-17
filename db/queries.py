from db.database import get_connection


# ── Categories ──────────────────────────────────────────────────────────────

def get_all_categories():
    conn = get_connection()
    c = conn.cursor()
    # "Other" is the catch-all bucket — always last in pickers/lists/charts
    # across the app so it doesn't crowd the meaningful categories alphabetically.
    c.execute(
        "SELECT id, name, color, budget FROM categories "
        "ORDER BY CASE WHEN name = 'Other' THEN 1 ELSE 0 END, name"
    )
    rows = c.fetchall()
    conn.close()
    return [{'id': r[0], 'name': r[1], 'color': r[2], 'budget': r[3]} for r in rows]


def update_category_budget(category_id, budget):
    conn = get_connection()
    c = conn.cursor()
    c.execute('UPDATE categories SET budget = ? WHERE id = ?', (budget, category_id))
    conn.commit()
    conn.close()


# ── Expenses ─────────────────────────────────────────────────────────────────

def add_expense(amount, category_id, note, date,
                is_recurring=0, recur_interval=1, recur_unit='month',
                recur_next_date=None, recur_start_date=None):
    from datetime import datetime as _dt
    created_at = _dt.now().strftime('%Y-%m-%d %H:%M:%S')
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        '''INSERT INTO expenses
               (amount, category_id, note, date, is_recurring, recur_interval,
                recur_unit, recur_next_date, recur_start_date, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
        (amount, category_id, note, date, is_recurring, recur_interval,
         recur_unit, recur_next_date,
         recur_start_date if recur_start_date else date,
         created_at),
    )
    new_id = c.lastrowid
    conn.commit()
    conn.close()
    return new_id


def duplicate_expense(expense_id, new_date):
    """Clone an existing expense as a NEW one-off entry on `new_date`.
    Preserves amount, category, note, and recurring settings (which become
    a fresh recurring template with `new_date` as the anchor)."""
    src = get_expense_by_id(expense_id)
    if not src:
        return None
    if src['is_recurring']:
        from utils.helpers import advance_by_interval
        next_dt = advance_by_interval(new_date, src['recur_interval'], src['recur_unit'])
        return add_expense(
            src['amount'], src['category_id'], src['note'], new_date,
            is_recurring=1,
            recur_interval=src['recur_interval'],
            recur_unit=src['recur_unit'],
            recur_next_date=next_dt,
            recur_start_date=new_date,
        )
    return add_expense(src['amount'], src['category_id'], src['note'], new_date)


def get_expenses_for_month(year_month):
    """year_month: '2026-04' format"""
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        '''SELECT e.id, e.amount, cat.name, cat.color, e.note, e.date,
                  COALESCE(e.is_recurring, 0), e.recur_next_date, COALESCE(e.recur_paused, 0)
           FROM expenses e
           JOIN categories cat ON e.category_id = cat.id
           WHERE strftime('%Y-%m', e.date) = ?
           ORDER BY e.date DESC, e.id DESC''',
        (year_month,),
    )
    rows = c.fetchall()
    conn.close()
    return [
        {'id': r[0], 'amount': r[1], 'category': r[2], 'color': r[3],
         'note': r[4], 'date': r[5], 'is_recurring': bool(r[6]),
         'recur_next_date': r[7] or '', 'recur_paused': bool(r[8])}
        for r in rows
    ]


def get_monthly_total(year_month):
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        "SELECT COALESCE(SUM(amount), 0) FROM expenses WHERE strftime('%Y-%m', date) = ?",
        (year_month,),
    )
    total = c.fetchone()[0]
    conn.close()
    return total


def get_category_totals_for_month(year_month):
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        '''SELECT cat.id, cat.name, cat.color, cat.budget, COALESCE(SUM(e.amount), 0) AS spent
           FROM categories cat
           LEFT JOIN expenses e ON e.category_id = cat.id
               AND strftime('%Y-%m', e.date) = ?
           GROUP BY cat.id
           ORDER BY spent DESC,
                    CASE WHEN cat.name = 'Other' THEN 1 ELSE 0 END,
                    cat.name''',
        (year_month,),
    )
    rows = c.fetchall()
    conn.close()
    return [
        {'id': r[0], 'name': r[1], 'color': r[2], 'budget': r[3], 'spent': r[4]}
        for r in rows
    ]


def get_expense_by_id(expense_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        '''SELECT e.id, e.amount, e.category_id, cat.name, cat.color, e.note, e.date,
                  COALESCE(e.is_recurring, 0), COALESCE(e.recur_interval, 1),
                  COALESCE(e.recur_unit, 'month'), e.recur_next_date, COALESCE(e.recur_paused, 0),
                  e.created_at
           FROM expenses e
           JOIN categories cat ON e.category_id = cat.id
           WHERE e.id = ?''',
        (expense_id,),
    )
    row = c.fetchone()
    conn.close()
    if row:
        return {
            'id': row[0], 'amount': row[1], 'category_id': row[2],
            'category': row[3], 'color': row[4], 'note': row[5], 'date': row[6],
            'is_recurring': bool(row[7]), 'recur_interval': row[8],
            'recur_unit': row[9], 'recur_next_date': row[10] or '',
            'recur_paused': bool(row[11]),
            'created_at': row[12] or '',
        }
    return None


def update_expense(expense_id, amount, category_id, note, date):
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        'UPDATE expenses SET amount = ?, category_id = ?, note = ?, date = ? WHERE id = ?',
        (amount, category_id, note, date, expense_id),
    )
    conn.commit()
    conn.close()


def delete_expense(expense_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute('DELETE FROM expenses WHERE id = ?', (expense_id,))
    conn.commit()
    conn.close()


def get_due_recurring_expenses(as_of_date):
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        '''SELECT id, amount, category_id, note, recur_interval,
                  COALESCE(recur_unit, 'month'), recur_next_date,
                  COALESCE(recur_start_date, recur_next_date) as recur_start_date
           FROM expenses
           WHERE is_recurring = 1 AND COALESCE(recur_paused, 0) = 0
             AND recur_next_date IS NOT NULL AND recur_next_date <= ?''',
        (as_of_date,),
    )
    rows = c.fetchall()
    conn.close()
    return [
        {'id': r[0], 'amount': r[1], 'category_id': r[2], 'note': r[3],
         'recur_interval': r[4], 'recur_unit': r[5], 'recur_next_date': r[6],
         'recur_start_date': r[7]}
        for r in rows
    ]


def update_expense_recur_next(expense_id, next_date):
    conn = get_connection()
    c = conn.cursor()
    c.execute('UPDATE expenses SET recur_next_date = ? WHERE id = ?', (next_date, expense_id))
    conn.commit()
    conn.close()


def update_recurring_schedule(expense_id, recur_interval, recur_unit):
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        'UPDATE expenses SET recur_interval = ?, recur_unit = ? WHERE id = ?',
        (recur_interval, recur_unit, expense_id),
    )
    conn.commit()
    conn.close()


def stop_recurring_expense(expense_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute('UPDATE expenses SET is_recurring = 0, recur_next_date = NULL WHERE id = ?', (expense_id,))
    conn.commit()
    conn.close()


def enable_recurring_expense(expense_id, recur_interval, recur_unit, recur_next_date):
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        '''UPDATE expenses SET is_recurring = 1, recur_interval = ?, recur_unit = ?,
           recur_next_date = ?, recur_paused = 0 WHERE id = ?''',
        (recur_interval, recur_unit, recur_next_date, expense_id),
    )
    conn.commit()
    conn.close()


def set_recurring_paused(expense_id, paused):
    conn = get_connection()
    c = conn.cursor()
    c.execute('UPDATE expenses SET recur_paused = ? WHERE id = ?', (1 if paused else 0, expense_id))
    conn.commit()
    conn.close()


def get_monthly_recurring_total():
    """Sum of all active (non-paused) recurring expense template amounts."""
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        "SELECT COALESCE(SUM(amount), 0) FROM expenses "
        "WHERE is_recurring = 1 AND COALESCE(recur_paused, 0) = 0"
    )
    total = c.fetchone()[0]
    conn.close()
    return total


def get_due_recurring_goals(as_of_date):
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        '''SELECT id, recur_amount, recur_interval, COALESCE(recur_unit, 'month'), recur_next_date
           FROM goals
           WHERE is_recurring = 1 AND is_complete = 0
             AND recur_next_date IS NOT NULL AND recur_next_date <= ?''',
        (as_of_date,),
    )
    rows = c.fetchall()
    conn.close()
    return [
        {'id': r[0], 'recur_amount': r[1], 'recur_interval': r[2], 'recur_unit': r[3], 'recur_next_date': r[4]}
        for r in rows
    ]


def update_goal_recur_next(goal_id, next_date):
    conn = get_connection()
    c = conn.cursor()
    c.execute('UPDATE goals SET recur_next_date = ? WHERE id = ?', (next_date, goal_id))
    conn.commit()
    conn.close()


def get_all_expenses():
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        '''SELECT e.id, e.amount, cat.name, e.note, e.date
           FROM expenses e
           JOIN categories cat ON e.category_id = cat.id
           ORDER BY e.date DESC, e.id DESC'''
    )
    rows = c.fetchall()
    conn.close()
    return [
        {'id': r[0], 'amount': r[1], 'category': r[2], 'note': r[3], 'date': r[4]}
        for r in rows
    ]


# ── Goals ────────────────────────────────────────────────────────────────────

def add_goal(name, target_amount, deadline=None,
             is_recurring=0, recur_amount=0.0, recur_interval=1, recur_unit='month', recur_next_date=None):
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        '''INSERT INTO goals
               (name, target_amount, deadline, is_recurring, recur_amount, recur_interval, recur_unit, recur_next_date)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
        (name, target_amount, deadline, is_recurring, recur_amount, recur_interval, recur_unit, recur_next_date),
    )
    conn.commit()
    conn.close()


def get_all_goals():
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        '''SELECT id, name, target_amount, saved_amount, deadline, is_complete,
                  COALESCE(is_recurring, 0), COALESCE(recur_amount, 0),
                  COALESCE(recur_interval, 1), COALESCE(recur_unit, 'month'), recur_next_date
           FROM goals ORDER BY is_complete, id'''
    )
    rows = c.fetchall()
    conn.close()
    return [
        {'id': r[0], 'name': r[1], 'target': r[2], 'saved': r[3], 'deadline': r[4],
         'is_complete': r[5], 'is_recurring': bool(r[6]), 'recur_amount': r[7],
         'recur_interval': r[8], 'recur_unit': r[9], 'recur_next_date': r[10]}
        for r in rows
    ]


def is_goal_complete(goal_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute('SELECT is_complete FROM goals WHERE id = ?', (goal_id,))
    row = c.fetchone()
    conn.close()
    return bool(row[0]) if row else False


def add_to_goal(goal_id, amount):
    conn = get_connection()
    c = conn.cursor()
    c.execute('UPDATE goals SET saved_amount = saved_amount + ? WHERE id = ?', (amount, goal_id))
    c.execute(
        'UPDATE goals SET is_complete = 1 WHERE id = ? AND saved_amount >= target_amount',
        (goal_id,),
    )
    conn.commit()
    conn.close()


def delete_goal(goal_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute('DELETE FROM goals WHERE id = ?', (goal_id,))
    conn.commit()
    conn.close()


# ── Settings ─────────────────────────────────────────────────────────────────

def get_setting(key):
    conn = get_connection()
    c = conn.cursor()
    c.execute('SELECT value FROM settings WHERE key = ?', (key,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None


def set_setting(key, value):
    conn = get_connection()
    c = conn.cursor()
    c.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', (key, str(value)))
    conn.commit()
    conn.close()


# ── Analytics queries (new) ───────────────────────────────────────────────────

def get_last_n_months_totals(n=6):
    """Returns list of {'label': 'Jan', 'year_month': '2026-01', 'total': 1234.5}, oldest first."""
    from datetime import datetime as dt
    conn = get_connection()
    c = conn.cursor()
    results = []
    today = dt.now()
    for i in range(n - 1, -1, -1):
        month = today.month - i
        year = today.year
        while month <= 0:
            month += 12
            year -= 1
        ym = f'{year}-{month:02d}'
        c.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM expenses WHERE strftime('%Y-%m', date) = ?",
            (ym,)
        )
        total = c.fetchone()[0]
        label = dt(year, month, 1).strftime('%b')
        results.append({'label': label, 'year_month': ym, 'total': total})
    conn.close()
    return results


def get_top_category_for_month(year_month):
    """Returns {'name': 'Food', 'amount': 1234.5, 'color': '#FF7043'} or None."""
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        '''SELECT cat.name, COALESCE(SUM(e.amount), 0) AS spent, cat.color
           FROM categories cat
           JOIN expenses e ON e.category_id = cat.id
           WHERE strftime('%Y-%m', e.date) = ?
           GROUP BY cat.id
           ORDER BY spent DESC
           LIMIT 1''',
        (year_month,),
    )
    row = c.fetchone()
    conn.close()
    if row and row[1] > 0:
        return {'name': row[0], 'amount': row[1], 'color': row[2]}
    return None


def get_all_recurring_expenses(category_name=None):
    """Returns all recurring expense templates (both active and paused).

    `category_name`: when set, restricts results to that category. Used by
    the Subscription Manager (filters to category_name='Subscriptions').
    """
    conn = get_connection()
    c = conn.cursor()
    base = '''SELECT e.id, e.amount, cat.name, cat.color, e.note,
                     COALESCE(e.recur_interval, 1), COALESCE(e.recur_unit, 'month'),
                     e.recur_next_date, COALESCE(e.recur_paused, 0)
              FROM expenses e
              JOIN categories cat ON e.category_id = cat.id
              WHERE e.is_recurring = 1'''
    params = ()
    if category_name:
        base += ' AND cat.name = ?'
        params = (category_name,)
    base += ' ORDER BY COALESCE(e.recur_paused, 0), e.recur_next_date'
    c.execute(base, params)
    rows = c.fetchall()
    conn.close()
    return [
        {'id': r[0], 'amount': r[1], 'category': r[2], 'color': r[3],
         'note': r[4] or '', 'recur_interval': r[5], 'recur_unit': r[6],
         'recur_next_date': r[7] or '', 'recur_paused': bool(r[8])}
        for r in rows
    ]


def get_monthly_recurring_total_for_category(category_name):
    """Sum of active (non-paused) recurring template amounts for a given
    category (matched by name). Used for the subscriptions hero card."""
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        '''SELECT COALESCE(SUM(e.amount), 0) FROM expenses e
           JOIN categories cat ON e.category_id = cat.id
           WHERE e.is_recurring = 1 AND COALESCE(e.recur_paused, 0) = 0
             AND cat.name = ?''',
        (category_name,),
    )
    total = c.fetchone()[0]
    conn.close()
    return total


def get_daily_totals_for_month(year_month):
    """Returns list of {'date': 'YYYY-MM-DD', 'total': float} for each day with spending."""
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        '''SELECT date, COALESCE(SUM(amount), 0)
           FROM expenses
           WHERE strftime('%Y-%m', date) = ?
           GROUP BY date
           ORDER BY date''',
        (year_month,),
    )
    rows = c.fetchall()
    conn.close()
    return [{'date': r[0], 'total': r[1]} for r in rows]


def get_weekday_vs_weekend_spending(year_month):
    """Returns weekday/weekend split: totals and distinct spending-day counts."""
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        '''SELECT
               COALESCE(SUM(CASE WHEN CAST(strftime('%w', date) AS INTEGER) IN (0,6)
                               THEN amount ELSE 0 END), 0) AS weekend_total,
               COALESCE(SUM(CASE WHEN CAST(strftime('%w', date) AS INTEGER) NOT IN (0,6)
                               THEN amount ELSE 0 END), 0) AS weekday_total,
               COUNT(DISTINCT CASE WHEN CAST(strftime('%w', date) AS INTEGER) IN (0,6)
                               THEN date END) AS weekend_days,
               COUNT(DISTINCT CASE WHEN CAST(strftime('%w', date) AS INTEGER) NOT IN (0,6)
                               THEN date END) AS weekday_days
           FROM expenses
           WHERE strftime('%Y-%m', date) = ?''',
        (year_month,),
    )
    row = c.fetchone()
    conn.close()
    if row:
        return {
            'weekend_total': row[0] or 0.0,
            'weekday_total': row[1] or 0.0,
            'weekend_days':  row[2] or 0,
            'weekday_days':  row[3] or 0,
        }
    return {'weekend_total': 0.0, 'weekday_total': 0.0, 'weekend_days': 0, 'weekday_days': 0}


def get_recent_categories(limit=3):
    """Returns last N distinct categories used, most recent first."""
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        '''SELECT DISTINCT cat.id, cat.name, cat.color
           FROM expenses e
           JOIN categories cat ON e.category_id = cat.id
           ORDER BY e.date DESC, e.id DESC
           LIMIT ?''',
        (limit,)
    )
    rows = c.fetchall()
    conn.close()
    return [{'id': r[0], 'name': r[1], 'color': r[2]} for r in rows]
