import curses

DEFAULT_FG = curses.COLOR_WHITE
DEFAULT_BG = curses.COLOR_BLACK
COLOR_PAIRS = {(10, 10): 0}
COLOR_PAIRS = {}

# colors
black = curses.COLOR_BLACK
blue = curses.COLOR_BLUE
cyan = curses.COLOR_CYAN
green = curses.COLOR_GREEN
magenta = curses.COLOR_MAGENTA
red = curses.COLOR_RED
white = curses.COLOR_WHITE
yellow = curses.COLOR_YELLOW
default = -1

# modes
normal = curses.A_NORMAL
bold = curses.A_BOLD
blink = curses.A_BLINK
reverse = curses.A_REVERSE
underline = curses.A_UNDERLINE
invisible = curses.A_INVIS
dim = curses.A_DIM


def get_color(fg: int, bg: int) -> int:
    """Returns the curses color pair for the given fg/bg combination."""

    key = (fg, bg)
    if key not in COLOR_PAIRS:
        size = len(COLOR_PAIRS)
        try:
            curses.init_pair(size, fg, bg)
        except curses.error:
            # If curses.use_default_colors() failed during the initialization
            # of curses, then using -1 as fg or bg will fail as well, which
            # we need to handle with fallback-defaults:
            if fg == -1:  # -1 is the "default" color
                fg = DEFAULT_FG
            if bg == -1:  # -1 is the "default" color
                bg = DEFAULT_BG

            try:
                curses.init_pair(size, fg, bg)
            except curses.error:
                # If this fails too, colors are probably not supported
                pass
        COLOR_PAIRS[key] = size

    return curses.color_pair(COLOR_PAIRS[key])
