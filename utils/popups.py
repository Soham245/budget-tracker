import os

from kivy.properties import ListProperty, StringProperty
from kivy.uix.modalview import ModalView


# Asset path for a fully transparent 1×1 PNG — used as ModalView `background`
# so Kivy's default BorderImage chrome renders nothing and our own rounded
# card surface (drawn in canvas.before) is the only visible modal.
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRANSPARENT_BG = os.path.join(_BASE_DIR, 'assets', 'transparent.png')


class AppModal(ModalView):
    """Base class for every in-app modal/dialog.

    Subclasses ModalView (not Popup) to skip Popup's title-bar + separator
    chrome entirely — the inner content is a direct child anchored center.

    Layering, made explicit (Kivy 2.x ModalView):
      1. `overlay_color` — full-window rectangle drawn BEHIND the popup.
         This is the backdrop dim. We use soft navy translucent so the page
         behind feels subdued without going pure black (Kivy's default is
         [0, 0, 0, 0.7] — too harsh against the app's navy theme and the
         source of the "muddy popup" perception in earlier builds).
      2. `background` / `background_color` — BorderImage drawn at popup size.
         We point `background` at a fully-transparent PNG and keep
         `background_color` neutral white so this layer renders nothing.
      3. `<AppModal>:` canvas.before — our own opaque RoundedRectangle card
         surface, drawn at popup size at full alpha. THIS is the visible
         modal. Because it has alpha=1 it is NEVER blended with the dim
         overlay underneath; the popup stays crisp.
      4. Children — modal content (title, fields, buttons).

    The dim affects ONLY layer 1; layers 3 and 4 sit fully opaque on top.

    Kivy's built-in ModalView fade-in provides modal entry — no custom
    motion is layered on top, keeping things lightweight."""

    def __init__(self, **kwargs):
        kwargs.setdefault('background', TRANSPARENT_BG)
        # Neutral tint — the BorderImage is transparent, so this just avoids
        # any accidental color cast on the (invisible) popup chrome layer.
        kwargs.setdefault('background_color', [1, 1, 1, 1])
        # Backdrop dim — soft navy translucent, 55% alpha. Applied ONLY to
        # the window-sized overlay rectangle that sits behind the popup
        # card. The card itself (drawn by <AppModal>: canvas.before) is
        # fully opaque, so the dim never washes over the modal content.
        kwargs.setdefault('overlay_color', [0.02, 0.03, 0.08, 0.55])
        kwargs.setdefault('auto_dismiss', True)
        super().__init__(**kwargs)


class ConfirmPopup(AppModal):
    """Compact centered confirmation dialog.

    Used app-wide for destructive confirmations (delete goal, delete expense,
    etc.). Pass a short message and an `on_confirm` callback."""

    title_text = StringProperty('Confirm')
    message = StringProperty('')
    confirm_label = StringProperty('Delete')
    confirm_color = ListProperty([0.78, 0.36, 0.36, 1])

    def __init__(self, message, on_confirm, title='Confirm', **kwargs):
        super().__init__(**kwargs)
        self.title_text = title
        self.message = message
        self._on_confirm = on_confirm

    def confirm(self):
        self._on_confirm()
        self.dismiss()
