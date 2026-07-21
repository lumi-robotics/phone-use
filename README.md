# phone-use

[![CI](https://github.com/lumi-robotics/phone-use/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/lumi-robotics/phone-use/actions/workflows/ci.yml?query=branch%3Amain)

A small Python SDK for phone automation. It calls a running automation service over HTTP and forwards model configuration to the service.

## Installation

Python 3.10 or newer is required.

~~~bash
pip install .
~~~

For local development:

~~~bash
pip install -e .
~~~

## Quick Start

~~~python
import os

from phone_use import PhoneUse

phone = PhoneUse(
    "http://127.0.0.1:8787",
    model_name="your-model",
    model_api_key=os.environ["PHONE_USE_MODEL_API_KEY"],
    model_base_url="https://model.example.com/v1",
)
result = phone.act("Open Settings and read the device model")

print(result)
~~~

The service URL can also be configured with an environment variable:

~~~bash
export PHONE_USE_BASE_URL=http://127.0.0.1:8787
python examples/quickstart.py
~~~

The SDK uses the server's default device unless another device is selected:

~~~python
phone = PhoneUse(
    "http://127.0.0.1:8787",
    device_id="device-01",
    timeout=60,
    model_name="your-model",
    model_api_key="your-api-key",
    model_base_url="https://model.example.com/v1",
    model_family="your-model-family",
    model_reasoning_enabled=False,
)
~~~

Model configuration is only sent to endpoints that require a model. Override it for one request with the model argument:

~~~python
phone.act(
    "Open Settings",
    model={
        "name": "another-model",
        "api_key": "another-api-key",
        "base_url": "https://model.example.com/v1",
    },
)
~~~

## Common Operations

~~~python
phone.health()
phone.list_devices()
phone.get_device()
phone.save_screenshot("screen.png")

phone.act("Open Settings")
phone.query_string("Read the current page title")
phone.wait_for("The Settings screen is visible", timeout_ms=30_000)

phone.tap(320, 640)
phone.tap_sequence([(320, 640), (500, 640)])
phone.swipe(500, 1200, 500, 400)
phone.named_action("home")
phone.type_text("hello world", clear_first=True)
~~~

Asynchronous execution:

~~~python
task = phone.start_task(
    "ai_act",
    args={"instruction": "Open Settings"},
)
status = phone.get_task(task["task_id"])
phone.cancel_task(task["task_id"])
~~~

Coordinates use pixels from the image returned by screenshot. See the [API reference](docs/api.md) for all parameters and exceptions.

## Testing

~~~bash
python -m unittest discover -s tests -v
~~~

The tests use a local mock HTTP server and do not control a real device.

## License

MIT
