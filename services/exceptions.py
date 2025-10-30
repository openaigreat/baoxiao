class ServiceError(Exception):
    """服务层基础异常类"""
    pass

class DatabaseError(ServiceError):
    """数据库相关异常"""
    pass

class ValidationError(ServiceError):
    """数据验证相关异常"""
    pass

class FileProcessingError(ServiceError):
    """文件处理相关异常"""
    pass