# https://stackoverflow.com/a/10016613/3912576


def to_tuple(a):
    try:
        return tuple(to_tuple(i) for i in a)
    except TypeError:
        return a
