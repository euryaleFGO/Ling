"""
MongoDB 客户端管理模块
"""
from pymongo import MongoClient
from pymongo.database import Database
from typing import Optional
import logging
import platform
import subprocess
import time

logger = logging.getLogger(__name__)


class MongoDBClient:
    """MongoDB 客户端单例"""
    
    _instance: Optional['MongoDBClient'] = None
    _client: Optional[MongoClient] = None
    _db: Optional[Database] = None
    
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(
        self, 
        host: str = "localhost", 
        port: int = 27017, 
        db_name: str = "liying_db"
    ):
        if self._client is None:
            self._host = host
            self._port = port
            self._db_name = db_name
            self._connect()
    
    def _connect(self):
        """建立数据库连接"""
        try:
            self._ensure_service()
            self._client = MongoClient(
                host=self._host,
                port=self._port,
                serverSelectionTimeoutMS=5000
            )
            # 测试连接
            self._client.admin.command('ping')
            self._db = self._client[self._db_name]
            logger.info(f"MongoDB 连接成功: {self._host}:{self._port}/{self._db_name}")
        except Exception as e:
            logger.error(f"MongoDB 连接失败: {e}")
            raise

    def _ensure_service(self):
        try:
            if platform.system() != "Windows":
                return
            if str(self._host) not in ("localhost", "127.0.0.1"):
                return
            names = ["MongoDB", "MongoDB Server", "mongodb"]
            for name in names:
                try:
                    status = subprocess.run([
                        "powershell", "-NoProfile", "-Command",
                        f"(Get-Service -Name '{name}' -ErrorAction SilentlyContinue).Status"
                    ], capture_output=True, text=True, timeout=5)
                    out = (status.stdout or "").strip()
                    if not out:
                        continue
                    if out.lower() != "running":
                        subprocess.run([
                            "powershell", "-NoProfile", "-Command",
                            f"Start-Service -Name '{name}'"
                        ], capture_output=True, text=True, timeout=15)
                        time.sleep(2)
                        status2 = subprocess.run([
                            "powershell", "-NoProfile", "-Command",
                            f"(Get-Service -Name '{name}').Status"
                        ], capture_output=True, text=True, timeout=5)
                        out2 = (status2.stdout or "").strip()
                        if out2.lower() == "running":
                            logger.info("已启动 MongoDB 服务")
                            return
                    else:
                        return
                except Exception:
                    continue
        except Exception:
            pass
    
    @property
    def db(self) -> Database:
        """获取数据库实例"""
        if self._db is None:
            self._connect()
        return self._db
    
    @property
    def client(self) -> MongoClient:
        """获取客户端实例"""
        if self._client is None:
            self._connect()
        return self._client
    
    def get_collection(self, name: str):
        """获取集合"""
        return self.db[name]
    
    def close(self):
        """关闭连接"""
        if self._client:
            self._client.close()
            self._client = None
            self._db = None
            logger.info("MongoDB 连接已关闭")
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


# 全局实例
_mongo_client: Optional[MongoDBClient] = None


def get_mongo_client(
    host: str = "localhost",
    port: int = 27017,
    db_name: str = "liying_db"
) -> MongoDBClient:
    """获取 MongoDB 客户端实例"""
    global _mongo_client
    if _mongo_client is None:
        _mongo_client = MongoDBClient(host, port, db_name)
    return _mongo_client


def get_db() -> Database:
    """获取数据库实例"""
    return get_mongo_client().db
