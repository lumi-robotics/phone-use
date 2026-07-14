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
