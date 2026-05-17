import csv
import os
from datetime import datetime

from kivy.metrics import dp
from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.widget import Widget
from kivy.graphics import Color, Rectangle
from kivy.properties import StringProperty, NumericProperty, ListProperty

import db.queries as queries
from db.database import get_db_path
from utils.helpers import hex_to_kivy_color, category_accent


class CategoryBudgetRow(BoxLayout):
    cat_id = NumericProperty(0)
    cat_name = StringProperty('')
    dot_color = ListProperty([0.36, 0.42, 0.75, 1])
    budget_str = StringProperty('0')


def _make_row_divider():
    """Thin 1px hairline used between CategoryBudgetRow items — same tone as
    the section dividers above/below the row list, so the grouped card reads
    as one continuous surface with list-item rhythm."""
    w = Widget(size_hint_y=None, height=dp(1))
    with w.canvas.before:
        Color(0.14, 0.16, 0.28, 1)
        rect = Rectangle(pos=w.pos, size=w.size)
    # Bind so the Rectangle tracks the widget's actual pos/size after layout.
    def _sync(*_):
        rect.pos = w.pos
        rect.size = w.size
    w.bind(pos=_sync, size=_sync)
    return w


class SettingsScreen(Screen):

    def on_enter(self, *args):
        income = queries.get_setting('monthly_income') or '0'
        val = float(income)
        self.ids.income_input.text = str(int(val)) if val == int(val) else str(val)
        self.ids.income_feedback.text = ''
        self.ids.budget_feedback.text = ''
        self.ids.export_feedback.text = ''
        currency = queries.get_setting('currency') or '₹'
        self._highlight_currency(currency)
        self._load_categories()

    def _highlight_currency(self, active):
        # Pills sit directly on the card surface — no recessed track behind.
        # Active pill takes the lavender accent + dark text + bold; inactive
        # pills carry a subtle page-tone fill so they read as distinct pill
        # shapes against the card.
        for btn_id, sym in [('btn_inr', '₹'), ('btn_usd', '$'),
                            ('btn_eur', '€'), ('btn_gbp', '£')]:
            btn = self.ids[btn_id]
            if sym == active:
                btn.fill_color = (0.75, 0.77, 0.95, 1)
                btn.color = (0.10, 0.10, 0.20, 1)
                btn.bold = True
            else:
                btn.fill_color = (0.06, 0.07, 0.12, 1)
                btn.color = (0.72, 0.74, 0.84, 1)
                btn.bold = False

    def _load_categories(self):
        container = self.ids.cat_budget_list
        container.clear_widgets()
        cats = queries.get_all_categories()
        for i, cat in enumerate(cats):
            r, g, b, _ = category_accent(cat['color'])
            budget = cat['budget'] or 0
            row = CategoryBudgetRow(
                cat_id=cat['id'],
                cat_name=cat['name'],
                dot_color=[r, g, b, 1],
                budget_str=str(int(budget)) if budget == int(budget) else str(budget),
            )
            container.add_widget(row)
            # Hairline divider between rows (but not after the last one — the
            # section's own footer divider above the Save button handles that).
            if i < len(cats) - 1:
                container.add_widget(_make_row_divider())

    def save_income(self):
        try:
            val = float(self.ids.income_input.text.strip() or '0')
            if val < 0:
                raise ValueError
            queries.set_setting('monthly_income', val)
            self.ids.income_feedback.text = '✓ Saved'
            self.ids.income_feedback.color = (0.30, 0.69, 0.31, 1)
        except ValueError:
            self.ids.income_feedback.text = 'Invalid amount'
            self.ids.income_feedback.color = (0.96, 0.26, 0.21, 1)

    def set_currency(self, symbol):
        queries.set_setting('currency', symbol)
        self._highlight_currency(symbol)

    def save_all_budgets(self):
        for row in self.ids.cat_budget_list.children:
            try:
                budget = float(row.ids.budget_input.text.strip() or '0')
                queries.update_category_budget(row.cat_id, max(0.0, budget))
            except (ValueError, AttributeError):
                pass
        self.ids.budget_feedback.text = '✓ Saved'
        self.ids.budget_feedback.color = (0.30, 0.69, 0.31, 1)

    def export_csv(self):
        expenses = queries.get_all_expenses()
        db_path = get_db_path()
        export_dir = os.path.dirname(db_path)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filepath = os.path.join(export_dir, f'budget_export_{timestamp}.csv')
        try:
            with open(filepath, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(['Date', 'Category', 'Amount', 'Note'])
                for e in expenses:
                    writer.writerow([e['date'], e['category'], e['amount'], e['note'] or ''])
            self.ids.export_feedback.text = f'✓ Exported {len(expenses)} rows → {os.path.basename(filepath)}'
            self.ids.export_feedback.color = (0.30, 0.69, 0.31, 1)
        except Exception as ex:
            self.ids.export_feedback.text = f'Export failed: {ex}'
            self.ids.export_feedback.color = (0.96, 0.26, 0.21, 1)
