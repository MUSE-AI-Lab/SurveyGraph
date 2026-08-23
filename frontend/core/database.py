"""
SurveyGraph Frontend - 数据库模块
==================================

使用 aiomysql 实现异步 MySQL 连接池。
"""

import aiomysql
from typing import Optional
from contextlib import asynccontextmanager
import logging

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import DatabaseConfig

logger = logging.getLogger(__name__)

# 全局连接池
_pool: Optional[aiomysql.Pool] = None


async def init_db() -> aiomysql.Pool:
    """
    初始化数据库连接池并创建表结构
    
    Returns:
        aiomysql.Pool: 数据库连接池
    """
    global _pool
    
    if _pool is not None:
        return _pool
    
    logger.info(f"正在连接数据库: {DatabaseConfig.HOST}:{DatabaseConfig.PORT}/{DatabaseConfig.DATABASE}")
    
    _pool = await aiomysql.create_pool(
        host=DatabaseConfig.HOST,
        port=DatabaseConfig.PORT,
        user=DatabaseConfig.USER,
        password=DatabaseConfig.PASSWORD,
        db=DatabaseConfig.DATABASE,
        minsize=DatabaseConfig.POOL_MIN_SIZE,
        maxsize=DatabaseConfig.POOL_MAX_SIZE,
        charset='utf8mb4',
        autocommit=True,
        cursorclass=aiomysql.DictCursor,
    )
    
    logger.info("数据库连接池创建成功")
    
    # 创建表结构
    await create_tables()
    
    return _pool


async def close_db():
    """关闭数据库连接池"""
    global _pool
    
    if _pool is not None:
        _pool.close()
        await _pool.wait_closed()
        _pool = None
        logger.info("数据库连接池已关闭")


async def get_db() -> aiomysql.Pool:
    """
    获取数据库连接池
    
    Returns:
        aiomysql.Pool: 数据库连接池
    """
    global _pool
    
    if _pool is None:
        await init_db()
    
    return _pool


@asynccontextmanager
async def get_connection():
    """
    获取数据库连接的上下文管理器
    
    Usage:
        async with get_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT * FROM users")
                result = await cur.fetchall()
    """
    pool = await get_db()
    conn = await pool.acquire()
    try:
        yield conn
    finally:
        pool.release(conn)


@asynccontextmanager
async def get_cursor():
    """
    获取数据库游标的上下文管理器
    
    Usage:
        async with get_cursor() as cur:
            await cur.execute("SELECT * FROM users")
            result = await cur.fetchall()
    """
    async with get_connection() as conn:
        async with conn.cursor() as cur:
            yield cur


async def create_tables():
    """创建数据库表结构"""
    
    create_users_table = """
    CREATE TABLE IF NOT EXISTS users (
        id INT PRIMARY KEY AUTO_INCREMENT,
        username VARCHAR(50) UNIQUE NOT NULL,
        email VARCHAR(100) UNIQUE NOT NULL,
        password_hash VARCHAR(255) NOT NULL,
        role ENUM('user', 'admin') DEFAULT 'user',
        daily_quota INT DEFAULT 1,
        bonus_quota INT DEFAULT 0,
        invite_code VARCHAR(20) UNIQUE,
        invited_by INT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        INDEX idx_username (username),
        INDEX idx_email (email),
        INDEX idx_invite_code (invite_code)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
    """
    
    create_tasks_table = """
    CREATE TABLE IF NOT EXISTS tasks (
        id INT PRIMARY KEY AUTO_INCREMENT,
        task_id VARCHAR(100) UNIQUE NOT NULL,
        user_id INT NOT NULL,
        topic VARCHAR(500) NOT NULL,
        keywords TEXT,
        status ENUM('pending', 'running', 'paused', 'completed', 'failed') DEFAULT 'pending',
        current_step INT DEFAULT 0,
        current_step_name VARCHAR(50),
        progress_percent INT DEFAULT 0,
        config JSON,
        uploaded_files JSON,
        enable_arxiv_search BOOLEAN DEFAULT TRUE,
        output_dir VARCHAR(500),
        mekg_data_path VARCHAR(500),
        outline_path VARCHAR(500),
        pdf_path VARCHAR(500),
        evaluation_path VARCHAR(500),
        visualization_path VARCHAR(500),
        papers_count INT DEFAULT 0,
        relations_count INT DEFAULT 0,
        sections_count INT DEFAULT 0,
        retry_count INT DEFAULT 0,
        last_retry_date DATE,
        error_message TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        completed_at DATETIME,
        INDEX idx_user_id (user_id),
        INDEX idx_task_id (task_id),
        INDEX idx_status (status),
        INDEX idx_created_at (created_at)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
    """
    
    create_task_logs_table = """
    CREATE TABLE IF NOT EXISTS task_logs (
        id INT PRIMARY KEY AUTO_INCREMENT,
        task_id INT NOT NULL,
        step INT NOT NULL,
        step_name VARCHAR(50),
        level ENUM('info', 'warning', 'error', 'debug') DEFAULT 'info',
        message TEXT,
        details JSON,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_task_id (task_id),
        INDEX idx_step (step),
        INDEX idx_level (level),
        INDEX idx_created_at (created_at)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
    """
    
    create_invitations_table = """
    CREATE TABLE IF NOT EXISTS invitations (
        id INT PRIMARY KEY AUTO_INCREMENT,
        inviter_id INT NOT NULL,
        invitee_id INT NOT NULL,
        invite_code VARCHAR(20) NOT NULL,
        bonus_granted BOOLEAN DEFAULT FALSE,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_inviter_id (inviter_id),
        INDEX idx_invitee_id (invitee_id),
        INDEX idx_invite_code (invite_code)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
    """
    
    # 用户知识库表 - 存储用户与PDF文件的关联关系
    # 注意：这里只存储关联关系，实际文件存储在共享PDF目录中
    # 用户从知识库"删除"文件只是删除关联记录，不删除实际文件
    create_user_knowledge_base_table = """
    CREATE TABLE IF NOT EXISTS user_knowledge_base (
        id INT PRIMARY KEY AUTO_INCREMENT,
        user_id INT NOT NULL,
        filename VARCHAR(255) NOT NULL,
        file_path VARCHAR(500) NOT NULL,
        file_size BIGINT DEFAULT 0,
        file_hash VARCHAR(64),
        title VARCHAR(500),
        description TEXT,
        tags VARCHAR(500),
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        INDEX idx_user_id (user_id),
        INDEX idx_filename (filename),
        INDEX idx_file_hash (file_hash),
        UNIQUE KEY uk_user_file (user_id, file_path)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
    """
    
    async with get_cursor() as cur:
        await cur.execute(create_users_table)
        logger.info("用户表创建/检查完成")
        
        await cur.execute(create_tasks_table)
        logger.info("任务表创建/检查完成")
        
        await cur.execute(create_task_logs_table)
        logger.info("任务日志表创建/检查完成")
        
        await cur.execute(create_invitations_table)
        logger.info("邀请记录表创建/检查完成")
        
        await cur.execute(create_user_knowledge_base_table)
        logger.info("用户知识库表创建/检查完成")


async def execute_query(query: str, params: tuple = None, fetch_one: bool = False):
    """
    执行查询并返回结果
    
    Args:
        query: SQL 查询语句
        params: 查询参数
        fetch_one: 是否只返回一条记录
        
    Returns:
        查询结果
    """
    async with get_cursor() as cur:
        await cur.execute(query, params)
        if fetch_one:
            return await cur.fetchone()
        return await cur.fetchall()


async def execute_insert(query: str, params: tuple = None) -> int:
    """
    执行插入并返回自增ID
    
    Args:
        query: SQL 插入语句
        params: 插入参数
        
    Returns:
        int: 自增ID
    """
    async with get_cursor() as cur:
        await cur.execute(query, params)
        return cur.lastrowid


async def execute_update(query: str, params: tuple = None) -> int:
    """
    执行更新并返回影响的行数
    
    Args:
        query: SQL 更新语句
        params: 更新参数
        
    Returns:
        int: 影响的行数
    """
    async with get_cursor() as cur:
        await cur.execute(query, params)
        return cur.rowcount