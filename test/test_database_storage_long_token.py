from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from services.storage.database_storage import AccountModel, DatabaseStorageBackend


def test_accounts_access_token_uses_unbounded_text_for_postgresql():
    ddl = str(CreateTable(AccountModel.__table__).compile(dialect=postgresql.dialect()))

    assert "access_token TEXT" in ddl
    assert "VARCHAR(2048)" not in ddl


def test_save_accounts_accepts_access_token_longer_than_2048(tmp_path):
    backend = DatabaseStorageBackend(f"sqlite:///{tmp_path / 'accounts.db'}")
    access_token = "a" * 2055

    backend.save_accounts([{"access_token": access_token, "name": "long token"}])

    [account] = backend.load_accounts()
    assert account["access_token"] == access_token
