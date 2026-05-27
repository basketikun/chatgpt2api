from openai.types.chat.chat_completion_chunk import ChatCompletionChunk
import json

data = {
    "id": "chatcmpl-123",
    "object": "chat.completion.chunk",
    "created": 1234567890,
    "model": "gpt-4",
    "choices": [
        {
            "index": 0,
            "delta": {
                "role": "assistant",
                "tool_calls": [
                    {
                        "index": 0,
                        "id": "xml_stream_0",
                        "type": "function",
                        "function": {
                            "name": "GetLiveContext",
                            "arguments": "{}"
                        }
                    }
                ]
            },
            "finish_reason": None
        }
    ]
}

chunk = ChatCompletionChunk.model_validate(data)
tool_call = chunk.choices[0].delta.tool_calls[0]
print(f"ID: {tool_call.id}")
print(f"Name: {tool_call.function.name if tool_call.function else 'None'}")
print(f"Args: {tool_call.function.arguments if tool_call.function else 'None'}")
