import ast


def parse_imports(import_directory):

    with open(import_directory.joinpath("imports.py")) as f:
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
