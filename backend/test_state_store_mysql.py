import json
import sys
import types
import unittest
from unittest.mock import patch

from state_store import MySQLStateStore, create_state_store


class FakeOperationalError(Exception):
    pass


class FakeCursor:
    def __init__(self, driver):
        self.driver = driver
        self.result = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def execute(self, sql, params=None):
        normalized = " ".join(sql.split())
        self.driver.queries.append((normalized, params))
        if normalized.startswith("SELECT state_json"):
            self.result = (self.driver.payload,) if self.driver.payload is not None else None
        elif normalized == "SELECT 1":
            self.result = (1,)
        elif normalized.startswith("INSERT INTO"):
            self.driver.payload = params[1]

    def fetchone(self):
        return self.result


class FakeConnection:
    def __init__(self, driver):
        self.driver = driver

    def cursor(self):
        return FakeCursor(self.driver)

    def commit(self):
        self.driver.commits += 1

    def rollback(self):
        self.driver.rollbacks += 1

    def close(self):
        self.driver.closes += 1


class FakePyMySQL(types.ModuleType):
    def __init__(self):
        super().__init__("pymysql")
        self.err = types.SimpleNamespace(OperationalError=FakeOperationalError)
        self.queries = []
        self.connect_calls = []
        self.payload = None
        self.commits = 0
        self.rollbacks = 0
        self.closes = 0

    def connect(self, **kwargs):
        self.connect_calls.append(kwargs)
        return FakeConnection(self)


class MySQLStateStoreTests(unittest.TestCase):
    def build_store(self, driver):
        with patch.dict(sys.modules, {"pymysql": driver}):
            return MySQLStateStore(
                "10.0.0.8:3306",
                "pinco_app",
                "secret",
                "pinco",
                "pinco_state",
                lambda: {"users": {}, "events": []},
            )

    def test_creates_table_and_round_trips_unicode_state(self):
        driver = FakePyMySQL()
        store = self.build_store(driver)

        self.assertTrue(any("CREATE TABLE IF NOT EXISTS `pinco_state`" in sql for sql, _ in driver.queries))
        self.assertEqual(store.load(), {"users": {}, "events": []})

        expected = {"users": {"u1": {"name": "甜甜"}}, "events": ["测试"]}
        store.save(expected)
        self.assertEqual(json.loads(driver.payload), expected)
        self.assertEqual(store.load(), expected)

        health = store.health()
        self.assertEqual(health["backend"], "mysql")
        self.assertTrue(health["durable"])
        self.assertTrue(health["online"])

    def test_factory_requires_cloud_hosting_mysql_variables(self):
        with self.assertRaisesRegex(RuntimeError, "MYSQL_ADDRESS.*MYSQL_USERNAME.*MYSQL_PASSWORD"):
            create_state_store(
                backend="mysql",
                file_path="/tmp/unused.json",
                default_factory=lambda: {},
            )

    def test_rejects_invalid_address_and_identifiers(self):
        driver = FakePyMySQL()
        with patch.dict(sys.modules, {"pymysql": driver}):
            with self.assertRaisesRegex(RuntimeError, "host:port"):
                MySQLStateStore("invalid", "user", "password", "pinco", "state", dict)
            with self.assertRaisesRegex(RuntimeError, "MYSQL_DATABASE"):
                MySQLStateStore("db:3306", "user", "password", "pinco-prod", "state", dict)


if __name__ == "__main__":
    unittest.main()
