import asyncio
import json

from fastapi.exceptions import RequestValidationError

from app.main import validation_error


def test_validation_is_specific_and_does_not_echo_input():
    error = RequestValidationError(
        [
            {
                "loc": ("body", "lng"),
                "type": "less_than_equal",
                "ctx": {"le": 180},
                "input": "secret",
            },
            {
                "loc": ("body", "password"),
                "type": "string_too_short",
                "ctx": {"min_length": 8},
                "input": "secret",
            },
        ]
    )
    response = asyncio.run(validation_error(None, error))
    message = json.loads(response.body)["message"]
    assert "经度：必须小于等于 180" in message
    assert "密码：最少字符数为 8" in message
    assert "secret" not in message
