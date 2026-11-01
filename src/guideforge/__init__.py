"""GuideForge — 100% Open-Source Client & Developer Manual Generator with Polyglot Code Runner."""

from guideforge.config import (
    OPEN_SOURCE_LICENSE_MANIFEST,
    AppServerConfig,
    BrandingConfig,
    CalloutBox,
    CodeSnippet,
    ConfigValidationError,
    GuideConfig,
    GuideStep,
    TTSConfig,
    VideoConfig,
    load_and_validate_config,
)
from guideforge.polyglot import (
    CodeExecutionResult,
    LanguageStackInfo,
    PolyglotCodeRunner,
    PolyglotStackDetector,
)
from guideforge.ui_controller import UNIVERSAL_AGENT_MANIFEST, GuideForgeController

__version__ = "0.4.0"
__all__ = [
    "__version__",
    "AppServerConfig",
    "BrandingConfig",
    "CalloutBox",
    "CodeExecutionResult",
    "CodeSnippet",
    "ConfigValidationError",
    "GuideConfig",
    "GuideStep",
    "LanguageStackInfo",
    "OPEN_SOURCE_LICENSE_MANIFEST",
    "PolyglotCodeRunner",
    "PolyglotStackDetector",
    "TTSConfig",
    "VideoConfig",
    "load_and_validate_config",
]
