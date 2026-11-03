"""Print the API's OpenAPI document; the frontend generates its client from it.

uv run python -m bloomberg_invest.api.openapi > ../frontend/src/api/openapi.json
"""

import json

from bloomberg_invest.api.app import create_app


def main() -> None:
    print(json.dumps(create_app().openapi(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
