import os
from pathlib import Path
from dataclasses import dataclass
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / '.env')

@dataclass
class Settings:
    mode: str = os.getenv('MODEL_MODE', 'auto')
    key: str = os.getenv('MODEL_API_KEY', '') or os.getenv('ARK_API_KEY', '')
    base_url: str = os.getenv('MODEL_BASE_URL', 'https://dashscope.aliyuncs.com/compatible-mode/v1')
    model: str = os.getenv('MODEL_NAME', 'qwen-flash')
    timeout: float = float(os.getenv('MODEL_TIMEOUT_SECONDS', '12'))
    intent_enabled: bool = os.getenv('INTENT_MODEL_ENABLED', 'true').lower() == 'true'
    intent_timeout: float = float(os.getenv('INTENT_TIMEOUT_SECONDS', '5'))
    provider: str = os.getenv('MODEL_PROVIDER', 'openai_compatible')
    thinking: bool = os.getenv('MODEL_THINKING', 'false').lower() == 'true'

    @property
    def mock(self):
        return self.mode == 'mock' or (self.mode == 'auto' and not self.key)
