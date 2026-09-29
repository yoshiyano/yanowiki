"""API のエラーの種類と HTTP ステータスの対応。

表は Wiki の「API 設計 > エラーの形」を正とする。
"""

STATUS = {
    "bad_path": 400,
    "bad_name": 400,
    "bad_request": 400,
    "not_found": 404,
    "forbidden": 403,
    "unsupported": 403,
    "bad_origin": 403,
    "exists": 409,
    "into_self": 409,
    "internal": 500,
}


class ApiError(Exception):
    """画面へそのまま返してよいエラー。message は操作者が読む文。"""

    def __init__(self, code: str, message: str, path: str | None = None):
        assert code in STATUS, code
        super().__init__(message)
        self.code = code
        self.message = message
        self.path = path

    @property
    def status(self) -> int:
        return STATUS[self.code]

    def to_json(self) -> dict:
        err = {"code": self.code, "message": self.message}
        if self.path is not None:
            err["path"] = self.path
        return {"error": err}
