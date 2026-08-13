"""Persistence adapters for Pinco's small-beta state.

The JSON adapter is intentionally development-only. Cloud deployments should use
one of the durable database stores so container restarts do not silently erase
user progress.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from abc import ABC, abstractmethod
from copy import deepcopy
from typing import Any, Callable, Dict, Optional


State = Dict[str, Any]


class StateStore(ABC):
    backend_name = "unknown"
    durable = False

    @abstractmethod
    def load(self) -> State:
        raise NotImplementedError

    @abstractmethod
    def save(self, state: State) -> None:
        raise NotImplementedError

    def health(self) -> Dict[str, Any]:
        return {
            "backend": self.backend_name,
            "durable": self.durable,
            "online": True,
            "detail": "状态仓库可用",
        }


class JsonFileStateStore(StateStore):
    backend_name = "file"
    durable = False

    def __init__(self, file_path: str, default_factory: Callable[[], State]):
        self.file_path = file_path
        self.default_factory = default_factory

    def load(self) -> State:
        os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
        if not os.path.exists(self.file_path):
            return deepcopy(self.default_factory())
        with open(self.file_path, "r", encoding="utf-8") as file:
            return json.load(file)

    def save(self, state: State) -> None:
        directory = os.path.dirname(self.file_path)
        os.makedirs(directory, exist_ok=True)
        fd, temp_path = tempfile.mkstemp(prefix="pinco-state-", suffix=".json", dir=directory)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as file:
                json.dump(state, file, ensure_ascii=False, indent=2)
                file.flush()
                os.fsync(file.fileno())
            os.replace(temp_path, self.file_path)
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    def health(self) -> Dict[str, Any]:
        return {
            "backend": self.backend_name,
            "durable": False,
            "online": True,
            "detail": "仅保存在容器文件中；适合本地开发，不支持云端重启持久化",
        }


class MongoStateStore(StateStore):
    backend_name = "mongodb"
    durable = True

    def __init__(
        self,
        uri: str,
        database: str,
        collection: str,
        default_factory: Callable[[], State],
    ):
        try:
            from pymongo import MongoClient
        except ImportError as error:  # pragma: no cover - depends on deployment image
            raise RuntimeError("已选择 MongoDB 状态仓库，但 pymongo 未安装") from error

        self.default_factory = default_factory
        self.client = MongoClient(uri, serverSelectionTimeoutMS=5000, connectTimeoutMS=5000)
        self.collection = self.client[database][collection]

    def load(self) -> State:
        document = self.collection.find_one({"_id": "pinco_state"})
        if not document:
            return deepcopy(self.default_factory())
        document.pop("_id", None)
        return document

    def save(self, state: State) -> None:
        document = deepcopy(state)
        document["_id"] = "pinco_state"
        self.collection.replace_one({"_id": "pinco_state"}, document, upsert=True)

    def health(self) -> Dict[str, Any]:
        try:
            self.client.admin.command("ping")
            return {
                "backend": self.backend_name,
                "durable": True,
                "online": True,
                "detail": "MongoDB 持久化连接正常",
            }
        except Exception as error:
            return {
                "backend": self.backend_name,
                "durable": True,
                "online": False,
                "detail": f"MongoDB 连接失败：{type(error).__name__}",
            }


class MySQLStateStore(StateStore):
    """Durable store backed by the MySQL bundled with WeChat Cloud Hosting.

    Pinco's beta state is currently one JSON document. Keeping that document in
    a single row preserves the existing state contract while moving it off the
    container filesystem. The table is created automatically; the database is
    created automatically only when the configured account has permission.
    """

    backend_name = "mysql"
    durable = True

    def __init__(
        self,
        address: str,
        username: str,
        password: str,
        database: str,
        table: str,
        default_factory: Callable[[], State],
    ):
        try:
            import pymysql
        except ImportError as error:  # pragma: no cover - depends on deployment image
            raise RuntimeError("已选择 MySQL 状态仓库，但 PyMySQL 未安装") from error

        self.pymysql = pymysql
        self.host, self.port = self._parse_address(address)
        self.username = username
        self.password = password
        self.database = self._validated_identifier(database, "MYSQL_DATABASE")
        self.table = self._validated_identifier(table, "MYSQL_STATE_TABLE")
        self.default_factory = default_factory
        self._ensure_schema()

    @staticmethod
    def _parse_address(address: str) -> tuple[str, int]:
        host, separator, port_text = address.strip().rpartition(":")
        if not separator or not host or not port_text.isdigit():
            raise RuntimeError("MYSQL_ADDRESS 必须是 host:port 格式")
        port = int(port_text)
        if port < 1 or port > 65535:
            raise RuntimeError("MYSQL_ADDRESS 端口无效")
        return host, port

    @staticmethod
    def _validated_identifier(value: str, label: str) -> str:
        normalized = value.strip()
        if not re.fullmatch(r"[A-Za-z0-9_]+", normalized):
            raise RuntimeError(f"{label} 只能包含字母、数字和下划线")
        return normalized

    def _connect(self, *, with_database: bool = True):
        kwargs = {
            "host": self.host,
            "port": self.port,
            "user": self.username,
            "password": self.password,
            "charset": "utf8mb4",
            "connect_timeout": 5,
            "read_timeout": 10,
            "write_timeout": 10,
            "autocommit": False,
        }
        if with_database:
            kwargs["database"] = self.database
        return self.pymysql.connect(**kwargs)

    def _ensure_schema(self) -> None:
        try:
            connection = self._connect()
        except self.pymysql.err.OperationalError as error:
            if not error.args or error.args[0] != 1049:
                raise
            # The bundled Cloud Hosting account is commonly an administrator on
            # first setup. If it is not, the operator can create the database in
            # the console and grant the application account access, then retry.
            connection = self._connect(with_database=False)
            try:
                with connection.cursor() as cursor:
                    cursor.execute(
                        f"CREATE DATABASE IF NOT EXISTS `{self.database}` "
                        "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                    )
                connection.commit()
            finally:
                connection.close()
            connection = self._connect()

        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS `{self.table}` (
                        state_key VARCHAR(64) NOT NULL PRIMARY KEY,
                        state_json LONGTEXT NOT NULL,
                        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                            ON UPDATE CURRENT_TIMESTAMP
                    ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
                    """
                )
            connection.commit()
        finally:
            connection.close()

    def load(self) -> State:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"SELECT state_json FROM `{self.table}` WHERE state_key=%s",
                    ("pinco_state",),
                )
                row = cursor.fetchone()
        finally:
            connection.close()
        if not row:
            return deepcopy(self.default_factory())
        return json.loads(row[0])

    def save(self, state: State) -> None:
        payload = json.dumps(state, ensure_ascii=False, separators=(",", ":"))
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    INSERT INTO `{self.table}` (state_key, state_json)
                    VALUES (%s, %s)
                    ON DUPLICATE KEY UPDATE state_json=VALUES(state_json)
                    """,
                    ("pinco_state", payload),
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def health(self) -> Dict[str, Any]:
        try:
            connection = self._connect()
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT 1")
                    cursor.fetchone()
            finally:
                connection.close()
            return {
                "backend": self.backend_name,
                "durable": True,
                "online": True,
                "detail": "微信云托管 MySQL 持久化连接正常",
            }
        except Exception as error:
            return {
                "backend": self.backend_name,
                "durable": True,
                "online": False,
                "detail": f"MySQL 连接失败：{type(error).__name__}",
            }


def create_state_store(
    *,
    backend: str,
    file_path: str,
    default_factory: Callable[[], State],
    mongo_uri: Optional[str] = None,
    mongo_database: str = "pinco",
    mongo_collection: str = "app_state",
    mysql_address: Optional[str] = None,
    mysql_username: Optional[str] = None,
    mysql_password: Optional[str] = None,
    mysql_database: str = "pinco",
    mysql_table: str = "pinco_state",
) -> StateStore:
    normalized = backend.strip().lower()
    if normalized == "mongodb":
        if not mongo_uri:
            raise RuntimeError("PINCO_STATE_BACKEND=mongodb 时必须配置 MONGODB_URI")
        return MongoStateStore(mongo_uri, mongo_database, mongo_collection, default_factory)
    if normalized == "mysql":
        missing = [
            name
            for name, value in {
                "MYSQL_ADDRESS": mysql_address,
                "MYSQL_USERNAME": mysql_username,
                "MYSQL_PASSWORD": mysql_password,
            }.items()
            if not value
        ]
        if missing:
            raise RuntimeError(
                "PINCO_STATE_BACKEND=mysql 时缺少环境变量：" + "、".join(missing)
            )
        return MySQLStateStore(
            mysql_address,
            mysql_username,
            mysql_password,
            mysql_database,
            mysql_table,
            default_factory,
        )
    if normalized != "file":
        raise RuntimeError(f"不支持的 PINCO_STATE_BACKEND：{backend}")
    return JsonFileStateStore(file_path, default_factory)
