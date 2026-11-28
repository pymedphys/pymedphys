from pymedphys._imports import dbfread


def get_dbf_table(path):
    # Clinical DBF records must not be cached across Streamlit sessions.
    try:
        return dbfread.DBF(path)
    except dbfread.DBFNotFound:
        # Paths may include patient identifiers: keep them out of the exception.
        raise FileNotFoundError("DBF table could not be opened") from None
