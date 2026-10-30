from test.helpers import post_json


def main() -> None:
    result = post_json(
        "/v1/images/generations",
        {
            "prompt": "一只橘猫坐在窗边，午后阳光，写实摄影",
            "model": "gpt-image-2",
            "n": 1,
            "response_format": "url",
        },
    )
    for item in result.get("data", []):
        print(item.get("url", ""))


if __name__ == "__main__":
    main()
