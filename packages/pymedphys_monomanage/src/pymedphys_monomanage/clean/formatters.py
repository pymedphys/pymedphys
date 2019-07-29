import black


def blacken_str(string_to_format, mode=None):
    if mode is None:
        mode = black.FileMode()

    return black.format_str(string_to_format, mode=mode)
