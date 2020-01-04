from setuptools import setup

setup(
    name="mosaiq_transfer_check",
    version="0.2.0",
    author="Simon Biggs",
    author_email="mail@simonbiggs.net",
    description="Compare mosaiq entries for two different sites.",
    packages=["mosaiq_transfer_check"],
    entry_points={
        "console_scripts": ["mosaiq_transfer_check=mosaiq_transfer_check:main"]
    },
    license="AGPL3+",
    install_requires=[
        "numpy",
        "pandas",
        "jinja2",
        "IPython",
        "csv_compare",
        "mosaiq_connection",
        "mosaiq_field_export",
        "notebook",
    ],
    include_package_data=True,
)
