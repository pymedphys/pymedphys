import pymssql


@pytest.mark.msq_db
def test_can_we_db():
    conn = pymssql.connect(".", user="sa", password="passWord123")
    cursor = conn.cursor()
    cursor.execute("select * from sys.databases")

    # should print the four system databases
    databases = list(cursor)
    print(databases)

    # and check that the correct number are present
    assert len(databases) == 4
