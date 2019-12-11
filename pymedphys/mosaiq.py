# pylint: disable = unused-import, missing-docstring


import apipkg

apipkg.initpkg(
    __name__,
    {
        "connect": "._mosaiq.connect:connect",
        "execute": "._mosaiq.connect:execute_sql",
        "qcls": "._mosaiq.helpers:get_qcls_by_date",
    },
)
