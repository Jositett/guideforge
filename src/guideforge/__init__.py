"""GuideForge — 100% Open-Source Client & Developer Manual Generator with Polyglot Code Runner."""

from guideforge.config import (
    AppServerConfig,
    BrandingConfig,
    CalloutBox,
    CodeSnippet,
    ConfigValidationError,
    GuideConfig,
    GuideStep,
    OPEN_SOURCE_LICENSE_MANIFEST,
    TTSConfig,
    VideoConfig,
    load_and_validate_config,
)
from guideforge.ui_controller import GuideForgeController, UNIVERSAL_AGENT_MANIFEST
from guideforge.polyglot import (
    CodeExecutionResult,
    LanguageStackInfo,
    PolyglotCodeRunner,
    PolyglotStackDetector,
)

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
