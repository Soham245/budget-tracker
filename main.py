import os
from kivy.app import App
from kivy.uix.screenmanager import ScreenManager, SlideTransition, NoTransition
from kivy.lang import Builder
from kivy.properties import StringProperty
from kivy.core.text import LabelBase

from db.database import init_db
from utils.recurring import process_recurring
from screens.home import HomeScreen
from screens.add_expense import AddExpenseScreen, RecurringToggle, ToggleRow  # noqa: F401
from screens.history import HistoryScreen, EditExpensePopup  # noqa: F401
from screens.goals import GoalsScreen
from screens.analytics import AnalyticsScreen  # noqa: F401
from screens.calendar_screen import CalendarScreen  # noqa: F401
from screens.settings import SettingsScreen, CategoryBudgetRow
from screens.expense_detail import ExpenseDetailScreen, MakeRecurringPopup  # noqa: F401
from screens.subscriptions import SubscriptionsScreen  # noqa: F401
from utils.popups import ConfirmPopup  # noqa: F401
from components.nav_bar import NavButton  # noqa: F401

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Register icon font — must happen before KV files are loaded
LabelBase.register(
    'MaterialIcons',
    os.path.join(BASE_DIR, 'assets', 'fonts', 'MaterialIcons-Regular.ttf'),
)

# Expose the category-icon helper to KV expressions globally. Kivy's #:import
# directive resolves an alias to a *module/class attribute on the top-level
# package* — it can't pull a function out of a sub-module. Registering it in
# global_idmap is the canonical way to make a function callable from any KV.
from kivy.lang import global_idmap
from components.category_chip import icon_for_category as _icon_for_category
global_idmap['icon_for_category'] = _icon_for_category

# design_system must load first — every other screen consumes its classes
# (IconButton, BackButton, ScreenHeader, HeaderTitle, etc.).
for kv_file in ['design_system', 'nav_bar', 'home', 'add_expense', 'history', 'goals', 'analytics', 'calendar', 'settings', 'subscriptions', 'expense_detail']:
    Builder.load_file(os.path.join(BASE_DIR, 'kv', f'{kv_file}.kv'))

# Tab order defines slide direction for transitions.
# Root tabs first (left → right as they appear in the bottom navbar), then
# drill-down screens. Opening a drill-down from any root tab slides "left"
# (deeper); back slides right. expense_detail is deepest.
#
# History was demoted from a root tab to a drill-down — reached via Home's
# "See All", Analytics category taps, or Calendar day taps — so it now sits
# alongside add_expense / subscriptions / expense_detail in the drill section.
_SCREEN_ORDER = ['home', 'analytics', 'calendar', 'goals', 'settings',
                 'history', 'add_expense', 'subscriptions', 'expense_detail']


class BudgetApp(App):
    current_screen = StringProperty('home')

    def build(self):
        init_db()
        process_recurring()
        self._slide = SlideTransition(duration=0.22)
        sm = ScreenManager(transition=NoTransition())
        sm.add_widget(HomeScreen(name='home'))
        sm.add_widget(AddExpenseScreen(name='add_expense'))
        sm.add_widget(HistoryScreen(name='history'))
        sm.add_widget(AnalyticsScreen(name='analytics'))
        sm.add_widget(GoalsScreen(name='goals'))
        sm.add_widget(CalendarScreen(name='calendar'))
        sm.add_widget(SettingsScreen(name='settings'))
        sm.add_widget(SubscriptionsScreen(name='subscriptions'))
        sm.add_widget(ExpenseDetailScreen(name='expense_detail'))
        return sm

    def go_to(self, screen_name):
        if screen_name == self.root.current:
            return
        cur = self.root.current
        cur_idx = _SCREEN_ORDER.index(cur) if cur in _SCREEN_ORDER else 0
        nxt_idx = _SCREEN_ORDER.index(screen_name) if screen_name in _SCREEN_ORDER else 0
        self._slide.direction = 'left' if nxt_idx >= cur_idx else 'right'
        self.root.transition = self._slide
        self.current_screen = screen_name
        self.root.current = screen_name

    def open_expense(self, expense_id, return_to=None):
        """Drill into the expense detail page for `expense_id`.

        `return_to` is the screen the back arrow returns to (defaults to the
        currently active screen — so tapping a row in History returns to
        History, tapping in Home returns to Home, etc.)."""
        if return_to is None:
            return_to = self.root.current
        screen = self.root.get_screen('expense_detail')
        screen.set_expense(expense_id, return_to=return_to)
        self.go_to('expense_detail')


if __name__ == '__main__':
    BudgetApp().run()
