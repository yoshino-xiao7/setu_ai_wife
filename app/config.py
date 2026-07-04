from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


load_dotenv()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    host: str = Field("127.0.0.1", alias="HOST")
    port: int = Field(7861, alias="PORT")
    comfyui_url: str = Field("http://127.0.0.1:8188", alias="COMFYUI_URL")
    ollama_url: str = Field("http://127.0.0.1:11434", alias="OLLAMA_URL")
    ollama_model: str = Field("qwen3:4b", alias="OLLAMA_MODEL")
    ollama_prompt_num_gpu: int = Field(1, alias="OLLAMA_PROMPT_NUM_GPU")
    output_dir: Path = Field(Path("outputs"), alias="OUTPUT_DIR")
    database_path: Path = Field(Path("data/jobs.sqlite3"), alias="DATABASE_PATH")
    characters_path: Path = Field(Path("config/characters.json"), alias="CHARACTERS_PATH")
    lora_metadata_path: Path = Field(Path("config/lora_metadata.json"), alias="LORA_METADATA_PATH")
    checkpoint_metadata_path: Path = Field(Path("config/checkpoint_metadata.json"), alias="CHECKPOINT_METADATA_PATH")
    prompt_presets_path: Path = Field(Path("config/prompt_presets.json"), alias="PROMPT_PRESETS_PATH")
    prompt_knowledge_path: Path = Field(Path("config/prompt_knowledge.json"), alias="PROMPT_KNOWLEDGE_PATH")
    comfyui_models_dir: Path = Field(Path("tools/ComfyUI_windows_portable/ComfyUI/models"), alias="COMFYUI_MODELS_DIR")
    default_checkpoint: str = Field("put-your-sdxl-anime-checkpoint.safetensors", alias="DEFAULT_CHECKPOINT")
    default_steps: int = Field(35, alias="DEFAULT_STEPS")
    default_cfg: float = Field(4.5, alias="DEFAULT_CFG")
    default_sampler: str = Field("euler", alias="DEFAULT_SAMPLER")
    default_scheduler: str = Field("normal", alias="DEFAULT_SCHEDULER")
    prompt_translation_timeout_seconds: float = Field(45, alias="PROMPT_TRANSLATION_TIMEOUT_SECONDS")
    comfyui_timeout_seconds: float = Field(15, alias="COMFYUI_TIMEOUT_SECONDS")
    local_ai_url: str = Field("http://127.0.0.1:7861", alias="LOCAL_AI_URL")
    cloud_api_url: str = Field("", alias="CLOUD_API_URL")
    ai_worker_token: str = Field("", alias="AI_WORKER_TOKEN")
    ai_worker_id: str = Field("local-comfyui-worker", alias="AI_WORKER_ID")
    ai_worker_name: str = Field("Local ComfyUI Worker", alias="AI_WORKER_NAME")
    ai_worker_version: str = Field("0.1.0", alias="AI_WORKER_VERSION")
    ai_worker_poll_seconds: float = Field(5, alias="AI_WORKER_POLL_SECONDS")
    ai_worker_capability_report_seconds: float = Field(60, alias="AI_WORKER_CAPABILITY_REPORT_SECONDS")
    ai_worker_cleanup_outputs: bool = Field(False, alias="AI_WORKER_CLEANUP_OUTPUTS")
    qq_bot_startup_notice_url: str = Field("", alias="QQ_BOT_STARTUP_NOTICE_URL")
    qq_bot_shutdown_notice_url: str = Field("", alias="QQ_BOT_SHUTDOWN_NOTICE_URL")
    qq_bot_send_message_url: str = Field("", alias="QQ_BOT_SEND_MESSAGE_URL")
    qq_bot_send_image_url: str = Field("", alias="QQ_BOT_SEND_IMAGE_URL")
    qq_bot_token: str = Field("", alias="QQ_BOT_TOKEN")
    dual_character_strategy: str = Field("auto", alias="DUAL_CHARACTER_STRATEGY")
    dual_lora_strength_cap: float = Field(0.65, alias="DUAL_LORA_STRENGTH_CAP")
    dual_mask_conditioning_strength: float = Field(0.95, alias="DUAL_MASK_CONDITIONING_STRENGTH")
    dual_inpaint_denoise: float = Field(0.62, alias="DUAL_INPAINT_DENOISE")
    dual_inpaint_mask_overlap_ratio: float = Field(0.08, alias="DUAL_INPAINT_MASK_OVERLAP_RATIO")
    inpaint_engine: str = Field("auto", alias="INPAINT_ENGINE")
    brushnet_model: str = Field("", alias="BRUSHNET_MODEL")
    brushnet_dtype: str = Field("float16", alias="BRUSHNET_DTYPE")
    brushnet_scale: float = Field(1.0, alias="BRUSHNET_SCALE")


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.output_dir.mkdir(parents=True, exist_ok=True)
    settings.database_path.parent.mkdir(parents=True, exist_ok=True)
    settings.characters_path.parent.mkdir(parents=True, exist_ok=True)
    settings.lora_metadata_path.parent.mkdir(parents=True, exist_ok=True)
    settings.checkpoint_metadata_path.parent.mkdir(parents=True, exist_ok=True)
    settings.prompt_presets_path.parent.mkdir(parents=True, exist_ok=True)
    settings.prompt_knowledge_path.parent.mkdir(parents=True, exist_ok=True)
    return settings
