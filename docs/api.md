# phone-use API

## Create a Client

~~~python
from phone_use import PhoneUse

phone = PhoneUse(
    "http://127.0.0.1:8787",
    device_id="default",
    timeout=30,
    headers={"Authorization": "Bearer token"},
    model_name="your-model",
    model_api_key="your-api-key",
    model_base_url="https://model.example.com/v1",
    model_family="your-model-family",
    model_reasoning_enabled=False,
)
~~~

Constructor parameters:

- base_url: Automation service URL. Defaults to PHONE_USE_BASE_URL, then http://127.0.0.1:8787.
- device_id: Device to control. Defaults to default.
- timeout: HTTP request timeout in seconds. Defaults to 30.
- headers: Additional HTTP headers included with every request.
- model_name: Model name.
- model_api_key: Model service API key.
- model_base_url: Model service endpoint.
- model_family: Optional model family identifier.
- model_reasoning_enabled: Enables or disables the model's reasoning mode.

Model parameters are sent as a model object to act, query_string, wait_for, and asynchronous ai_act tasks. Screenshots, device queries, and coordinate actions do not include model parameters.

## Service and Devices

~~~python
phone.health()
phone.list_devices()
phone.get_device()
~~~

health checks the API service, list_devices returns available devices, and get_device returns information about the selected device.

## Screenshots

~~~python
png_bytes = phone.screenshot()
png_bytes = phone.screenshot(source="snapshot")
path = phone.save_screenshot("screen.png")
~~~

screenshot returns PNG bytes. save_screenshot writes the image and returns a pathlib.Path.

## Screen Operations

### act

Execute a natural-language instruction:

~~~python
result = phone.act(
    "Open Settings and read the device model",
    timeout_s=60,
    park_after=True,
    generate_report=False,
)
~~~

Override the client's model configuration for one request:

~~~python
result = phone.act(
    "Open Settings",
    model={
        "name": "another-model",
        "api_key": "another-api-key",
        "base_url": "https://model.example.com/v1",
        "family": "another-family",
        "reasoning_enabled": True,
    },
)
~~~

### query_string

Read a string from the current screen:

~~~python
result = phone.query_string(
    "Read the current page title",
    screenshot_included=True,
)
print(result["answer"])
~~~

### wait_for

Wait for a screen condition:

~~~python
phone.wait_for(
    "The Settings screen is visible",
    timeout_ms=30_000,
    check_interval_ms=1_000,
)
~~~

Additional keyword arguments are forwarded to the service with their original names. Arguments set to None are omitted.

## Coordinate Actions

~~~python
phone.tap(320, 640, park_after=True)
phone.tap_sequence([(320, 640), (500, 640)])
phone.swipe(
    500,
    1200,
    500,
    400,
    hold_s=0.2,
    release_ratio=0.4,
)
~~~

All coordinates use pixels from the image returned by screenshot.

## System Actions and Text Input

~~~python
phone.named_action("back")
phone.named_action("home")

phone.type_text(
    "hello world",
    clear_first=True,
    preserve_case=True,
    park_after=True,
)
~~~

## Asynchronous Tasks

~~~python
task = phone.start_task(
    "ai_act",
    args={"instruction": "Open Settings"},
    model={"name": "another-model"},
)

phone.get_task(task["task_id"])
phone.list_tasks(status="running", limit=10)
phone.cancel_task(
    task["task_id"],
    reason="no longer needed",
    stop_device=True,
)
~~~

## Exceptions

~~~python
from phone_use import PhoneUseAPIError, PhoneUseNetworkError

try:
    phone.act("Open Settings")
except PhoneUseAPIError as exc:
    print(exc.status_code, exc.message, exc.response)
except PhoneUseNetworkError as exc:
    print(exc)
~~~

- PhoneUseAPIError: The service returned a non-success HTTP status. It includes status_code, message, and response.
- PhoneUseNetworkError: The connection failed, timed out, or encountered another network error.
- ValueError: A local argument is invalid and no request was sent.

All SDK exceptions inherit from PhoneUseError.
