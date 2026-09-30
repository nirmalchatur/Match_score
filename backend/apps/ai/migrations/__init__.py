"""
Migrations for the AI app.

The app was a plain package -- provider abstraction, schemas, validators -- with
no models, so it had no migration package either. It gained one when ``AIRun``
landed: the audit table has to exist for the record to mean anything.
"""
