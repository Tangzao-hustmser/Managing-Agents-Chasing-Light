"""七牛云相关服务：上传凭证与私有访问链接。"""

from qiniu import Auth

from app.config import settings


def get_qiniu_upload_token(key: str = "") -> dict:
    """生成七牛云上传 Token，并返回前端直传所需参数。"""
    if not all([settings.qiniu_access_key, settings.qiniu_secret_key, settings.qiniu_bucket]):
        return {
            "enabled": False,
            "message": "七牛云未配置，请在 .env 中补充 QINIU_* 参数",
        }

    q = Auth(settings.qiniu_access_key, settings.qiniu_secret_key)
    token = q.upload_token(settings.qiniu_bucket, key, settings.qiniu_upload_token_expire)
    return {
        "enabled": True,
        "upload_token": token,
        "bucket": settings.qiniu_bucket,
        "key": key,
        "domain": settings.qiniu_domain,
        "expire_seconds": settings.qiniu_upload_token_expire,
    }


def get_qiniu_private_download_url(key: str, expire_seconds: int = 3600) -> dict:
    """为私有空间对象生成可限时访问的下载 URL。"""
    if not all(
        [
            settings.qiniu_access_key,
            settings.qiniu_secret_key,
            settings.qiniu_bucket,
            settings.qiniu_domain,
        ]
    ):
        return {
            "enabled": False,
            "message": "七牛云未完整配置，请检查 QINIU_* 参数",
        }
    if not key:
        return {"enabled": False, "message": "key 不能为空"}

    q = Auth(settings.qiniu_access_key, settings.qiniu_secret_key)
    # 使用域名 + key 生成基础资源链接，再签名成私有下载链接。
    base_url = f"{settings.qiniu_domain.rstrip('/')}/{key.lstrip('/')}"
    private_url = q.private_download_url(base_url, expires=expire_seconds)
    return {
        "enabled": True,
        "bucket": settings.qiniu_bucket,
        "key": key,
        "expires_in": expire_seconds,
        "private_url": private_url,
    }
