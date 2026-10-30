from test.helpers import post_json, save_image


def main() -> None:
    prompt = "A cute orange cat sitting on a chair"
    result = post_json("/v1/images/generations", {"prompt": prompt, "model": "gpt-image-2", "n": 1})
    for index, item in enumerate(result["data"], start=1):
        print(save_image(item["b64_json"], f"generations_{index}"))


if __name__ == "__main__":
    main()
