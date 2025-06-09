import os

import config
from google.oauth2 import service_account
from llama_index.core.llms.llm import LLM
from llama_index.llms.anthropic import Anthropic
from llama_index.llms.openai import OpenAI
from llama_index.llms.openai_like import OpenAILike
from llama_index.llms.vertex import Vertex
from pydantic import BaseModel

from .log_utils import get_logger
from .utils import VertexAnthropicWithCredentials

logger = get_logger(__name__)


class Config:
    def __init__(self, file_path=None):
        self.file_path = file_path
        self.file_config = {}
        if self.file_path and os.path.isfile(self.file_path):
            self.file_config = config.Config(self.file_path)
        self.fallback_config = {}
        self.fallback_config["OPENAI_API_BASE_URL"] = ""

    def __getitem__(self, index):
        # Values in key.cfg has priority over env variables
        if index in self.file_config:
            return self.file_config[index]
        if index in os.environ:
            return os.environ[index]
        if index in self.fallback_config:
            return self.fallback_config[index]
        raise KeyError(
            f"Cannot find {index} in either cfg file '{self.file_path}' or env variables"
        )

    def get(self, index, default=None):
        # Values in key.cfg has priority over env variables
        try:
            return self[index]
        except KeyError:
            return default


def get_llm(**kwargs) -> LLM:
    cfg = Config(kwargs["cfg_path"])
    provider: str = kwargs["provider"]
    provider = provider.lower()
    if provider == "anthropic":
        try:
            llm: LLM = Anthropic(
                model=kwargs["model"],
                api_key=cfg["ANTHROPIC_API_KEY"],
                max_tokens=kwargs["max_token"],
                temperature=kwargs["temperature"],
            )

        except Exception as e:
            raise Exception(f"gen_config: Failed to get {provider} LLM") from e
    elif kwargs["provider"] == "openai":
        try:
            llm: LLM = OpenAI(
                model=kwargs["model"],
                api_key=cfg["OPENAI_API_KEY"],
                max_tokens=kwargs["max_token"],
            )

        except Exception as e:
            raise Exception(f"gen_config: Failed to get {provider} LLM") from e
    elif kwargs["provider"] == "sglang":
        try:
            # SGLang uses OpenAI-compatible API
            api_base = cfg.get("SGLANG_API_BASE", "http://localhost:30000/v1")
            api_key = cfg.get("SGLANG_API_KEY", "EMPTY")  # SGLang often doesn't require a real API key
            
            llm: LLM = OpenAILike(
                model=kwargs["model"],
                api_base=api_base,
                api_key=api_key,
                max_tokens=kwargs["max_token"],
                temperature=kwargs.get("temperature", 0.0),
                top_p=kwargs.get("top_p", 1.0),
                is_chat_model=True,
                is_function_calling_model=True,  # SGLang supports function calling
                timeout=cfg.get("SGLANG_TIMEOUT", 300),  # 设置5分钟超时
            )

        except Exception as e:
            raise Exception(f"gen_config: Failed to get {provider} LLM") from e
    elif kwargs["provider"] == "vertex":
        logger.warning(
            "Support of Vertex Gemini LLMs is still in experimental stage, use with caution"
        )
        service_account_path = os.path.expanduser(cfg["VERTEX_SERVICE_ACCOUNT_PATH"])
        if not os.path.exists(service_account_path):
            raise FileNotFoundError(
                f"Google Cloud Service Account file not found: {service_account_path}"
            )
        try:
            credentials = service_account.Credentials.from_service_account_file(
                service_account_path
            )
            llm: LLM = Vertex(
                model=kwargs["model"],
                project=credentials.project_id,
                credentials=credentials,
                max_tokens=kwargs["max_token"],
            )

        except Exception as e:
            raise Exception(f"gen_config: Failed to get {provider} LLM") from e
    elif kwargs["provider"] == "vertexanthropic":
        service_account_path = os.path.expanduser(cfg["VERTEX_SERVICE_ACCOUNT_PATH"])
        if not os.path.exists(service_account_path):
            raise FileNotFoundError(
                f"Google Cloud Service Account file not found: {service_account_path}"
            )
        try:
            credentials = service_account.Credentials.from_service_account_file(
                service_account_path,
                scopes=["https://www.googleapis.com/auth/cloud-platform"],
            )
            llm: LLM = VertexAnthropicWithCredentials(
                model=kwargs["model"],
                project_id=credentials.project_id,
                credentials=credentials,
                region=cfg["VERTEX_REGION"],
                max_tokens=kwargs["max_token"],
            )

        except Exception as e:
            raise Exception(f"gen_config: Failed to get {provider} LLM") from e
    else:
        raise ValueError(f"gen_config: Invalid provider: {provider}")

    try:
        _ = llm.complete("Say 'Hi'")
    except Exception as e:
        raise Exception(
            f"gen_config: Failed to complete LLM chat for {provider}"
        ) from e

    return llm


class ExperimentSetting(BaseModel):
    """
    Global setting for experiment
    """

    temperature: float = 0.85  # Chat temperature
    top_p: float = 0.95  # Chat top_p


global_exp_setting = ExperimentSetting()


def get_exp_setting() -> ExperimentSetting:
    return global_exp_setting


def set_exp_setting(temperature: float | None = None, top_p: float | None = None):
    if temperature is not None:
        global_exp_setting.temperature = temperature
    if top_p is not None:
        global_exp_setting.top_p = top_p
    return global_exp_setting
