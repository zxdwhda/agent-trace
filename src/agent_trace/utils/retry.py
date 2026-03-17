#!/usr/bin/env python3
"""
重试机制工具模块

提供带指数退避的重试装饰器
"""

import time
import logging
from functools import wraps
from typing import Callable, TypeVar, Tuple, Optional

T = TypeVar('T')

logger = logging.getLogger("agent_trace")


def retry_with_backoff(
    max_retries: int = 3,
    initial_delay: float = 1.0,
    max_delay: float = 30.0,
    exponential_base: float = 2.0,
    retryable_exceptions: Tuple[type, ...] = (Exception,),
    on_retry: Optional[Callable[[Exception, int], None]] = None
):
    """
    带指数退避的重试装饰器
    
    Args:
        max_retries: 最大重试次数
        initial_delay: 初始延迟（秒）
        max_delay: 最大延迟（秒）
        exponential_base: 指数基数
        retryable_exceptions: 可重试的异常类型
        on_retry: 重试时的回调函数
    
    Returns:
        装饰器函数
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            delay = initial_delay
            last_exception = None
            
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except retryable_exceptions as e:
                    last_exception = e
                    
                    if attempt >= max_retries:
                        logger.warning(
                            f"{func.__name__} failed after {max_retries + 1} attempts: {e}"
                        )
                        raise
                    
                    if on_retry:
                        try:
                            on_retry(e, attempt + 1)
                        except Exception:
                            pass
                    
                    logger.warning(
                        f"{func.__name__} failed (attempt {attempt + 1}/{max_retries + 1}): {e}. "
                        f"Retrying in {delay:.1f}s..."
                    )
                    
                    time.sleep(delay)
                    delay = min(delay * exponential_base, max_delay)
            
            # 不应该到达这里，但为了类型检查
            raise last_exception if last_exception else RuntimeError("Unexpected error")
        
        return wrapper
    return decorator


def retry_sdk_call(max_retries: int = 3, initial_delay: float = 1.0):
    """
    SDK 调用专用的重试装饰器
    
    适用于 CozeLoop SDK 等可能因网络问题失败的操作
    """
    return retry_with_backoff(
        max_retries=max_retries,
        initial_delay=initial_delay,
        max_delay=10.0,
        exponential_base=2.0,
        retryable_exceptions=(
            ConnectionError,
            TimeoutError,
            OSError,
            Exception,  # 作为兜底，捕获 SDK 可能抛出的各种异常
        )
    )
