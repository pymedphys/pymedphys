import ast


def parse_imports(filepath):
    """Formulate a dictionary of imports within a python file for usage by ``apipkg``.

    Parameters
    ----------
    filepath
        The python file containing the imports to be parsed.

    Returns
    -------
    imports_for_apipkg
        A dictionary of imports in the format expected by ``apipkg``.

    """
    with open(filepath) as f:
        imports_string = f.read()

    imports_for_apipkg = {}

    for node in ast.parse(imports_string).body:
        if not isinstance(node, ast.Import):
            raise ValueError("Only direct import statements are supported")

        aliases = list(node.names)
        if len(aliases) != 1:
            raise ValueError("Only one alias per import supported")

        alias = aliases[0]
        asname = alias.asname

        if asname is None:
            asname = alias.name

        imports_for_apipkg[asname] = alias.name

    return imports_for_apipkg
