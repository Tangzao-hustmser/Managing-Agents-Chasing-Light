"""七牛云文件上传路由。"""

from fastapi import APIRouter, Query

from app.services.qiniu_service import get_qiniu_private_download_url, get_qiniu_upload_token

router = APIRouter(prefix="/files", tags=["文件上传"])


@router.get("/qiniu-token")
def fetch_qiniu_token(key: str = Query(default="", description="对象存储 key，可不传")):
    """获取七牛云上传凭证，供前端直传使用。"""
    return get_qiniu_upload_token(key)


@router.get("/qiniu-private-url")
def fetch_qiniu_private_url(
    key: str = Query(..., description="对象存储 key，必传"),
    expire_seconds: int = Query(default=3600, description="链接有效期，单位秒"),
):
    """获取私有空间文件的限时访问 URL。"""
    return get_qiniu_private_download_url(key, expire_seconds)
