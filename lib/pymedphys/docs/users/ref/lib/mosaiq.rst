######
Mosaiq
######

*******
Summary
*******

.. automodule:: pymedphys.mosaiq
    :no-members:

See :doc:`../../tasks/mosaiq` for authorised read-only queries, parameter
binding, result interpretation, credentials, and connection lifetime.



***
API
***

Connect and Query the Mosaiq Database
-------------------------------------

.. autofunction:: pymedphys.mosaiq.connect

.. autofunction:: pymedphys.mosaiq.execute

Connection and cursor lifecycle
-------------------------------

Prefer :func:`pymedphys.mosaiq.connect` to construct a connection with the
documented credential behaviour. Both wrappers support context managers;
leaving the context closes that object. ``execute`` opens and closes its own
cursor, while the caller retains responsibility for the connection.

.. autoclass:: pymedphys.mosaiq.Connection
   :members: cursor, close

.. autoclass:: pymedphys.mosaiq.Cursor
   :members: execute, fetchall, close

Cursor ``execute(query, parameters)`` uses the underlying driver's parameter
binding; ``fetchall()`` returns a list of row tuples. Do not construct SQL by
interpolating patient identifiers or other values into the query string.
