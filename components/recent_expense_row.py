from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.behaviors import ButtonBehavior
from kivy.properties import StringProperty, ListProperty, NumericProperty


class RecentExpenseRow(ButtonBehavior, BoxLayout):
    """Tappable recent-expense row on the home dashboard. Opens the detail
    page when tapped, with a brief press tint as feedback."""
    expense_id = NumericProperty(0)
    exp_category = StringProperty('')
    exp_amount = StringProperty('')
    exp_note = StringProperty('')
    exp_date = StringProperty('')
    exp_color = ListProperty([0.5, 0.5, 0.5, 1])

    def on_release(self):
        app = App.get_running_app()
        if app and self.expense_id:
            app.open_expense(self.expense_id, return_to='home')
