import ast

from stdlib_list import stdlib_list
STDLIB = set(stdlib_list())


IMPORT_TYPES = {
    type(ast.parse('import george').body[0]),  # type: ignore
    type(ast.parse('import george as macdonald').body[0])}  # type: ignore

IMPORT_FROM_TYPES = {
    type(ast.parse('from george import macdonald').body[0])  # type: ignore
}

ALL_IMPORT_TYPES = IMPORT_TYPES.union(IMPORT_FROM_TYPES)

CONVERSIONS = {
    'attr': 'attrs',
    'PIL': 'Pillow',
    'Image': 'Pillow',
    'mpl_toolkits': 'matplotlib',
    'dateutil': 'python_dateutil'
}



def get_imports(filepath, internal_packages):
    with open(filepath, 'r') as file:
        data = file.read()

    parsed = ast.parse(data)
    imports = [
        node for node in ast.walk(parsed) if type(node) in ALL_IMPORT_TYPES]

    stdlib_imports = set()
    external_imports = set()
    internal_package_imports = set()
    internal_module_imports = set()
    internal_file_imports = set()

    def get_base_converted_module(name):
        name = name.split('.')[0]

        try:
            name = CONVERSIONS[name]
        except KeyError:
            pass

        return name

    def add_level_0(name):
        if name in STDLIB:
            stdlib_imports.add(name)
        elif name in internal_packages:
            internal_package_imports.add(name)
        else:
            external_imports.add(name)

    for an_import in imports:

        if type(an_import) in IMPORT_TYPES:
            for alias in an_import.names:
                name = get_base_converted_module(alias.name)
                add_level_0(name)

        elif type(an_import) in IMPORT_FROM_TYPES:
            name = get_base_converted_module(an_import.module)
            if an_import.level == 0:
                add_level_0(name)
            elif an_import.level == 1:
                internal_file_imports.add(name)
            else:
                internal_module_imports.add(name)

        else:
            raise TypeError("Unexpected import type")

    return {
        'stdlib': stdlib_imports,
        'external': external_imports,
        'internal_package': internal_package_imports,
        'internal_module': internal_module_imports,
        'internal_file': internal_file_imports
    }
