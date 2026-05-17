import db.queries as queries
from utils.helpers import current_date, advance_by_interval, advance_from_anchor


def process_recurring():
    """Generate any overdue recurring expense entries and goal contributions.
    Safe to call multiple times — advances next_date past today each run.
    """
    today = current_date()
    _process_expenses(today)
    _process_goals(today)


def _process_expenses(today):
    for r in queries.get_due_recurring_expenses(today):
        next_date = r['recur_next_date']
        unit = r.get('recur_unit', 'month')
        interval = r['recur_interval']
        # anchor: the original start date — ensures correct day-of-month is
        # preserved even after short-month clamping (e.g. Jan 31 → Mar 31)
        anchor = r.get('recur_start_date') or next_date

        while next_date <= today:
            queries.add_expense(
                r['amount'], r['category_id'], r['note'], next_date,
                # Generated entries are NOT recurring templates themselves
            )
            next_date = advance_from_anchor(anchor, next_date, interval, unit)

        queries.update_expense_recur_next(r['id'], next_date)


def _process_goals(today):
    for r in queries.get_due_recurring_goals(today):
        next_date = r['recur_next_date']
        unit = r.get('recur_unit', 'month')
        interval = r['recur_interval']
        while next_date <= today:
            queries.add_to_goal(r['id'], r['recur_amount'])
            next_date = advance_by_interval(next_date, interval, unit)
            if queries.is_goal_complete(r['id']):
                break
        queries.update_goal_recur_next(r['id'], next_date)
