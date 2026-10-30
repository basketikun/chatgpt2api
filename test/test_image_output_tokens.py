import json
import urllib.error
import urllib.request

from test.helpers import BASE_URL, load_auth_key


def main() -> None:
    payload = {
        "prompt": "一只橘猫坐在窗台上，午后阳光，写实摄影",
        "model": "gpt-image-2",
        "n": 1,
        "response_format": "url",
    }
    request = urllib.request.Request(
        BASE_URL + "/v1/images/generations",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {load_auth_key()}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request) as response:
            body = response.read().decode()
    except urllib.error.HTTPError as error:
        body = error.read().decode()
    try:
        print(json.dumps(json.loads(body), ensure_ascii=False, indent=2))
    except json.JSONDecodeError:
        print(body)


if __name__ == "__main__":
    main()
