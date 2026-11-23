from io import BytesIO
import codecs

from django.conf import settings
from rest_framework.exceptions import APIException, ParseError
from rest_framework.parsers import JSONParser


class DevicePayloadTooLarge(APIException):
    status_code = 413
    default_code = "device_payload_too_large"


class BoundedDeviceJSONParser(JSONParser):
    limit_setting = "DEVICE_CHECK_IN_MAX_BYTES"
    payload_name = "Device check-in"

    def parse(self, stream, media_type=None, parser_context=None):
        encoding = (parser_context or {}).get("encoding") or settings.DEFAULT_CHARSET
        try:
            utf8 = codecs.lookup(encoding).name == "utf-8"
        except LookupError:
            utf8 = False
        if not utf8:
            raise ParseError("Use UTF-8 JSON for device requests.")
        limit = getattr(settings, self.limit_setting)
        body = stream.read(limit + 1)
        if len(body) > limit:
            raise DevicePayloadTooLarge(f"{self.payload_name} body must not exceed {limit} bytes.")
        try:
            return super().parse(BytesIO(body), media_type=media_type, parser_context=parser_context)
        except RecursionError as exc:
            raise ParseError("JSON structure is too deeply nested.") from exc


class CheckInJSONParser(BoundedDeviceJSONParser):
    pass


class EventBatchJSONParser(BoundedDeviceJSONParser):
    limit_setting = "DEVICE_EVENT_BATCH_MAX_BYTES"
    payload_name = "Device event batch"
