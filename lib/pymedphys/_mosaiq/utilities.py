def separate_server_port_string(sql_server_and_port):
    """separates a server:port string

    Parameters
    ----------
    sql_server_and_port : str
        the server:port string

    Returns
    -------
    tuple
        server (str) and port number

    Raises
    ------
    ValueError
        if the string isn't properly formatted
    """
    split_tuple = str(sql_server_and_port).split(":")
    if len(split_tuple) == 1:
        server = split_tuple[0]
        port = 1433
    elif len(split_tuple) == 2:
        server, port = split_tuple
    else:
        raise ValueError(
            "Only one : should appear in server name,"
            " and it should be used to divide hostname from port number"
        )

    return server, port
