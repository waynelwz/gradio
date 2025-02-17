""" Handy utility functions."""

from __future__ import annotations

import asyncio
import copy
import inspect
import json
import json.decoder
import os
import pkgutil
import random
import re
import subprocess
import sys
import tempfile
import time
import typing
import warnings
from contextlib import contextmanager
from distutils.version import StrictVersion
from enum import Enum
from io import BytesIO
from numbers import Number
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Dict,
    Generator,
    List,
    NewType,
    Tuple,
    Type,
    TypeVar,
)

import aiohttp
import fsspec.asyn
import httpx
import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import PIL
import requests
from pydantic import BaseModel, Json, parse_obj_as

import gradio
from gradio import processing_utils
from gradio.context import Context
from gradio.documentation import document, set_documentation_group

if TYPE_CHECKING:  # Only import for type checking (is False at runtime).
    from gradio.blocks import BlockContext
    from gradio.components import Component

analytics_url = "https://api.gradio.app/"
PKG_VERSION_URL = "https://api.gradio.app/pkg-version"
JSON_PATH = os.path.join(os.path.dirname(gradio.__file__), "launches.json")

T = TypeVar("T")


def version_check():
    try:
        current_pkg_version = (
            pkgutil.get_data(__name__, "version.txt").decode("ascii").strip()
        )
        latest_pkg_version = requests.get(url=PKG_VERSION_URL, timeout=3).json()[
            "version"
        ]
        if StrictVersion(latest_pkg_version) > StrictVersion(current_pkg_version):
            print(
                "IMPORTANT: You are using gradio version {}, "
                "however version {} "
                "is available, please upgrade.".format(
                    current_pkg_version, latest_pkg_version
                )
            )
            print("--------")
    except json.decoder.JSONDecodeError:
        warnings.warn("unable to parse version details from package URL.")
    except KeyError:
        warnings.warn("package URL does not contain version info.")
    except:
        pass


def get_local_ip_address() -> str:
    """Gets the public IP address or returns the string "No internet connection" if unable to obtain it."""
    try:
        ip_address = requests.get(
            "https://checkip.amazonaws.com/", timeout=3
        ).text.strip()
    except (requests.ConnectionError, requests.exceptions.ReadTimeout):
        ip_address = "No internet connection"
    return ip_address


def initiated_analytics(data: Dict[str:Any]) -> None:
    try:
        requests.post(
            analytics_url + "gradio-initiated-analytics/", data=data, timeout=3
        )
    except (requests.ConnectionError, requests.exceptions.ReadTimeout):
        pass  # do not push analytics if no network


def launch_analytics(data: Dict[str, Any]) -> None:
    try:
        requests.post(
            analytics_url + "gradio-launched-analytics/", data=data, timeout=3
        )
    except (requests.ConnectionError, requests.exceptions.ReadTimeout):
        pass  # do not push analytics if no network


def integration_analytics(data: Dict[str, Any]) -> None:
    try:
        requests.post(
            analytics_url + "gradio-integration-analytics/", data=data, timeout=3
        )
    except (requests.ConnectionError, requests.exceptions.ReadTimeout):
        pass  # do not push analytics if no network


def error_analytics(ip_address: str, message: str) -> None:
    """
    Send error analytics if there is network
    :param type: RuntimeError or NameError
    """
    data = {"ip_address": ip_address, "error": message}
    try:
        requests.post(analytics_url + "gradio-error-analytics/", data=data, timeout=3)
    except (requests.ConnectionError, requests.exceptions.ReadTimeout):
        pass  # do not push analytics if no network


async def log_feature_analytics(ip_address: str, feature: str) -> None:
    data = {"ip_address": ip_address, "feature": feature}
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(
                analytics_url + "gradio-feature-analytics/", data=data
            ):
                pass
        except (aiohttp.ClientError):
            pass  # do not push analytics if no network


def colab_check() -> bool:
    """
    Check if interface is launching from Google Colab
    :return is_colab (bool): True or False
    """
    is_colab = False
    try:  # Check if running interactively using ipython.
        from IPython import get_ipython

        from_ipynb = get_ipython()
        if "google.colab" in str(from_ipynb):
            is_colab = True
    except (ImportError, NameError):
        pass
    return is_colab


def ipython_check() -> bool:
    """
    Check if interface is launching from iPython (not colab)
    :return is_ipython (bool): True or False
    """
    is_ipython = False
    try:  # Check if running interactively using ipython.
        from IPython import get_ipython

        if get_ipython() is not None:
            is_ipython = True
    except (ImportError, NameError):
        pass
    return is_ipython


def readme_to_html(article: str) -> str:
    try:
        response = requests.get(article, timeout=3)
        if response.status_code == requests.codes.ok:  # pylint: disable=no-member
            article = response.text
    except requests.exceptions.RequestException:
        pass
    return article


def show_tip(interface: gradio.Blocks) -> None:
    if interface.show_tips and random.random() < 1.5:
        tip: str = random.choice(gradio.strings.en["TIPS"])
        print(f"Tip: {tip}")


def launch_counter() -> None:
    try:
        if not os.path.exists(JSON_PATH):
            launches = {"launches": 1}
            with open(JSON_PATH, "w+") as j:
                json.dump(launches, j)
        else:
            with open(JSON_PATH) as j:
                launches = json.load(j)
            launches["launches"] += 1
            if launches["launches"] in [25, 50, 150, 500, 1000]:
                print(gradio.strings.en["BETA_INVITE"])
            with open(JSON_PATH, "w") as j:
                j.write(json.dumps(launches))
    except:
        pass


def get_default_args(func: Callable) -> List[Any]:
    signature = inspect.signature(func)
    return [
        v.default if v.default is not inspect.Parameter.empty else None
        for v in signature.parameters.values()
    ]


def assert_configs_are_equivalent_besides_ids(
    config1: Dict, config2: Dict, root_keys: Tuple = ("mode", "theme")
):
    """Allows you to test if two different Blocks configs produce the same demo.

    Parameters:
    config1 (dict): nested dict with config from the first Blocks instance
    config2 (dict): nested dict with config from the second Blocks instance
    root_keys (Tuple): an interable consisting of which keys to test for equivalence at
        the root level of the config. By default, only "mode" and "theme" are tested,
        so keys like "version" are ignored.
    """
    config1 = copy.deepcopy(config1)
    config2 = copy.deepcopy(config2)

    for key in root_keys:
        assert config1[key] == config2[key], f"Configs have different: {key}"

    assert len(config1["components"]) == len(
        config2["components"]
    ), "# of components are different"

    def assert_same_components(config1_id, config2_id):
        c1 = list(filter(lambda c: c["id"] == config1_id, config1["components"]))[0]
        c2 = list(filter(lambda c: c["id"] == config2_id, config2["components"]))[0]
        c1 = copy.deepcopy(c1)
        c1.pop("id")
        c2 = copy.deepcopy(c2)
        c2.pop("id")
        assert c1 == c2, f"{c1} does not match {c2}"

    def same_children_recursive(children1, chidren2):
        for child1, child2 in zip(children1, chidren2):
            assert_same_components(child1["id"], child2["id"])
            if "children" in child1 or "children" in child2:
                same_children_recursive(child1["children"], child2["children"])

    children1 = config1["layout"]["children"]
    children2 = config2["layout"]["children"]
    same_children_recursive(children1, children2)

    for d1, d2 in zip(config1["dependencies"], config2["dependencies"]):
        for t1, t2 in zip(d1.pop("targets"), d2.pop("targets")):
            assert_same_components(t1, t2)
        for i1, i2 in zip(d1.pop("inputs"), d2.pop("inputs")):
            assert_same_components(i1, i2)
        for o1, o2 in zip(d1.pop("outputs"), d2.pop("outputs")):
            assert_same_components(o1, o2)

        assert d1 == d2, f"{d1} does not match {d2}"

    return True


def format_ner_list(input_string: str, ner_groups: Dict[str : str | int]):
    if len(ner_groups) == 0:
        return [(input_string, None)]

    output = []
    prev_end = 0

    for group in ner_groups:
        entity, start, end = group["entity_group"], group["start"], group["end"]
        output.append((input_string[prev_end:start], None))
        output.append((input_string[start:end], entity))
        prev_end = end

    output.append((input_string[end:], None))
    return output


def delete_none(_dict: T, skip_value: bool = False) -> T:
    """
    Delete None values recursively from all of the dictionaries, tuples, lists, sets.
    Credit: https://stackoverflow.com/a/66127889/5209347
    """
    if isinstance(_dict, dict):
        for key, value in list(_dict.items()):
            if skip_value and key == "value":
                continue
            if isinstance(value, (list, dict, tuple, set)):
                _dict[key] = delete_none(value)
            elif value is None or key is None:
                del _dict[key]

    elif isinstance(_dict, (list, set, tuple)):
        _dict = type(_dict)(delete_none(item) for item in _dict if item is not None)

    return _dict


def resolve_singleton(_list: List[Any] | Any) -> Any:
    if len(_list) == 1:
        return _list[0]
    else:
        return _list


def component_or_layout_class(cls_name: str) -> Type[Component] | Type[BlockContext]:
    """
    Returns the component, template, or layout class with the given class name, or
    raises a ValueError if not found.

    Parameters:
    cls_name (str): lower-case string class name of a component
    Returns:
    cls: the component class
    """
    import gradio.components
    import gradio.layouts
    import gradio.templates

    components = [
        (name, cls)
        for name, cls in gradio.components.__dict__.items()
        if isinstance(cls, type)
    ]
    templates = [
        (name, cls)
        for name, cls in gradio.templates.__dict__.items()
        if isinstance(cls, type)
    ]
    layouts = [
        (name, cls)
        for name, cls in gradio.layouts.__dict__.items()
        if isinstance(cls, type)
    ]
    for name, cls in components + templates + layouts:
        if name.lower() == cls_name.replace("_", "") and (
            issubclass(cls, gradio.components.Component)
            or issubclass(cls, gradio.blocks.BlockContext)
        ):
            return cls
    raise ValueError(f"No such component or layout: {cls_name}")


def synchronize_async(func: Callable, *args, **kwargs) -> Any:
    """
    Runs async functions in sync scopes.

    Can be used in any scope. See run_coro_in_background for more details.

    Example:
        if inspect.iscoroutinefunction(block_fn.fn):
            predictions = utils.synchronize_async(block_fn.fn, *processed_input)

    Args:
        func:
        *args:
        **kwargs:
    """
    return fsspec.asyn.sync(fsspec.asyn.get_loop(), func, *args, **kwargs)


def run_coro_in_background(func: Callable, *args, **kwargs):
    """
    Runs coroutines in background.

    Warning, be careful to not use this function in other than FastAPI scope, because the event_loop has not started yet.
    You can use it in any scope reached by FastAPI app.

    correct scope examples: endpoints in routes, Blocks.process_api
    incorrect scope examples: Blocks.launch

    Use startup_events in routes.py if you need to run a coro in background in Blocks.launch().


    Example:
        utils.run_coro_in_background(fn, *args, **kwargs)

    Args:
        func:
        *args:
        **kwargs:

    Returns:

    """
    event_loop = asyncio.get_event_loop()
    return event_loop.create_task(func(*args, **kwargs))


def async_iteration(iterator):
    try:
        return next(iterator)
    except StopIteration:
        # raise a ValueError here because co-routines can't raise StopIteration themselves
        raise StopAsyncIteration()


class AsyncRequest:
    """
    The AsyncRequest class is a low-level API that allow you to create asynchronous HTTP requests without a context manager.
    Compared to making calls by using httpx directly, AsyncRequest offers more flexibility and control over:
        (1) Includes response validation functionality both using validation models and functions.
        (2) Since we're still using httpx.Request class by wrapping it, we have all it's functionalities.
        (3) Exceptions are handled silently during the request call, which gives us the ability to inspect each one
        individually in the case of multiple asynchronous request calls and some of them failing.
        (4) Provides HTTP request types with AsyncRequest.Method Enum class for ease of usage
    AsyncRequest also offers some util functions such as has_exception, is_valid and status to inspect get detailed
    information about executed request call.

    The basic usage of AsyncRequest is as follows: create a AsyncRequest object with inputs(method, url etc.). Then use it
    with the "await" statement, and then you can use util functions to do some post request checks depending on your use-case.
    Finally, call the get_validated_data function to get the response data.

    You can see example usages in test_utils.py.
    """

    ResponseJson = NewType("ResponseJson", Json)
    client = httpx.AsyncClient()

    class Method(str, Enum):
        """
        Method is an enumeration class that contains possible types of HTTP request methods.
        """

        ANY = "*"
        CONNECT = "CONNECT"
        HEAD = "HEAD"
        GET = "GET"
        DELETE = "DELETE"
        OPTIONS = "OPTIONS"
        PATCH = "PATCH"
        POST = "POST"
        PUT = "PUT"
        TRACE = "TRACE"

    def __init__(
        self,
        method: Method,
        url: str,
        *,
        validation_model: Type[BaseModel] = None,
        validation_function: Callable = None,
        exception_type: Type[Exception] = Exception,
        raise_for_status: bool = False,
        **kwargs,
    ):
        """
        Initialize the Request instance.
        Args:
            method(Request.Method) : method of the request
            url(str): url of the request
            *
            validation_model(Type[BaseModel]): a pydantic validation class type to use in validation of the response
            validation_function(Callable): a callable instance to use in validation of the response
            exception_class(Type[Exception]): a exception type to throw with its type
            raise_for_status(bool): a flag that determines to raise httpx.Request.raise_for_status() exceptions.
        """
        self._response = None
        self._exception = None
        self._status = None
        self._raise_for_status = raise_for_status
        self._validation_model = validation_model
        self._validation_function = validation_function
        self._exception_type = exception_type
        self._validated_data = None
        # Create request
        self._request = self._create_request(method, url, **kwargs)

    def __await__(self) -> Generator[None, Any, "AsyncRequest"]:
        """
        Wrap Request's __await__ magic function to create request calls which are executed in one line.
        """
        return self.__run().__await__()

    async def __run(self) -> AsyncRequest:
        """
        Manage the request call lifecycle.
        Execute the request by sending it through the client, then check its status.
        Then parse the request into Json format. And then validate it using the provided validation methods.
        If a problem occurs in this sequential process,
        an exception will be raised within the corresponding method, and allowed to be examined.
        Manage the request call lifecycle.

        Returns:
            Request
        """
        try:
            # Send the request and get the response.
            self._response: httpx.Response = await AsyncRequest.client.send(
                self._request
            )
            # Raise for _status
            self._status = self._response.status_code
            if self._raise_for_status:
                self._response.raise_for_status()
            # Parse client response data to JSON
            self._json_response_data = self._response.json()
            # Validate response data
            self._validated_data = self._validate_response_data(
                self._json_response_data
            )
        except Exception as exception:
            # If there is an exception, store it to do further inspections.
            self._exception = self._exception_type(exception)
        return self

    @staticmethod
    def _create_request(method: Method, url: str, **kwargs) -> AsyncRequest:
        """
        Create a request. This is a httpx request wrapper function.
        Args:
            method(Request.Method): request method type
            url(str): target url of the request
            **kwargs
        Returns:
            Request
        """
        request = httpx.Request(method, url, **kwargs)
        return request

    def _validate_response_data(self, response: ResponseJson) -> ResponseJson:
        """
        Validate response using given validation methods. If there is a validation method and response is not valid,
        validation functions will raise an exception for them.
        Args:
            response(ResponseJson): response object
        Returns:
            ResponseJson: Validated Json object.
        """

        # We use raw response as a default value if there is no validation method or response is not valid.
        validated_response = response

        try:
            # If a validation model is provided, validate response using the validation model.
            if self._validation_model:
                validated_response = self._validate_response_by_model(
                    validated_response
                )
            # Then, If a validation function is provided, validate response using the validation function.
            if self._validation_function:
                validated_response = self._validate_response_by_validation_function(
                    validated_response
                )
        except Exception as exception:
            # If one of the validation methods does not confirm, raised exception will be silently handled.
            # We assign this exception to classes instance to do further inspections via is_valid function.
            self._exception = exception

        return validated_response

    def _validate_response_by_model(self, response: ResponseJson) -> ResponseJson:
        """
        Validate response json using the validation model.
        Args:
            response(ResponseJson): response object
        Returns:
            ResponseJson: Validated Json object.
        """
        validated_data = parse_obj_as(self._validation_model, response)
        return validated_data

    def _validate_response_by_validation_function(
        self, response: ResponseJson
    ) -> ResponseJson:
        """
        Validate response json using the validation function.
        Args:
            response(ResponseJson): response object
        Returns:
            ResponseJson: Validated Json object.
        """
        validated_data = self._validation_function(response)
        return validated_data

    def is_valid(self, raise_exceptions: bool = False) -> bool:
        """
        Check response object's validity+. Raise exceptions if raise_exceptions flag is True.
        Args:
            raise_exceptions(bool) : a flag to raise exceptions in this check
        Returns:
            bool: validity of the data
        """
        if self.has_exception:
            if raise_exceptions:
                raise self._exception
            return False
        else:
            # If there is no exception, that means there is no validation error.
            return True

    def get_validated_data(self):
        return self._validated_data

    @property
    def json(self):
        return self._json_response_data

    @property
    def exception(self):
        return self._exception

    @property
    def has_exception(self):
        return self.exception is not None

    @property
    def raise_exceptions(self):
        if self.has_exception:
            raise self._exception

    @property
    def status(self):
        return self._status


@contextmanager
def set_directory(path: Path | str):
    """Context manager that sets the working directory to the given path."""
    origin = Path().absolute()
    try:
        os.chdir(path)
        yield
    finally:
        os.chdir(origin)


def strip_invalid_filename_characters(filename: str, max_bytes: int = 200) -> str:
    """Strips invalid characters from a filename and ensures that the file_length is less than `max_bytes` bytes."""
    filename = "".join([char for char in filename if char.isalnum() or char in "._- "])
    filename_len = len(filename.encode())
    if filename_len > max_bytes:
        while filename_len > max_bytes:
            if len(filename) == 0:
                break
            filename = filename[:-1]
            filename_len = len(filename.encode())
    return filename


def sanitize_value_for_csv(value: str | Number) -> str | Number:
    """
    Sanitizes a value that is being written to a CSV file to prevent CSV injection attacks.
    Reference: https://owasp.org/www-community/attacks/CSV_Injection
    """
    if isinstance(value, Number):
        return value
    unsafe_prefixes = ["=", "+", "-", "@", "\t", "\n"]
    unsafe_sequences = [",=", ",+", ",-", ",@", ",\t", ",\n"]
    if any(value.startswith(prefix) for prefix in unsafe_prefixes) or any(
        sequence in value for sequence in unsafe_sequences
    ):
        value = "'" + value
    return value


def sanitize_list_for_csv(values: T) -> T:
    """
    Sanitizes a list of values (or a list of list of values) that is being written to a
    CSV file to prevent CSV injection attacks.
    """
    sanitized_values = []
    for value in values:
        if isinstance(value, list):
            sanitized_value = [sanitize_value_for_csv(v) for v in value]
            sanitized_values.append(sanitized_value)
        else:
            sanitized_value = sanitize_value_for_csv(value)
            sanitized_values.append(sanitized_value)
    return sanitized_values


def append_unique_suffix(name: str, list_of_names: List[str]):
    """Appends a numerical suffix to `name` so that it does not appear in `list_of_names`."""
    list_of_names = set(list_of_names)  # for O(1) lookup
    if name not in list_of_names:
        return name
    else:
        suffix_counter = 1
        new_name = name + f"_{suffix_counter}"
        while new_name in list_of_names:
            suffix_counter += 1
            new_name = name + f"_{suffix_counter}"
        return new_name


def validate_url(possible_url: str) -> bool:
    headers = {"User-Agent": "gradio (https://gradio.app/; team@gradio.app)"}
    try:
        return requests.get(possible_url, headers=headers).ok
    except Exception:
        return False


def is_update(val):
    return isinstance(val, dict) and "update" in val.get("__type__", "")


def get_continuous_fn(fn: Callable, every: float) -> Callable:
    def continuous_fn(*args):
        while True:
            output = fn(*args)
            yield output
            time.sleep(every)

    return continuous_fn


async def cancel_tasks(task_ids: List[str]):
    if sys.version_info < (3, 8):
        return None

    matching_tasks = [
        task for task in asyncio.all_tasks() if task.get_name() in task_ids
    ]
    for task in matching_tasks:
        task.cancel()
    await asyncio.gather(*matching_tasks, return_exceptions=True)


def set_task_name(task, session_hash: str, fn_index: int, batch: bool):
    if sys.version_info >= (3, 8) and not (
        batch
    ):  # You shouldn't be able to cancel a task if it's part of a batch
        task.set_name(f"{session_hash}_{fn_index}")


def get_cancel_function(
    dependencies: List[Dict[str, Any]]
) -> Tuple[Callable, List[int]]:
    fn_to_comp = {}
    for dep in dependencies:
        fn_index = next(
            i for i, d in enumerate(Context.root_block.dependencies) if d == dep
        )
        fn_to_comp[fn_index] = [Context.root_block.blocks[o] for o in dep["outputs"]]

    async def cancel(session_hash: str) -> None:
        task_ids = set([f"{session_hash}_{fn}" for fn in fn_to_comp])
        await cancel_tasks(task_ids)

    return (
        cancel,
        list(fn_to_comp.keys()),
    )


def check_function_inputs_match(fn: Callable, inputs: List, inputs_as_dict: bool):
    """
    Checks if the input component set matches the function
    Returns: None if valid, a string error message if mismatch
    """

    def is_special_typed_parameter(name):
        from gradio.routes import Request

        """Checks if parameter has a type hint designating it as a gr.Request"""
        return parameter_types.get(name, "") == Request

    signature = inspect.signature(fn)
    parameter_types = typing.get_type_hints(fn) if inspect.isfunction(fn) else {}
    min_args = 0
    max_args = 0
    for name, param in signature.parameters.items():
        has_default = param.default != param.empty
        if param.kind in [param.POSITIONAL_ONLY, param.POSITIONAL_OR_KEYWORD]:
            if not (is_special_typed_parameter(name)):
                if not has_default:
                    min_args += 1
                max_args += 1
        elif param.kind == param.VAR_POSITIONAL:
            max_args = "infinity"
        elif param.kind == param.KEYWORD_ONLY:
            if not has_default:
                return f"Keyword-only args must have default values for function {fn}"
    arg_count = 1 if inputs_as_dict else len(inputs)
    if min_args == max_args and max_args != arg_count:
        warnings.warn(
            f"Expected {max_args} arguments for function {fn}, received {arg_count}."
        )
    if arg_count < min_args:
        warnings.warn(
            f"Expected at least {min_args} arguments for function {fn}, received {arg_count}."
        )
    if max_args != "infinity" and arg_count > max_args:
        warnings.warn(
            f"Expected maximum {max_args} arguments for function {fn}, received {arg_count}."
        )


class TupleNoPrint(tuple):
    # To remove printing function return in notebook
    def __repr__(self):
        return ""

    def __str__(self):
        return ""


set_documentation_group("component-helpers")


@document()
def make_waveform(
    audio: str | Tuple[int, np.ndarray],
    *,
    bg_color: str = "#f3f4f6",
    bg_image: str = None,
    fg_alpha: float = 0.75,
    bars_color: str | Tuple[str, str] = ("#fbbf24", "#ea580c"),
    bar_count: int = 50,
    bar_width: float = 0.6,
):
    """
    Generates a waveform video from an audio file. Useful for creating an easy to share audio visualization. The output should be passed into a `gr.Video` component.
    Parameters:
        audio: Audio file path or tuple of (sample_rate, audio_data)
        bg_color: Background color of waveform (ignored if bg_image is provided)
        bg_image: Background image of waveform
        fg_alpha: Opacity of foreground waveform
        bars_color: Color of waveform bars. Can be a single color or a tuple of (start_color, end_color) of gradient
        bar_count: Number of bars in waveform
        bar_width: Width of bars in waveform. 1 represents full width, 0.5 represents half width, etc.
    Returns:
        A filepath to the output video.
    """
    if isinstance(audio, str):
        audio_file = audio
        audio = processing_utils.audio_from_file(audio)
    else:
        tmp_wav = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        processing_utils.audio_to_file(audio[0], audio[1], tmp_wav.name)
        audio_file = tmp_wav.name
    duration = round(len(audio[1]) / audio[0], 4)

    # Helper methods to create waveform
    def hex_to_RGB(hex_str):
        return [int(hex_str[i : i + 2], 16) for i in range(1, 6, 2)]

    def get_color_gradient(c1, c2, n):
        assert n > 1
        c1_rgb = np.array(hex_to_RGB(c1)) / 255
        c2_rgb = np.array(hex_to_RGB(c2)) / 255
        mix_pcts = [x / (n - 1) for x in range(n)]
        rgb_colors = [((1 - mix) * c1_rgb + (mix * c2_rgb)) for mix in mix_pcts]
        return [
            "#" + "".join([format(int(round(val * 255)), "02x") for val in item])
            for item in rgb_colors
        ]

    # Reshape audio to have a fixed number of bars
    samples = audio[1]
    if len(samples.shape) > 1:
        samples = np.mean(samples, 1)
    bins_to_pad = bar_count - (len(samples) % bar_count)
    samples = np.pad(samples, [(0, bins_to_pad)])
    samples = np.reshape(samples, (bar_count, -1))
    samples = np.abs(samples)
    samples = np.max(samples, 1)

    matplotlib.use("Agg")
    plt.clf()
    # Plot waveform
    color = (
        bars_color
        if isinstance(bars_color, str)
        else get_color_gradient(bars_color[0], bars_color[1], bar_count)
    )
    plt.bar(
        np.arange(0, bar_count),
        samples * 2,
        bottom=(-1 * samples),
        width=bar_width,
        color=color,
    )
    plt.axis("off")
    plt.margins(x=0)
    tmp_img = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    savefig_kwargs = {"bbox_inches": "tight"}
    if bg_image is not None:
        savefig_kwargs["transparent"] = True
    else:
        savefig_kwargs["facecolor"] = bg_color
    plt.savefig(tmp_img.name, **savefig_kwargs)
    waveform_img = PIL.Image.open(tmp_img.name)
    waveform_img = waveform_img.resize((1000, 200))

    # Composite waveform with background image
    if bg_image is not None:
        waveform_array = np.array(waveform_img)
        waveform_array[:, :, 3] = waveform_array[:, :, 3] * fg_alpha
        waveform_img = PIL.Image.fromarray(waveform_array)

        bg_img = PIL.Image.open(bg_image)
        waveform_width, waveform_height = waveform_img.size
        bg_width, bg_height = bg_img.size
        if waveform_width != bg_width:
            bg_img = bg_img.resize(
                (waveform_width, 2 * int(bg_height * waveform_width / bg_width / 2))
            )
            bg_width, bg_height = bg_img.size
        composite_height = max(bg_height, waveform_height)
        composite = PIL.Image.new("RGBA", (waveform_width, composite_height), "#FFFFFF")
        composite.paste(bg_img, (0, composite_height - bg_height))
        composite.paste(
            waveform_img, (0, composite_height - waveform_height), waveform_img
        )
        composite.save(tmp_img.name)
        img_width, img_height = composite.size
    else:
        img_width, img_height = waveform_img.size
        waveform_img.save(tmp_img.name)

    # Convert waveform to video with ffmpeg
    output_mp4 = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)

    ffmpeg_cmd = f"""ffmpeg -loop 1 -i {tmp_img.name} -i {audio_file} -vf "color=c=#FFFFFF77:s={img_width}x{img_height}[bar];[0][bar]overlay=-w+(w/{duration})*t:H-h:shortest=1" -t {duration} -y {output_mp4.name}"""

    subprocess.call(ffmpeg_cmd, shell=True)
    return output_mp4.name


def tex2svg(formula, *args):
    FONTSIZE = 20
    DPI = 300
    plt.rc("mathtext", fontset="cm")
    fig = plt.figure(figsize=(0.01, 0.01))
    fig.text(0, 0, r"${}$".format(formula), fontsize=FONTSIZE)
    output = BytesIO()
    fig.savefig(
        output,
        dpi=DPI,
        transparent=True,
        format="svg",
        bbox_inches="tight",
        pad_inches=0.0,
    )
    plt.close(fig)
    output.seek(0)
    xml_code = output.read().decode("utf-8")
    svg_start = xml_code.index("<svg ")
    svg_code = xml_code[svg_start:]
    svg_code = re.sub(r"<metadata>.*<\/metadata>", "", svg_code, flags=re.DOTALL)
    copy_code = f"<span style='font-size: 0px'>{formula}</span>"
    return f"{copy_code}{svg_code}"
