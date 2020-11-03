# From https://gist.github.com/tvst/036da038ab3e999a64497f42de966a92

"""Hack to add per-session state to Streamlit.
Usage
-----
>>> import SessionState
>>>
>>> session_state = SessionState.get(user_name='', favourite_color='black')
>>> session_state.user_name
''
>>> session_state.user_name = 'Mary'
>>> session_state.favourite_color
'black'
Since you set user_name above, next time your script runs this will be the
result:
>>> session_state = get(user_name='', favourite_color='black')
>>> session_state.user_name
'Mary'
"""
try:
    import streamlit.ReportThread as ReportThread
    from streamlit.server.Server import Server
except ModuleNotFoundError:
    # Streamlit >= 0.65.0
    import streamlit.report_thread as ReportThread
    from streamlit.server.server import Server


class SessionState:
    def __init__(self, **kwargs):
        """A new SessionState object.
        Parameters
        ----------
        **kwargs : any
            Default values for the session state.
        Example
        -------
        >>> session_state = SessionState(user_name='', favourite_color='black')
        >>> session_state.user_name = 'Mary'  # doctest: +SKIP
        ''
        >>> session_state.favourite_color  # doctest: +SKIP
        'black'
        """
        for key, val in kwargs.items():
            setattr(self, key, val)


def get(**kwargs):
    """Gets a SessionState object for the current session.
    Creates a new object if necessary.
    Parameters
    ----------
    **kwargs : any
        Default values you want to add to the session state, if we're creating a
        new one.
    Example
    -------
    >>> session_state = get(user_name='', favourite_color='black')  # doctest: +SKIP
    >>> session_state.user_name  # doctest: +SKIP
    ''
    >>> session_state.user_name = 'Mary'  # doctest: +SKIP
    >>> session_state.favourite_color  # doctest: +SKIP
    'black'
    Since you set user_name above, next time your script runs this will be the
    result:
    >>> session_state = get(user_name='', favourite_color='black')  # doctest: +SKIP
    >>> session_state.user_name  # doctest: +SKIP
    'Mary'
    """
    # Hack to get the session object from Streamlit.

    ctx = ReportThread.get_report_ctx()

    this_session = None

    current_server = Server.get_current()
    if hasattr(current_server, "_session_infos"):
        # Streamlit < 0.56
        session_infos = (
            Server.get_current()._session_infos.values()  # pylint: disable = no-member, protected-access
        )
    else:
        session_infos = (
            Server.get_current()._session_info_by_id.values()  # pylint: disable = protected-access
        )

    for session_info in session_infos:
        s = session_info.session
        if (
            # Streamlit < 0.54.0
            (  # pylint: disable = too-many-boolean-expressions
                hasattr(s, "_main_dg")
                and s._main_dg == ctx.main_dg  # pylint: disable = protected-access
            )
            or
            # Streamlit >= 0.54.0
            (not hasattr(s, "_main_dg") and s.enqueue == ctx.enqueue)
            or
            # Streamlit >= 0.65.2
            (
                not hasattr(s, "_main_dg")
                and s._uploaded_file_mgr  # pylint: disable = protected-access
                == ctx.uploaded_file_mgr
            )
        ):
            this_session = s

    if this_session is None:
        raise RuntimeError(
            "Oh noes. Couldn't get your Streamlit Session object. "
            "Are you doing something fancy with threads?"
        )

    # Got the session object! Now let's attach some state into it.

    if not hasattr(this_session, "_custom_session_state"):
        this_session._custom_session_state = SessionState(  # pylint: disable = protected-access
            **kwargs
        )

    return this_session._custom_session_state  # pylint: disable = protected-access
