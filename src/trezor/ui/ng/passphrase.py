from micropython import const

from trezor import io, loop, res, ui
from trezor.ui import display
from trezor.ui.ng.button import Button, ButtonClear, ButtonConfirm
from trezor.ui.ng.swipe import SWIPE_HORIZONTAL, SWIPE_LEFT, Swipe

SPACE = res.load(ui.ICON_SPACE)

KEYBOARD_KEYS = (
    ("1", "2", "3", "4", "5", "6", "7", "8", "9", "0"),
    (SPACE, "abc", "def", "ghi", "jkl", "mno", "pqrs", "tuv", "wxyz", "*#"),
    (SPACE, "ABC", "DEF", "GHI", "JKL", "MNO", "PQRS", "TUV", "WXYZ", "*#"),
    ("_<>", ".:@", "/|\\", "!()", "+%&", "-[]", "?{}", ",'`", ';"~', "$^="),
)


def digit_area(i):
    if i == 9:  # 0-position
        i = 10  # display it in the middle
    return ui.grid(i + 3)  # skip the first line


def render_scrollbar(page):
    bbox = const(240)
    size = const(8)
    padding = 12
    page_count = len(KEYBOARD_KEYS)

    if page_count * padding > bbox:
        padding = bbox // page_count

    x = (bbox // 2) - (page_count // 2) * padding
    y = 44

    for i in range(0, page_count):
        if i != page:
            ui.display.bar_radius(
                x + i * padding, y, size, size, ui.DARK_GREY, ui.BG, size // 2
            )
    ui.display.bar_radius(x + page * padding, y, size, size, ui.FG, ui.BG, size // 2)


class KeyButton(Button):
    def __init__(self, area, content, keyboard):
        self.keyboard = keyboard
        super().__init__(area, content)

    def on_click(self):
        self.keyboard.on_key_click(self)

    def get_text_content(self):
        if self.content is SPACE:
            return " "
        else:
            return self.content


def key_buttons(keys, keyboard):
    return [KeyButton(digit_area(i), k, keyboard) for i, k in enumerate(keys)]


class Input(Button):
    def __init__(self, area, content):
        super().__init__(area, content)
        self.pending = False
        self.disable()

    def edit(self, content, pending):
        self.content = content
        self.pending = pending
        self.dirty = True

    def render_content(self, s, ax, ay, aw, ah):
        text_style = s.text_style
        fg_color = s.fg_color
        bg_color = s.bg_color

        p = self.pending  # should we draw the pending marker?
        t = self.content  # input content

        tx = ax + 24  # x-offset of the content
        ty = ay + ah // 2 + 8  # y-offset of the content
        maxlen = const(14)  # maximum text length

        # input content
        if len(t) > maxlen:
            t = "<" + t[-maxlen:]  # too long, align to the right
        width = display.text_width(t, text_style)
        display.text(tx, ty, t, text_style, fg_color, bg_color)

        if p:  # pending marker
            pw = display.text_width(t[-1:], text_style)
            px = tx + width - pw
            display.bar(px, ty + 2, pw + 1, 3, fg_color)
        else:  # cursor
            cx = tx + width + 1
            display.bar(cx, ty - 18, 2, 22, fg_color)

    def on_click(self):
        pass


class Prompt(ui.Control):
    def __init__(self, text):
        self.text = text
        self.dirty = True

    def on_render(self):
        if self.dirty:
            display.bar(0, 0, ui.WIDTH, 48, ui.BG)
            display.text_center(ui.WIDTH // 2, 32, self.text, ui.BOLD, ui.GREY, ui.BG)
            self.dirty = False


CANCELLED = const(0)


class PassphraseKeyboard(ui.Control):
    def __init__(self, prompt, page=1):
        self.page = page
        self.prompt = Prompt(prompt)

        self.input = Input(ui.grid(0, n_x=1, n_y=6), "")

        self.back = Button(ui.grid(12), res.load(ui.ICON_BACK), ButtonClear)
        self.back.on_click = self.on_back_click

        self.done = Button(ui.grid(14), res.load(ui.ICON_CONFIRM), ButtonConfirm)
        self.done.on_click = self.on_confirm

        self.keys = key_buttons(KEYBOARD_KEYS[self.page], self)
        self.pending_button = None
        self.pending_index = 0

    def dispatch(self, event, x, y):
        if self.input.content:
            self.input.dispatch(event, x, y)
        else:
            self.prompt.dispatch(event, x, y)
        self.back.dispatch(event, x, y)
        self.done.dispatch(event, x, y)
        for btn in self.keys:
            btn.dispatch(event, x, y)

        if event == ui.RENDER:
            render_scrollbar(self.page)

    def on_back_click(self):
        # Backspace was clicked.  If we have any content in the input, let's
        # delete the last character.  Otherwise cancel.
        content = self.input.content
        if content:
            self.edit(content[:-1])
        else:
            self.on_cancel()

    def on_key_click(self, button: KeyButton):
        # Key button was clicked.  If this button is pending, let's cycle the
        # pending character in input.  If not, let's just append the first
        # character.
        text = button.get_text_content()
        if self.pending_button is button:
            index = (self.pending_index + 1) % len(text)
            content = self.input.content[:-1] + text[index]
            pending_button = button
        else:
            index = 0
            content = self.input.content + text[0]
            if len(text) > 1:
                pending_button = button
            else:
                pending_button = None
        self.edit(content, pending_button, index)

    def on_timeout(self):
        # Timeout occurred, let's just reset the pending marker.
        self.edit(self.input.content)

    def edit(self, content: str, button: Button = None, index: int = 0):
        self.pending_button = button
        self.pending_index = index

        # modify the input state
        pending = button is not None
        self.input.edit(content, pending)

        if content:
            self.back.enable()
        else:
            self.back.disable()
            self.prompt.dirty = True

    async def __iter__(self):
        try:
            while True:
                spawn_render = self.spawn_render()
                spawn_input = self.spawn_input()
                spawn_paging = self.spawn_paging()
                await loop.spawn(spawn_render, spawn_input, spawn_paging)
        except ui.Result as result:
            return result.value

    # @ui.layout
    async def spawn_input(self):
        touch = loop.wait(io.TOUCH)
        timeout = loop.sleep(1000 * 1000 * 1)
        spawn_touch = loop.spawn(touch)
        spawn_timeout = loop.spawn(touch, timeout)

        while True:
            if self.pending_button is not None:
                spawn = spawn_timeout
            else:
                spawn = spawn_touch
            result = await spawn

            if touch in spawn.finished:
                event, x, y = result
                self.dispatch(event, x, y)
            else:
                self.on_timeout()

    async def spawn_paging(self):
        swipe = await Swipe(directions=SWIPE_HORIZONTAL)
        if swipe == SWIPE_LEFT:
            self.page = (self.page + 1) % len(KEYBOARD_KEYS)
        else:
            self.page = (self.page - 1) % len(KEYBOARD_KEYS)
        self.keys = key_buttons(KEYBOARD_KEYS[self.page], self)
        self.back.dirty = True
        self.done.dirty = True
        self.input.dirty = True
        self.prompt.dirty = True

    def on_cancel(self):
        pass

    def on_confirm(self):
        pass
