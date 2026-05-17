from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.properties import StringProperty, BooleanProperty, ListProperty


# MaterialIcons codepoints, keyed by canonical category name.
# Built with chr() rather than literal private-use chars or \u escapes —
# the Write/Edit tools strip both. chr(int) survives round-trips cleanly.
CATEGORY_ICON_CODEPOINTS = {
    'Food':          0xe56c,  # restaurant
    'Transport':     0xe531,  # directions_car
    'Shopping':      0xe8cc,  # shopping_cart
    'Bills':         0xe8b0,  # receipt
    'Health':        0xe548,  # local_hospital
    'Entertainment': 0xe333,  # tv
    'Subscriptions': 0xe863,  # autorenew
    'Other':         0xe5d3,  # more_horiz
}
CATEGORY_ICONS = {name: chr(cp) for name, cp in CATEGORY_ICON_CODEPOINTS.items()}

CATEGORY_ICON_DEFAULT   = chr(0xe5d3)  # more_horiz
CATEGORY_ICON_ALL       = chr(0xe5c3)  # apps
CATEGORY_ICON_RECURRING = chr(0xe5d5)  # refresh


def icon_for_category(name):
    return CATEGORY_ICONS.get(name, CATEGORY_ICON_DEFAULT)


class CategoryChip(ButtonBehavior, BoxLayout):
    """Color-coded filter chip: tinted background + outlined border + icon + text.

    Real Python class (not a KV @ dynamic class) so ListProperty defaults are
    proper RGBA tuples - guards against the canvas.before IndexError gotcha
    that bites @-classes with default-empty list properties.
    """
    text   = StringProperty('')
    icon   = StringProperty('')
    accent = ListProperty([0.75, 0.77, 0.95, 1])
    active = BooleanProperty(False)
