from functools import wraps


def sync_log_decorator(module_logger):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            res = func(*args, **kwargs)
            log_args = args[1:] if args and hasattr(args[0], func.__name__) else args
            args_str = ", ".join(map(str, log_args))
            kwargs_str = ", ".join(f"{k}={v}" for k, v in kwargs.items())
            module_logger.info(f"{func.__name__}({args_str}{', ' if kwargs_str else ''}{kwargs_str} {res=})")
            return res

        return wrapper

    return decorator


def async_log_decorator(module_logger):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            res = await func(*args, **kwargs)
            log_args = args[1:] if args and hasattr(args[0], func.__name__) else args
            args_str = ", ".join(map(str, log_args))
            kwargs_str = ", ".join(f"{k}={v}" for k, v in kwargs.items())
            module_logger.info(f"{func.__name__}({args_str}{', ' if kwargs_str else ''}{kwargs_str} {res=})")
            return res

        return wrapper

    return decorator
