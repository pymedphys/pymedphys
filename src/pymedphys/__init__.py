# import importlib
# import os
# from glob import glob

# HERE = os.path.dirname(__file__)

# module_abs_paths = glob("{}/level*/*.py".format(HERE))
# module_rel_paths = [
#     ".{}".format(
#         os.path.relpath(module_abs_path, HERE).replace(os.sep, '.')[:-3]
#     )
#     for module_abs_path in module_abs_paths
#     if os.path.isfile(module_abs_path) and
#     not module_abs_path.endswith('__init__.py')
# ]

# module_names = [
#     module_rel_path.split(".")[-1]
#     for module_rel_path in module_rel_paths
# ]

# import_dict = {
#     name: importlib.import_module(path, package=__name__)
#     for name, path in zip(module_names, module_rel_paths)
# }

# globals().update(import_dict)
