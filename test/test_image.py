from __future__ import annotations

from services.protocol import openai_v1_image_generations
from test.helpers import save_image


def main() -> None:
    prompt = "一只橘猫坐在窗台上，午后阳光，写实摄影"
    data = openai_v1_image_generations.handle({"prompt": prompt, "model": "gpt-5-3", "n": 1})
    for index, item in enumerate(data["data"], start=1):
        print(save_image(item["b64_json"], f"image_{index}"))


if __name__ == "__main__":
    main()
