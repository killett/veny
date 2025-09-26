#!/usr/bin/env python3

# Written by Emmy Killett (she/her), ChatGPT 4o (it/its), ChatGPT o1-preview (it/its), ChatGPT o3-mini-high (it/its), ChatGPT o4-mini-high (it/its), ChatGPT 5 Thinking (it/its), and GitHub Copilot (it/its).
from __future__ import annotations  # For Python 3.7+ compatibility with type annotations
import os
import sys
from pathlib import Path  # Preferred over os.path for path manipulations.
import logging
from collections.abc import Sequence, Callable, Iterable
from itertools import chain
from typing import TextIO, Any, TypeAlias, Type, Literal, Protocol, Final
import re  # Used to precompile regexes for performance
from dataclasses import dataclass, field, replace
from enum import Enum
import errno

# Version of univ_defs.py:
__version__: str = "0.2.0"

# Version of python which should be used in scripts that import this module.
# Python 3.12 is supported until 2028-10. https://devguide.python.org/versions/
# The next version (Python 3.13) will leave the bugfix phase around 2026-10.
PY_VERSION: float = 3.12

# Default encoding used for reading and writing text files:
DEFAULT_ENCODING: str = "utf-8"

# ANSI escape codes
ANSI_RED:    str = "\033[91m"
ANSI_GREEN:  str = "\033[92m"  # this is bold/bright green on Linux but orange on my Mac
ANSI_YELLOW: str = "\033[93m"
ANSI_CYAN:   str = "\033[94m"  # this is blue on Linux but cyan on my Mac
ANSI_RESET:  str = "\033[0m"

# All the formatting rules to ignore when running flake8 to check Python formatting.
IGNORED_CODES: list[str] = [
    "W503",  # line break before binary operator (W503 and W504 are mutually exclusive, so ignore both)
    "W504",  # line break  after binary operator (W503 and W504 are mutually exclusive, so ignore both)
    "E128",  # continuation line under-indented for visual indent
    "E201",  # whitespace after "("
    "E202",  # whitespace before ")"
    "E203",  # whitespace before ":"
    "E211",  # whitespace before "("
    "E221",  # multiple spaces before operator
    "E222",  # multiple spaces after  operator
    "E226",  # missing whitespace around arithmetic operator        (the fix doesn't work on the right side even with --aggressive)
    "E227",  # missing whitespace around bitwise or shift operator  (the fix doesn't work on the right side even with --aggressive)
    "E241",  # multiple spaces after ","
    "E251",  # unexpected spaces around keyword / parameter equals
    "E262",  # inline comment should start with "# "
    "E271",  # multiple spaces  after keyword
    "E272",  # multiple spaces before keyword
    "E701",  # multiple statements on one line (colon)
    "E702",  # multiple statements on one line (semicolon)
]

# Check for some characters that I personally dislike in Python source code:
BACKTICK            = "\u0060"  # U+0060 "GRAVE ACCENT" (the backtick)
LSQUOTE             = "\u2018"  # U+2018 "LEFT  SINGLE QUOTATION MARK" (curly apostrophe)
RSQUOTE             = "\u2019"  # U+2019 "RIGHT SINGLE QUOTATION MARK" (curly apostrophe)
LDQUOTE             = "\u201C"  # U+201C "LEFT  DOUBLE QUOTATION MARK"
RDQUOTE             = "\u201D"  # U+201D "RIGHT DOUBLE QUOTATION MARK"
HORIZONTAL_ELLIPSIS = "\u2026"  # U+2026 "HORIZONTAL ELLIPSIS" (three closely spaced periods)
EM_DASH             = "\u2014"  # U+2014 "EM DASH"


class Options:
    """Class that has all global options in one place."""

    def __init__(self) -> None:
        """Initialize the options with default values."""
        self.log_mode: int = logging.INFO
        self.home:    Path = Path.home()  # User's home directory


class PlotOptions(Options):
    """Global figure options."""

    def __init__(self) -> None:
        """Initialize PlotOptions class with values from the Options class, and default plotting values."""
        # Ideas for improving this parent class: https://chatgpt.com/share/6876a7e2-da84-8006-9c8f-100d243b73e4
        super().__init__()
        self.myfigsize  = (16, 9)
        self.fsize      = 24
        self.dpi_choice = 300
        # keep immutable "base" palettes so we can recompute safely
        self._base_colors      = ["black", "red",    "blue",      "green",      "purple"]
        self._base_lightcolors = ["grey",  "pink",   "lightblue", "lightgreen", "lightpurple"]
        self.markers           = ["o",     "s",      "^",         "v",          "<",          ">"]
        self.linestyles        = ["solid", "dashed", "dashdot",   "dotted"]

        self._dark_mode = False   # backing store
        self._apply_theme()       # derive palettes/background/text from _dark_mode

    @property
    def dark_mode(self) -> bool:
        """This is a property, so setting it will also update the theme."""
        return self._dark_mode

    @dark_mode.setter
    def dark_mode(self, value: int | bool) -> None:
        """This is a property with a setter, so any child class that changes self.dark_mode will also update the theme."""
        self._dark_mode = bool(value)
        self._apply_theme()

    def _apply_theme(self) -> None:
        """Apply the current theme (light or dark) to the plot options."""
        if self._dark_mode:
            self.background_color = "#000000"
            self.text_color       = "#FFFFFF"
            # recompute "view" palettes from the bases
            self.colors      = [ ("darkgrey" if  c == "black" else c) for c in self._base_colors ]
            self.lightcolors = [ ("lightgrey" if c == "grey"  else c) for c in self._base_lightcolors ]
        else:
            self.background_color = "#FFFFFF"
            self.text_color       = "#000000"
            self.colors      = list(self._base_colors)
            self.lightcolors = list(self._base_lightcolors)


class SelectionStrategy(str, Enum):
    """Enumeration of selection strategies for model selection."""
    CHEAPEST                 = "cheapest"
    CONTEXT_THEN_PRICE       = "context_then_price"
    CODE_SKILL_THEN_PRICE    = "code_skill_then_price"
    GENERAL_SKILL_THEN_PRICE = "general_skill_then_price"
    LOWEST_TTFT              = "lowest_TTFT"
    FASTEST                  = "fastest"
    SMALLEST                 = "smallest"


@dataclass
class LLMConfig:
    """Configuration for LLM selection and usage. Data only."""
    # Routing / engines
    allow_local_models: bool = True
    use_local_model:    bool = False
    local_model_name:    str = "ollama/qwen2.5-coder:1.5b-base"

    ollama_base_url:     str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    vllm_base_url:       str = os.getenv("VLLM_BASE_URL",   "http://localhost:8000")

    # Selection knobs
    selection_strategy: SelectionStrategy | str = SelectionStrategy.CHEAPEST
    min_context_tokens:                     int = 0
    assumed_prompt_tokens:                  int = 1000
    assumed_output_tokens:                  int = 1000

    # Candidates + scoring
    candidate_models:    list[str] = field(default_factory=list)    # if empty -> _default_candidate_models()

    # Optional: commonly-used knobs some programs keep near config
    default_temperature: float = 0.0
    max_tokens:            int = 1000

    model_scores: dict[str, float | dict[str, float]] = field(default_factory=dict)

    # --- multi-objective preferences ---
    prefer_code:                    bool = False  # emphasize coding skill
    prefer_low_TTFT:                bool = False  # emphasize time-to-first-token
    prefer_local:                   bool = False  # *prefer* local (not a hard requirement)
    max_estimated_cost:     float | None = None   # hard cap per (assumed_in, assumed_out)

    # Optional constraints
    speed_floor:              float | None = None   # minimum steady-state speed (in tokens/sec) (if known)

    # --- weights for the composite score (lower = better) ---
    # If a weight remains 0 but a corresponding prefer_* flag is True,
    # defaults are injected in _resolve_config() so you don't have to tune.
    weight_price:                  float = 1.0    # always keep some price pressure
    weight_code_skill:             float = 0.0
    weight_general_skill:          float = 0.0
    weight_TTFT:                   float = 0.0    # lower penalty when higher TTFT
    weight_speed:                  float = 0.0    # lower penalty when lower speed
    weight_nonlocal_penalty:       float = 0.0    # penalty if prefer_local=True and model is not local


_DEFAULT_MODEL_SKILL:      float =  0.5  # default skill level for models without specific default skill
_DEFAULT_MODEL_CONTEXT:      int = 8192  # default context window for models without specific context
_DEFAULT_MODEL_PARAMETERS: float = 9E99  # default number of parameters for models without specific parameter count


@dataclass
class ModelInfo:
    """Information about a candidate Large Language Model (LLM)."""
    name:                    str
    provider:                str  # e.g., "OpenAI", "Anthropic", "Mistral", "IBM"
    context_window:          int  # in+out, in tokens
    input_cost_per_token:  float  # $/token (normalized)
    output_cost_per_token: float  # $/token (normalized)
    available:              bool  # Is env/api key/endpoint reachable (best effort)?
    is_local:               bool  # True for Ollama, vLLM, or similar
    # Values without defaults have to be listed before values with defaults.
    runtime:        str | None = None  # e.g., "Ollama", "vLLM"
    parameters:            float = _DEFAULT_MODEL_PARAMETERS  # number of model parameters
    code_skill:            float = _DEFAULT_MODEL_SKILL  # 0..1, coding-centric capability
    general_skill:         float = _DEFAULT_MODEL_SKILL  # 0..1, broad/academic capability
    TTFT:           float | None = None  # time-to-first-token (seconds); None = unknown
    speed:          float | None = None  # tokens/sec after first token;  None = unknown
    meta:         dict[str, Any] = field(default_factory=dict)  # diagnostics/etc. not used for selection

    def __post_init__(self) -> None:
        """Post-initialization checks."""
        # Enforce runtime only when relevant.
        if self.is_local and not self.runtime:
            raise ValueError(f"runtime is required when is_local=True for model '{self.name}' (e.g., 'Ollama', 'vLLM').")

    def estimate_cost(self, tokens_in: int, tokens_out: int) -> float:
        """Estimate cost for a given input/output token count."""
        return self.input_cost_per_token * tokens_in + self.output_cost_per_token * tokens_out


@dataclass
class SelectionContext:
    """Context passed to strategy functions."""
    tokens_in:          int
    tokens_out:         int
    min_context_tokens: int
    require_local:     bool = False
    extras:  dict[str, Any] = field(default_factory=dict)


class StrategyFn(Protocol):
    """Strategy function interface."""
    def __call__(self, candidates: Sequence[ModelInfo], ctx: SelectionContext) -> ModelInfo: ...


class LLMs:
    """
    - Routes via LiteLLM
    - Builds ModelInfo list, filters by availability/context
    - Applies registered/built-in selection strategy
    - Exposes stable send_prompt(...)
    """
    # ----------------------------
    # Default model preferences
    # ----------------------------

    model_info: dict[str, dict[str, Any]] = {

        ##################################
        # OpenAI
        ##################################

        "gpt-3.5-turbo": {
            "provider"   : "OpenAI",
            "context"    : 16_385,
            "code_skill" : 0.60,
            "local"      : False,
            "parameters" : _DEFAULT_MODEL_PARAMETERS,
        },

        "gpt-4o-mini": {
            "provider"   : "OpenAI",
            "context"    : 128_000,
            "code_skill" : 0.80,     # improved smalls trend; near 4.1-mini on many evals [S6]
            "local"      : False,
            "parameters" : _DEFAULT_MODEL_PARAMETERS,
        },

        "gpt-4o": {
            "provider"   : "OpenAI",
            "context"    : 128_000,
            "code_skill" : 0.93,     # strong coding; multiple evals (Aider diff, SWE gains) [S6]
            "local"      : False,
            "parameters" : _DEFAULT_MODEL_PARAMETERS,
        },

        "gpt-4.1": {
            "provider"      : "OpenAI",
            "context"       : 1_000_000,  # [S5,S6]
            "code_skill"    : 0.94,       # OpenAI shows +21% vs 4o on SWE-bench Verified [S6]
            "general_skill" : 0.92,       # MMLU 90.2%, GPQA Diamond 66.3% [S6]
            "TTFT"          : 15.0,       # ~15s TTFT at 128k; ~60s at 1M (OpenAI) [S7]
            "speed"         : 124.0,      # ArtificialAnalysis provider aggregate [S2]
            "local"         : False,
            "parameters"    : _DEFAULT_MODEL_PARAMETERS,
        },

        "gpt-4.1-mini": {
            "provider"   : "OpenAI",
            "context"    : 1_000_000,  # [S6] (OpenAI says 4.1 family supports up to 1M)
            "code_skill" : 0.82,       # "beats 4o on many evals"; keep slightly above 4o-mini [S6]
            "speed"      : 75.8,       # AA aggregate (time-varying)
            "local"      : False,
            "parameters" : _DEFAULT_MODEL_PARAMETERS,
        },

        "gpt-4.1-nano": {
            "provider"   : "OpenAI",
            "context"    : 1_000_000,  # [S6]
            "code_skill" : 0.65,       # small, but 1M ctx and better than 4o-mini on some evals [S6]
            "TTFT"       : 5.0,        # "often <5s" for 128k inputs (OpenAI) [S7]
            "local"      : False,
            "parameters" : _DEFAULT_MODEL_PARAMETERS,
        },

        "o1-mini": {
            "provider"   : "OpenAI",
            "context"    : 128_000,  # context per OpenAI docs; o3/o4-mini are 200k [S28]
            "code_skill" : 0.86,     # strong reasoning; coding solid but slower TTFT [S14,S7]
            "local"      : False,
            "parameters" : _DEFAULT_MODEL_PARAMETERS,
        },

        "o3-mini": {
            "provider"      : "OpenAI",
            "context"       : 200_000,  # [S28]
            "code_skill"    : 0.88,     # faster TTFT than o1-mini; coding near o1 mini [S12,S6]
            "general_skill" : 0.89,     # strong reasoning for size [S6,S7]
            "TTFT"          : 8.0,      # AA & coverage: higher latency than smalls, but improved vs o1 [S14,S7]
            "speed"         : 163.0,    # AA [S12]
            "local"         : False,
            "parameters"    : _DEFAULT_MODEL_PARAMETERS,
        },

        "o4-mini": {
            "provider"   : "OpenAI",
            "context"    : 200_000,  # [S28]
            "code_skill" : 0.90,     # newer small reasoning; top small-code in AA index
            "local"      : False,
            "parameters" : _DEFAULT_MODEL_PARAMETERS,
        },

        "gpt-5": {
            "provider"      : "OpenAI",
            "context"       : 400_000,  # API total context, 128k max output (OpenAI) [S1]
            "code_skill"    : 0.96,     # frontier; AA shows top "intelligence index" class [S1,S21]
            "general_skill" : 0.95,     # AA Intelligence Index leader tier [S1,S21]
            "local"         : False,
            "parameters"    : _DEFAULT_MODEL_PARAMETERS,
        },

        ##################################
        # Anthropic
        ##################################

        "claude-3-haiku-20240229": {
            "provider"   : "Anthropic",
            "context"    : 200_000,  # Anthropic docs & vendor pages [S26,S27]
            "code_skill" : 0.70,
            "local"      : False,
            "parameters" : _DEFAULT_MODEL_PARAMETERS,
        },

        "claude-3-5-sonnet-20241022": {
            "provider"   : "Anthropic",
            "context"    : 200_000,  # [S26,S27]
            "code_skill" : 0.92,
            "local"      : False,
            "parameters" : _DEFAULT_MODEL_PARAMETERS,
        },

        "claude-3-7-sonnet-20250219": {
            "provider"      : "Anthropic",
            "context"       : 200_000,  # [S21,S26,S27] (Sonnet 4 has 1M, not 3.7) [S20]
            "code_skill"    : 0.93,     # leads/near-top on SWE-bench Verified [S13,S16]
            "general_skill" : 0.90,     # hybrid reasoning; strong OSWorld & agentic [S16]
            "TTFT"          : 1.16,     # ~1.16s avg; reports of ~0.2s for quick replies (varies) [S36]
            "speed"         : 65.5,     # AA [S36]
            "local"         : False,
            "parameters"    : 123E9,
        },

        ##################################
        # Mistral
        ##################################

        "mistral-large-2": {
            "provider"      : "Mistral",
            "context"       : 128_000,  # product pages and summaries [S9,S23]
            "code_skill"    : 0.90,     # claims match GPT-4o on coding; multiple writeups [S11,S17]
            "general_skill" : 0.86,     # broad improvements vs Large 1; multilingual [S9]
            "local"         : False,
            "parameters"    : _DEFAULT_MODEL_PARAMETERS,
        },

        "mistral-medium-2505": {
            "provider"   : "Mistral",
            "context"    : 128_000,  # [S8]
            "code_skill" : 0.82,     # below Large, above earlier Mediums; frontier multi [S8]
            "local"      : False,
            "parameters" : _DEFAULT_MODEL_PARAMETERS,
        },

        "codestral-25.01": {
            "provider"   : "Mistral",
            "context"    : 256_000,  # Mistral docs list Codestral 25.01/25.08 at 256k [S8,S10]
            "code_skill" : 0.86,     # upgraded Codestral; ~2x speed & strong HE/MBPP [S10,S9]
            "local"      : False,
            "parameters" : _DEFAULT_MODEL_PARAMETERS,
        },

        "codestral-25.08": {
            "provider"   : "Mistral",
            "context"    : 256_000,  # [S8]
            "code_skill" : 0.88,     # latest Codestral (summer 2025) [S8]
            "local"      : False,
            "parameters" : _DEFAULT_MODEL_PARAMETERS,
        },

        ##################################
        # Local (Ollama)
        # Local models are hardware-dependent; leave None to encourage live measurement:
        # local models -> measure at runtime
        ##################################

        "ollama/qwen2.5-coder:1.5b-base": {
            "provider"   : "Alibaba Cloud",
            "context"    : 32_768,
            "code_skill" : 0.41,    # ~41 average across 9 langs for 1.5B *base* [S3]
            "local"      : True,
            "runtime"    : "Ollama",
            "parameters" : 1.5E9,
        },

        "ollama/qwen2.5-coder:3b-base": {
            "provider"   : "Alibaba Cloud",
            "context"    : 32_768,
            "code_skill" : 0.48,    # ~48 average across 9 langs for 3B *base* [S3]
            "local"      : True,
            "runtime"    : "Ollama",
            "parameters" : 3.0E9,
        },

        "ollama/codegemma:2b-code": {
            "provider"   : "Google",
            "context"    : 8_192,   # [S38, S39]
            "code_skill" : 0.311,   # HumanEval pass@1 = 31.1% (official model card)
            "local"      : True,
            "runtime"    : "Ollama",
            "parameters" : 2.0E9,
        },

        "ollama/starcoder2:3b": {
            "provider"   : "BigCode",
            "context"    : 16_384,  # StarCoder2 smalls default 16k
            "code_skill" : 0.317,   # ~31.7% pass@1 typical; ~31.1 avg across langs in Qwen2.5 tbl [S3,S30]
            "local"      : True,
            "runtime"    : "Ollama",
            "parameters" : 3.0E9,
        },

        "ollama/granite-code:3b": {
            "provider"   : "IBM",
            "context"    : 128_000,  # IBM Granite-3B-Code-Instruct-128K [S18]
            "code_skill" : 0.262,    # [S40, S41]
            "local"      : True,
            "runtime"    : "Ollama",
            "parameters" : 3.0E9,
        },

        "ollama/phi3.5:3.8b": {
            "provider"      : "Microsoft",
            "context"       : 128_000,  # Microsoft release/Foundry catalog [S34]
            "code_skill"    : 0.56,     # mid-estimate: reports cluster ~0.50–0.63 HE for 3.5-mini [S31,S33]
            "general_skill" : 0.69,     # Phi-3 mini MMLU ~69%; 3.5 mini similar+ [S32]
            "local"         : True,
            "runtime"       : "Ollama",
            "parameters"    : 3.8E9,
        },

        "ollama/mistral:7b-instruct-q4_0": {
            "provider"      : "Mistral",
            "context"       : 8_192,     # conservative default; some builds enable up to ~32k
            "code_skill"    : 0.52,      # solid general LLM; decent coding for 7B instruct
            "general_skill" : 0.64,      # typical bench range for Mistral-7B-Instruct [S42, S43, S44]
            "local"         : True,
            "runtime"       : "Ollama",
            "parameters"    : 7.0E9,
        },

        "ollama/llama3:8b": {
            "provider"      : "Meta",
            "context"       : 8_192,
            "code_skill"    : 0.55,   # aligns w/ public mid-tier code results
            "general_skill" : 0.66,   # Llama3-8B MMLU ballpark; public reports ~66–67% [S35]
            "local"         : True,
            "runtime"       : "Ollama",
            "parameters"    : 8.0E9,
        },

        "ollama/llama3.1:8b-instruct-q4_0": {
            "provider"      : "Meta",
            "context"       : 128_000,   # Llama 3.1 8B supports 128k
            "code_skill"    : 0.58,      # slight bump vs Llama 3 8B; quantized
            "general_skill" : 0.70,      # stronger reasoning/knowledge vs 3.0 [S45, S46]
            "local"         : True,
            "runtime"       : "Ollama",
            "parameters"    : 8.0E9,
        },
    }

    ##################################
    # References
    ##################################
    #  S1 — OpenAI: Introducing GPT-5 for developers — https://openai.com/index/introducing-gpt-5-for-developers/
    #  S2 — Artificial Analysis: GPT-4.1 (speed/latency/TPS aggregates) — https://artificialanalysis.ai/models/gpt-4-1
    #  S3 — Aider LLM Leaderboards (Polyglot code-editing benchmark) — https://aider.chat/docs/leaderboards/
    #  S4 — OpenAI: Introducing GPT-5 (overview/benchmarks) — https://openai.com/index/introducing-gpt-5/
    #  S5 — OpenAI: Introducing GPT-4.1 in the API (capabilities & SWE-bench Verified) — https://openai.com/index/gpt-4-1/
    #  S6 — OpenAI: GPT-4.1 long-context details (up to 1M tokens) — https://openai.com/index/gpt-4-1/#long-context
    #  S7 — Artificial Analysis: GPT-4.1 (Providers view; TTFT/output speed) — https://artificialanalysis.ai/models/gpt-4-1/providers
    #  S8 — Mistral Docs: Models Overview (incl. mistral-medium-2505/2508, codestral-2508) — https://docs.mistral.ai/getting-started/models/models_overview/
    #  S9 — Mistral Blog: "Large Enough" (Mistral Large 2; 128k context, positioning) — https://mistral.ai/news/mistral-large-2407
    # S10 — Mistral Blog: Codestral 25.01 announcement — https://mistral.ai/news/codestral-2501
    # S11 — Artificial Analysis: Mistral Large 2 (quality/price/speed aggregates) — https://artificialanalysis.ai/models/mistral-large-2
    # S12 — Artificial Analysis: o3-mini (speed/latency metrics) — https://artificialanalysis.ai/models/o3-mini
    # S13 — OpenAI: Introducing o3 and o4-mini (reasoning series) — https://openai.com/index/introducing-o3-and-o4-mini/
    # S14 — TextCortex review: o3-mini vs o1-mini (relative response speed) — https://textcortex.com/post/openai-o3-mini-review
    # S15 — Mistral Docs: Codestral 2508 (latest Codestral release entry) — https://docs.mistral.ai/getting-started/models/models_overview/#codestral-2508
    # S16 — Anthropic News: Claude 3.7 Sonnet launch/overview — https://www.anthropic.com/news/claude-3-7-sonnet
    # S17 — AWS Blog: Mistral Large 2 now in Bedrock (confirms 128k context) — https://aws.amazon.com/blogs/machine-learning/mistral-large-2-is-now-available-in-amazon-bedrock/
    # S18 — IBM Granite-3B-Code-Instruct model card (context/perf references) — https://huggingface.co/ibm-granite/granite-3b-code-instruct
    # S19 — OpenAI: New tools & features in the Responses API (o3/o4-mini integration; 2025) — https://openai.com/index/new-tools-and-features-in-the-responses-api/
    # S20 — Anthropic News: Claude Opus 4.1 (SWE-bench Verified 74.5%) — https://www.anthropic.com/news/claude-opus-4-1
    # S21 — OpenAI: GPT-5 (coding focus; SWE-bench methodology note) — https://openai.com/index/introducing-gpt-5/
    # S22 — The Verge: GPT-4.1 in ChatGPT (rollout; context & coding improvements) — https://www.theverge.com/news/667507/openai-chatgpt-gpt-4-1-ai-model-general-availability
    # S23 — NVIDIA NIM Ref: Mistral Large 2 Instruct (128k context confirmation) — https://docs.api.nvidia.com/nim/reference/mistralai-mistral-large-2-instruct
    # S24 — OpenAI Blog: GPT-4o mini (128k context & pricing) — https://openai.com/index/gpt-4o-mini-advancing-cost-efficient-intelligence/
    # S25 — OpenAI Docs: o4-mini model page — https://platform.openai.com/docs/models/o4-mini
    # S26 — Qwen2.5-Coder technical report (benchmarks overview) — https://arxiv.org/abs/2501.03012
    # S27 — HF Model Card: Qwen2.5-Coder-3B-Base — https://huggingface.co/Qwen/Qwen2.5-Coder-3B
    # S28 — OpenAI Help: o3 & o4-mini context (200k) — https://help.openai.com/en/articles/9855712-openai-o1-models-faq-chatgpt-enterprise-and-edu
    # S29 — StarCoder2 paper (model details; evals) — https://arxiv.org/abs/2402.19173
    # S30 — HF Model Card: BigCode/StarCoder2-3B — https://huggingface.co/bigcode/starcoder2-3b
    # S31 — Phi-3 Technical Report (MMLU 69% etc.) — https://arxiv.org/abs/2404.14219
    # S32 — Meta Llama 3 models overview (general capability references) — https://www.llama.com/models/llama-3/
    # S33 — HF Model Card: microsoft/Phi-3-mini-128k-instruct (3.8B; 128k ctx) — https://huggingface.co/microsoft/Phi-3-mini-128k-instruct
    # S34 — NVIDIA NIM / HF: Phi-3.5-MoE (128k ctx; MoE details) — https://docs.api.nvidia.com/nim/reference/microsoft-phi-3_5-moe
    # S35 — HF Model Card: meta-llama/Meta-Llama-3-8B (8k ctx; base references) — https://huggingface.co/meta-llama/Meta-Llama-3-8B
    # S36 — Artificial Analysis: Claude 3.7 Sonnet (standard/thinking; TTFT & TPS) — https://artificialanalysis.ai/models/claude-3-7-sonnet / https://artificialanalysis.ai/models/claude-3-7-sonnet-thinking
    # S37 — OpenAI Community - https://community.openai.com/t/what-is-the-token-context-window-size-of-the-gpt-4-o1-preview-model/954321
    # S38 - https://huggingface.co/google/codegemma-2b
    # S39 - https://arxiv.org/pdf/2406.11409
    # S40 - https://huggingface.co/ibm-granite/granite-3b-code-instruct-128k/blame/main/README.md
    # S41 - https://www.ibm.com/docs/en/watsonx/w-and-w/2.2.0?topic=models-granite-3b-code-instruct-v2-model-card
    # S42 - MMLU-CF leaderboard — row "Mistral-7B-instruct-v0.3" (MMLU 5-shot 60.3; MMLU-CF 5-shot 50.7; also 0-shot values) - https://github.com/microsoft/MMLU-CF
    # S43 - Evaluating Code Quality from Quantized LLMs — reports Mistral Instruct 7B HumanEval+ pass@1 ≈ 25% (notes the EvalPlus variant) - https://arxiv.org/pdf/2411.10656
    # S44 - Mistral 7B announcement — qualitative coding claim "approaches CodeLlama 7B performance on code" - https://mistral.ai/news/announcing-mistral-7b
    # S45 - Meta Llama 3.1 8B Instruct model card — instruction-tuned benchmarks incl. MMLU 69.4, HumanEval 72.6, MBPP++ 72.8 - https://huggingface.co/meta-llama/Llama-3.1-8B-Instruct
    # S46 - Llama 3.1 8B Instruct eval details dataset — per-task results backing the model card table - https://huggingface.co/datasets/meta-llama/Llama-3.1-8B-Instruct-evals

    # Provider -> required env var
    _provider_env: dict[str, str] = {
        "OpenAI"    : "OPENAI_API_KEY",
        "Anthropic" : "ANTHROPIC_API_KEY",
        "Mistral"   : "MISTRAL_API_KEY",
    }

    _vllm_aliases = ("vllm", "vllm-openai", "vllm_compatible", "vlm")

    # ---------- public lifecycle ----------
    def __init__(self) -> None:
        """Initialize LLMs manager. Call apply_config() before use."""
        # LiteLLM configuration:
        self._config:                           LLMConfig | None = None
        self._selected:                         ModelInfo | None = None
        self._candidates_after_filter:           list[ModelInfo] = []
        self._strategies:                  dict[str, StrategyFn] = {}
        self._last_strategy:                                 str = str(SelectionStrategy.CHEAPEST.value)
        self._pricing_cache: dict[str, tuple[float, float, int]] = {}
        self._litellm_ready:                                bool = False  # True when/if LiteLLM client has been imported
        self._litellm_mod:                            Any | None = None
        self._register_builtin_strategies()

    @property
    def selected(self) -> ModelInfo | None:
        """Read-only handle to the currently selected model (or None)."""
        return self._selected

    @property
    def model(self) -> str | None:
        """Selected model name."""
        return self._selected.name     if self._selected else None

    @property
    def provider(self) -> str | None:
        """Selected provider name."""
        return self._selected.provider if self._selected else None

    # ---------- config application ----------
    def apply_config(self, config: LLMConfig) -> None:
        """
        Store config, hydrate defaults, compute candidates, select a model.
        """
        cfg = self._resolve_config(config)
        self._config = cfg

        if cfg.use_local_model:
            entry = self.model_info.get(cfg.local_model_name, {})
            if not entry.get("local", False):
                raise RuntimeError(f"cfg.use_local_model is {cfg.use_local_model} but '{cfg.local_model_name}' is not marked as local in the registry.")
            if entry.get("local") is True:
                provider = entry.get("provider", "Local")
                if not self._is_provider_available(provider, cfg.local_model_name):
                    raise RuntimeError(
                        f"Local model '{cfg.local_model_name}' is not available on runtime "
                        f"'{entry.get('runtime', 'unknown')}'. Ensure the runtime is up "
                        f"(Ollama: {cfg.ollama_base_url}) and that the model is pulled."
                    )

        # Forced-local short-circuit preserved
        if cfg.use_local_model:
            chosen                        = self._build_model_info(cfg.local_model_name, cfg)
            self._selected                = chosen
            self._candidates_after_filter = [chosen]
            self._after_selection(chosen.name, chosen.provider)
            return

        # Build pool and context with the resolved cfg
        eff, ctx, reasons_map = self._selection_pool(cfg)

        # Choose strategy (same logic you already have)
        if isinstance(cfg.selection_strategy, SelectionStrategy):
            strategy_name = cfg.selection_strategy.value
        else:
            strategy_name = str(cfg.selection_strategy)

        wants_multi = any([
            cfg.prefer_code,
            cfg.prefer_low_TTFT,cfg.prefer_local,
            cfg.max_estimated_cost is not None,
            cfg.speed_floor        is not None,
            cfg.weight_code_skill       > 0.0,
            cfg.weight_general_skill    > 0.0,
            cfg.weight_TTFT             > 0.0,
            cfg.weight_speed            > 0.0,
            cfg.weight_nonlocal_penalty > 0.0,
        ])
        if wants_multi and strategy_name == SelectionStrategy.CHEAPEST.value:
            strategy_name = "multi_objective"

        strategy_fn         = self._strategies.get(strategy_name) or \
                              self._strategies[SelectionStrategy.CHEAPEST.value]
        self._last_strategy = strategy_name

        winner              = strategy_fn(eff, ctx)
        self._selected      = winner
        self._candidates_after_filter = eff
        for mi in self._candidates_after_filter:
            mi.meta["filter_reasons"] = reasons_map.get(mi.name, [])
        self._after_selection(winner.name, winner.provider)

    def refresh_selection(self) -> None:
        """Re-run selection using the current LLMConfig."""
        if self._config is None:
            my_critical_error("refresh_selection() called before apply_config().")
        self.apply_config(self._config)

    def get_config(self) -> LLMConfig:
        """Return a copy of the current config (or default if none applied yet)."""
        if self._config is None:
            # Return a default config if none applied yet.
            return LLMConfig()
        return replace(self._config)

    # ---------- strategy registry ----------
    def register_strategy(self, name: str, fn: StrategyFn) -> None:
        """Register a custom strategy for model selection."""
        self._strategies[name] = fn

    def _register_builtin_strategies(self) -> None:
        """Define built-in strategies for model selection."""

        def cheapest(cands: Sequence[ModelInfo], ctx: SelectionContext) -> ModelInfo:
            """Cheapest model among candidates, ignoring any other factors."""
            return min(cands, key=lambda m: m.estimate_cost(ctx.tokens_in, ctx.tokens_out))

        def context_then_price(cands: Sequence[ModelInfo], ctx: SelectionContext) -> ModelInfo:
            """Context-aware selection, then price."""
            # cands already filtered by context; cheapest among them
            return min(cands, key=lambda m: m.estimate_cost(ctx.tokens_in, ctx.tokens_out))

        def code_skill_then_price(cands: Sequence[ModelInfo], ctx: SelectionContext) -> ModelInfo:
            """Highest code skill, then cheapest among those."""
            def key(m: ModelInfo) -> tuple[float, float]:
                """Key function for code_skill-then-price strategy."""
                return (-m.code_skill, m.estimate_cost(ctx.tokens_in, ctx.tokens_out))
            return min(cands, key=key)

        def general_skill_then_price(cands: Sequence[ModelInfo], ctx: SelectionContext) -> ModelInfo:
            """Highest general skill, then cheapest among those."""
            def key(m: ModelInfo) -> tuple[float, float]:
                """Key function for general_skill-then-price strategy."""
                return (-m.general_skill, m.estimate_cost(ctx.tokens_in, ctx.tokens_out))
            return min(cands, key=key)

        def lowest_TTFT(cands: Sequence[ModelInfo], ctx: SelectionContext) -> ModelInfo:
            """
            Lowest TTFT (Time To First Token) among candidates.
            Treat unknown TTFT as worst; tie-break by price.
            """
            def key(m: ModelInfo) -> tuple[float, float]:
                """Key function for lowest_TTFT strategy."""
                TTFT = m.TTFT if m.TTFT is not None else float("inf")
                return (TTFT, m.estimate_cost(ctx.tokens_in, ctx.tokens_out))
            return min(cands, key=key)

        def fastest(cands: Sequence[ModelInfo], ctx: SelectionContext) -> ModelInfo:
            """
            Fastest model among candidates.
            Highest speed is best; unknown speed is worst; tie-break by price.
            """
            def key(m: ModelInfo) -> tuple[float, float]:
                """Key function for fastest strategy."""
                sp = m.speed if m.speed is not None else -1.0
                # We invert for max; min() will prefer higher speed by sorting negative
                return (-sp, m.estimate_cost(ctx.tokens_in, ctx.tokens_out))
            return min(cands, key=key)

        def smallest(cands: Sequence[ModelInfo], ctx: SelectionContext) -> ModelInfo:
            """Model with fewest parameters among candidates."""
            return min(cands, key=lambda m: m.parameters)

        def multi_objective(cands: Sequence[ModelInfo], ctx: SelectionContext) -> ModelInfo:
            """Using multiple preferences and weights, choose the best-fit model."""
            cfg = self._config or LLMConfig()

            # Group stats for normalization
            costs     = [m.estimate_cost(cfg.assumed_prompt_tokens,
                                         cfg.assumed_output_tokens) for m in cands]
            max_cost  = max(costs) if costs else 1.0

            TTFTs     = [m.TTFT for m in cands if m.TTFT is not None]
            max_TTFT  = max(TTFTs) if TTFTs else 1.0

            speeds    = [m.speed for m in cands if m.speed is not None]
            max_speed = max(speeds) if speeds else 1.0

            def key(m: ModelInfo) -> float:
                """Key function for multi-objective optimization."""
                # Hard caps first: if user set max cost, filter; if all filtered, caller will fallback
                est_cost = m.estimate_cost(cfg.assumed_prompt_tokens, cfg.assumed_output_tokens)
                if cfg.max_estimated_cost is not None and est_cost > cfg.max_estimated_cost:
                    return float("inf")

                # Normalized penalties (0=best)
                cost_pen = est_cost / max_cost if max_cost > 0 else 0.0

                if m.TTFT is not None and max_TTFT > 0:
                    TTFT_pen = m.TTFT / max_TTFT
                else:
                    TTFT_pen = 1.0  # unknown => mild penalty if weighted

                if m.speed is not None and max_speed > 0:
                    speed_pen = 1.0 - (m.speed / max_speed)  # higher speed => lower penalty
                else:
                    speed_pen = 1.0  # unknown speed

                code_pen = 1.0 - (m.code_skill    if m.code_skill    is not None else _DEFAULT_MODEL_SKILL)
                gen_pen  = 1.0 - (m.general_skill if m.general_skill is not None else _DEFAULT_MODEL_SKILL)
                nonlocal_pen = 0.0 if m.is_local else 1.0

                # Optional floor on speed (soft penalty, not exclusion)
                if cfg.speed_floor is not None:
                    if (m.speed is None) or (m.speed < cfg.speed_floor):
                        speed_pen += 1.0

                score = (  cfg.weight_price            * cost_pen
                         + cfg.weight_TTFT             * TTFT_pen
                         + cfg.weight_speed            * speed_pen
                         + cfg.weight_code_skill       * code_pen
                         + cfg.weight_general_skill    * gen_pen
                         + cfg.weight_nonlocal_penalty * nonlocal_pen)
                return score

            return min(cands, key=key)

        self._strategies[SelectionStrategy.CHEAPEST.value]                 = cheapest
        self._strategies[SelectionStrategy.CONTEXT_THEN_PRICE.value]       = context_then_price
        self._strategies[SelectionStrategy.CODE_SKILL_THEN_PRICE.value]    = code_skill_then_price
        self._strategies[SelectionStrategy.GENERAL_SKILL_THEN_PRICE.value] = general_skill_then_price
        self._strategies[SelectionStrategy.LOWEST_TTFT.value]              = lowest_TTFT
        self._strategies[SelectionStrategy.FASTEST.value]                  = fastest
        self._strategies[SelectionStrategy.SMALLEST.value]                 = smallest
        self._strategies["multi_objective"]                                = multi_objective

    # ---------- selection introspection ----------
    def list_candidates(self, with_reasons: bool = False) -> list[ModelInfo]:
        """
        Return the candidate list after filtering (or just the selected if forced local).
        If with_reasons=True, include 'filter_reasons' in meta where applicable.
        """
        res = [replace(mi, meta=dict(mi.meta)) for mi in self._candidates_after_filter]  # deep-copy meta
        if not with_reasons:
            for mi in res:
                mi.meta.pop("filter_reasons", None)
        return res

    def _selection_pool(self, cfg: LLMConfig) -> tuple[list[ModelInfo], SelectionContext]:
        """Build the effective candidate pool and SelectionContext for a given config."""
        # Forced-local short-circuit → caller should handle, but keep this as a guard
        if cfg.use_local_model:
            # validate local availability (reuse the same checks as apply_config)
            entry = self.model_info.get(cfg.local_model_name, {})
            if not entry.get("local", False):
                raise RuntimeError(f"cfg.use_local_model is {cfg.use_local_model} but '{cfg.local_model_name}' is not marked as local in the registry.")
            provider = entry.get("provider", "Local")
            if not self._is_provider_available(provider, cfg.local_model_name):
                raise RuntimeError(
                    f"Local model '{cfg.local_model_name}' is not available on runtime "
                    f"'{entry.get('runtime', 'unknown')}'. Ensure the runtime is up "
                    f"(Ollama: {cfg.ollama_base_url}) and that the model is pulled."
                )
            mi = self._build_model_info(cfg.local_model_name, cfg)
            ctx = SelectionContext(
                tokens_in=cfg.assumed_prompt_tokens,
                tokens_out=cfg.assumed_output_tokens,
                min_context_tokens=cfg.min_context_tokens,
                require_local=True,
            )
            return [mi], ctx
        raw_candidates = [self._build_model_info(m, cfg) for m in cfg.candidate_models]
        ctx = SelectionContext(
            tokens_in=cfg.assumed_prompt_tokens,
            tokens_out=cfg.assumed_output_tokens,
            min_context_tokens=cfg.min_context_tokens,
            require_local=False,
        )
        filtered, reasons_map = self._filter_candidates(raw_candidates, ctx)
        eff = filtered if filtered else raw_candidates
        if cfg.max_estimated_cost is not None:
            tmp = [m for m in eff if m.estimate_cost(cfg.assumed_prompt_tokens, cfg.assumed_output_tokens) <= cfg.max_estimated_cost]
            if tmp:
                eff = tmp
        if cfg.speed_floor is not None:
            tmp = [m for m in eff if (m.speed is not None and m.speed >= cfg.speed_floor)]
            if tmp:
                eff = tmp
        if not eff:
            raise RuntimeError(
                "No candidates available after filtering. "
                "Check allow_local_models, min_context_tokens, candidate_models, and provider availability."
            )
        return eff, ctx, reasons_map

    def alternative_model(self, *, strategy: SelectionStrategy | str,
                          return_reasons: bool = False, **cfg_overrides) -> ModelInfo:
        """
        Return the best candidate under a given strategy using a TEMPORARY config
        built from the current config + partial overrides (e.g., use_local_model=True),
        WITHOUT mutating the current selection.
        """
        from dataclasses import replace as _dc_replace
        base_cfg = self.get_config()  # snapshot of current config (already resolved by apply_config)
        # apply partial overrides
        try:
            tmp_cfg = _dc_replace(base_cfg, **cfg_overrides)
        except TypeError as e:
            raise ValueError(f"Invalid override(s): {e}")
        # Re-resolve in case overrides trigger weight injections, etc.
        tmp_cfg  = self._resolve_config(tmp_cfg)
        # Build pool (handles forced-local inside)
        eff, ctx, reasons_map = self._selection_pool(tmp_cfg)
        # Pick strategy
        name = strategy.value if isinstance(strategy, SelectionStrategy) else str(strategy)
        fn = self._strategies.get(name)
        if fn is None:
            raise ValueError(f"Unknown strategy: {name}")
        winner = fn(eff, ctx)
        return (winner, reasons_map) if return_reasons else winner

    def describe_selection(self) -> dict[str, Any]:
        """Describe the current model selection."""
        chosen = self._selected
        cfg = self._config or LLMConfig()
        if chosen is None:
            return {
                "chosen_model" : None,
                "provider"     : None,
                "strategy"     : getattr(self, "_last_strategy", str(cfg.selection_strategy)),
                "explanation"  : "No selection computed yet. Call apply_config().",
            }
        considered = []
        for mi in self._candidates_after_filter:
            considered.append({
                "name"                  : mi.name,
                "provider"              : mi.provider,
                "context_window"        : mi.context_window,
                "input_cost_per_token"  : mi.input_cost_per_token,
                "output_cost_per_token" : mi.output_cost_per_token,
                "code_skill"            : mi.code_skill,
                "general_skill"         : mi.general_skill,
                "TTFT"                  : mi.TTFT,
                "speed"                 : mi.speed,
                "estimated_cost"        : mi.estimate_cost(cfg.assumed_prompt_tokens,
                                                           cfg.assumed_output_tokens),
                "available"             : mi.available,
                "local"                 : mi.is_local,
                "runtime"               : mi.runtime,
            })
        return {
            "chosen_model"   : chosen.name,
            "provider"       : chosen.provider,
            "context_window" : chosen.context_window,
            "estimated_cost" : chosen.estimate_cost(cfg.assumed_prompt_tokens,
                                                    cfg.assumed_output_tokens),
            "strategy"       : getattr(self, "_last_strategy", str(cfg.selection_strategy)),
            "weights"        : {
                "price"                  : cfg.weight_price,
                "code_skill"             : cfg.weight_code_skill,
                "general_skill"          : cfg.weight_general_skill,
                "TTFT"                   : cfg.weight_TTFT,
                "speed"                  : cfg.weight_speed,
                "nonlocal_penalty"       : cfg.weight_nonlocal_penalty,
            },
            "prefs": {
                "prefer_code"            : cfg.prefer_code,
                "prefer_low_TTFT"        : cfg.prefer_low_TTFT,
                "prefer_local"           : cfg.prefer_local,
                "max_estimated_cost"     : cfg.max_estimated_cost,
                "speed_floor"            : cfg.speed_floor,
            },
            "considered": considered,
        }

    # ---------- core send method (stable) ----------
    def send_prompt(self, prompt: str, system_message: str,
                    model: str, temperature: float,
                    max_tokens: int = 1000) -> str:
        """
        Send a prompt+system message to the specified model, return the text response.

        Args:
            prompt:         The user prompt to send.
            system_message: The system message to include.
            model:          The model name to use (must be in model_info).
            temperature:    Sampling temperature.
            max_tokens:     Maximum tokens to generate in the response.
        
        Returns:
            The text response from the model.
        
        Raises:
            RuntimeError: If the model is unknown or if the request fails.
            ValueError:   If the prompt is empty.
        """
        self._ensure_litellm()
        litellm = self._litellm_mod  # type: ignore
        extra   = self._extra_litellm_args_for(model)
        try:
            resp = litellm.completion(
                model=model,
                messages=[{"role": "system", "content": system_message},
                          {"role": "user",   "content": prompt}],
                temperature=temperature,
                max_tokens=max_tokens,
                **extra
            )
        except Exception as e:
            my_critical_error(f"LiteLLM request failed for model '{model}': {e}")
        return self._extract_text_from_openai_like(resp)

    # ====================================================
    # overridable hooks (tiny, intentional)
    # ====================================================
    def _default_candidate_models(self) -> list[str]:
        """Return a sane default list combining remote + local names."""
        return list(self.model_info.keys())

    def _extra_litellm_args_for(self, model: str) -> dict[str, Any]:
        """
        Per-model transport args for LiteLLM (e.g., {'api_base': self.ollama_base_url}
        for "runtime == "Ollama"). Default returns {}.
        """
        cfg   = self._config or LLMConfig()
        entry = self.model_info.get(model, {})
        runtime = (entry.get("runtime") or "").strip().casefold()
        if entry.get("local") is True and runtime:
            if runtime == "ollama":
                base = (cfg.ollama_base_url or "").rstrip("/")
                return {"api_base": base} if base else {}
            if runtime in self._vllm_aliases:
                base = (cfg.vllm_base_url or "").rstrip("/")
                return {"api_base": base} if base else {}
        return {}

    def _after_selection(self, model: str, provider: str) -> None:
        """Optional hook for telemetry/logging; default no-op."""
        logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("Selected model %s (%s)", model, provider)

    # ====================================================
    # internals
    # ====================================================

    def _resolve_config(self, config: LLMConfig) -> LLMConfig:
        """Hydrate defaults: candidates, scores (with env JSON merge)."""
        # Candidate models
        cands = list(config.candidate_models) if config.candidate_models else self._default_candidate_models()
        if not config.allow_local_models:
            cands = [m for m in cands if not self.model_info.get(m, {}).get("local", False)]

        # Merge env JSON (if present) into cfg.model_scores; allow both float and {'code','general'} forms
        scores        = dict(config.model_scores)  # copy
        json_path_str = os.getenv("LLM_MODEL_SCORES_JSON")
        if json_path_str:
            try:
                import json
                with open(json_path_str, "r", encoding=DEFAULT_ENCODING) as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    scores.update(data)
            except Exception as e:
                logging.warning("Failed to load LLM_MODEL_SCORES_JSON from %s: %s", json_path_str, e)

        hydrated = replace(config, candidate_models=cands, model_scores=scores)

        # If user flipped prefs but left weights at 0, inject reasonable defaults.
        # Price stays at 1.0 unless user overrides.
        if hydrated.prefer_code and hydrated.weight_code_skill == 0.0:
            hydrated = replace(hydrated, weight_code_skill=0.60)
        if hydrated.prefer_low_TTFT and hydrated.weight_TTFT == 0.0:
            hydrated = replace(hydrated, weight_TTFT=0.40)
        if hydrated.prefer_local and hydrated.weight_nonlocal_penalty == 0.0:
            hydrated = replace(hydrated, weight_nonlocal_penalty=0.30)
        # You can optionally bias throughput when TTFT isn't critical
        if hydrated.weight_speed == 0.0 and not hydrated.prefer_low_TTFT and hydrated.speed_floor:
            hydrated = replace(hydrated, weight_speed=0.20)

        return hydrated

    def _filter_candidates(self, candidates: list[ModelInfo],
                           ctx: SelectionContext) -> tuple[list[ModelInfo], dict[str, list[str]]]:
        """Filter by availability, context, and optional locality. Return filtered list and reasons per model name."""
        filtered: list[ModelInfo] = []
        reasons: dict[str, list[str]] = {}
        for mi in candidates:
            r: list[str] = []
            if not mi.available:
                r.append("provider_not_available")
            if mi.context_window < ctx.min_context_tokens:
                r.append(f"context_too_small({mi.context_window}<{ctx.min_context_tokens})")
            if ctx.require_local and not mi.is_local:
                r.append("requires_local")
            if r:
                reasons[mi.name] = r
            else:
                filtered.append(mi)
                reasons[mi.name] = []  # << capture "no reasons" for included models
        return filtered, reasons

    def _is_provider_available(self, provider: str, model: str) -> bool:
        """Check if a model provider is available."""
        entry = self.model_info.get(model, {})
        if entry.get("local") is True:
            runtime = (entry.get("runtime") or "").strip().casefold()

            if runtime == "ollama":
                cfg = self._config or LLMConfig()
                base = (cfg.ollama_base_url or "").rstrip("/")
                if not base:
                    return False

                # Ping /api/tags to ensure server is up and to list pulled models
                data = self._http_get_json(f"{base}/api/tags", timeout=2.0)
                if not isinstance(data, dict):
                    return False

                models = data.get("models", [])
                if not isinstance(models, list):
                    return False

                # Build installed set
                installed = set()
                for m in models:
                    name = (m.get("name") or m.get("model"))
                    if isinstance(name, str):
                        installed.add(name.strip().lower())

                # Derive the tag from the registry key (no extra fields required)
                target = self._derive_ollama_tag(model, runtime)
                if not target:
                    return False  # runtime mismatch or empty tag

                # Match directly; (optional) also accept ':latest' normalization
                if target in installed:
                    return True
                if not target.endswith(":latest") and f"{target}:latest" in installed:
                    return True
                return False

            # ---- vLLM: (not implemented yet) ----
            if runtime in self._vllm_aliases:
                return False

            # Unknown local runtime → not available
            return False

        # Non-local: require env var only if we know one for that provider
        env_var = self._provider_env.get(provider)
        if not env_var:
            return True
        return env_var in os.environ

    def _build_model_info(self, model: str, cfg: LLMConfig) -> ModelInfo:
        """Build ModelInfo for a given model name, using config and defaults as needed."""
        entry     = self.model_info.get(model, {})
        provider  = entry.get("provider", "Unknown")
        available = self._is_provider_available(provider, model)
        in_cost, out_cost, ctx = self._get_model_pricing_and_context(model)

        # ---- pull skills / speed from defaults if present; fallback safely ----
        code_skill = self._score_override(cfg, model, "code")
        if code_skill is None:
            code_skill = float(entry.get("code_skill", _DEFAULT_MODEL_SKILL))
        general_skill = self._score_override(cfg, model, "general")
        if general_skill is None:
            general_skill = float(entry.get("general_skill", _DEFAULT_MODEL_SKILL))
        TTFT       = entry.get("TTFT")
        speed      = entry.get("speed")
        parameters = entry.get("parameters", _DEFAULT_MODEL_PARAMETERS)
        is_local   = bool(entry.get("local", False))
        runtime    = entry.get("runtime")

        meta: dict[str, Any] = {"pricing_source": "cache_or_litellm_or_fallback"}

        return ModelInfo(
            name=model,
            provider=provider,
            context_window=ctx,
            input_cost_per_token=in_cost,
            output_cost_per_token=out_cost,
            available=available,
            is_local=is_local,
            parameters=parameters,
            runtime=runtime,
            code_skill=float(code_skill),
            general_skill=float(general_skill),
            TTFT=TTFT,
            speed=speed,
            meta=meta,
        )

    def _ensure_litellm(self) -> None:
        """Ensure LiteLLM is imported and ready to use."""
        if self._litellm_ready:
            return
        try:
            import litellm  # type: ignore
            self._litellm_mod   = litellm
            self._litellm_ready = True
        except ImportError as e:
            my_critical_error(f"LiteLLM is enabled but not installed. 'pip install litellm' Error: {e}")

    def _http_get_json(self, url: str, timeout: float = 2.0) -> dict[str, Any] | None:
        """Helper to GET a URL and parse JSON, returning None on any failure."""
        from urllib import request, error
        req = request.Request(url, headers={"Accept": "application/json"})
        try:
            with request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
        except (error.URLError, error.HTTPError, TimeoutError):
            return None
        try:
            import json
            return json.loads(raw.decode(DEFAULT_ENCODING))
        except Exception:
            return None

    def _derive_ollama_tag(self, model: str, runtime: str | None) -> str:
        """
        Map your registry key to an Ollama tag without needing extra registry fields.
        Rules:
        - If the model key starts with 'ollama/', strip that prefix and use the rest.
        - Else, if runtime is ollama, assume the key itself is the tag.
        - Normalize to lowercase for matching against /api/tags results.
        """
        r = (runtime or "").strip().casefold()
        tag = model
        if model.startswith("ollama/"):
            tag = model[len("ollama/") :]
        return tag.strip().lower() if r == "ollama" else ""

    # Pricing/context helpers with caching

    def _get_model_pricing_and_context(self, model: str) -> tuple[float, float, int]:
        """
        Returns (input_cost_per_token, output_cost_per_token, context_window).
        Prices normalized to $/token (not per-1k). Unknown remote prices get a very high sentinel;
        local models always return 0 for both.
        """
        if model in self._pricing_cache:
            return self._pricing_cache[model]

        entry = self.model_info.get(model, {})

        # Local models: $0 and registry context
        if entry.get("local") is True:
            ctx = int(entry.get("context", _DEFAULT_MODEL_CONTEXT))
            in_cost = out_cost = 0.0
            self._pricing_cache[model] = (in_cost, out_cost, ctx)
            return self._pricing_cache[model]

        # ---- non-local path ----
        in_cost  = None
        out_cost = None
        context  = int(entry.get("context", _DEFAULT_MODEL_CONTEXT))

        try:
            import litellm  # type: ignore
            info_fn = getattr(litellm, "get_model_info", None)
            md = {}
            if callable(info_fn):
                try:
                    md = info_fn(model) or {}
                except Exception:
                    md = {}

            cpit    = self._deep_get(md, ["input_cost_per_token"])
            cppt    = self._deep_get(md, ["output_cost_per_token"])
            cpik    = self._deep_get(md, ["input_cost_per_1k_tokens"])
            cpok    = self._deep_get(md, ["output_cost_per_1k_tokens"])
            max_ctx = self._deep_get(md, ["max_input_tokens"]) or self._deep_get(md, ["max_tokens"])

            if max_ctx:
                try:
                    context = int(max_ctx)
                except Exception:
                    pass

            if cpit is not None and cppt is not None:
                in_cost, out_cost = float(cpit), float(cppt)
            elif cpik is not None and cpok is not None:
                in_cost, out_cost = float(cpik) / 1000.0, float(cpok) / 1000.0

            if in_cost is None or out_cost is None:
                cost_map = getattr(litellm, "model_cost", None) or getattr(litellm, "litellm_model_cost", None)
                if isinstance(cost_map, dict) and model in cost_map:
                    row = cost_map[model]
                    if in_cost is None:
                        if "input_cost_per_token" in row:
                            in_cost = float(row["input_cost_per_token"])
                        elif "input_cost_per_1k_tokens" in row:
                            in_cost = float(row["input_cost_per_1k_tokens"]) / 1000.0
                    if out_cost is None:
                        if "output_cost_per_token" in row:
                            out_cost = float(row["output_cost_per_token"])
                        elif "output_cost_per_1k_tokens" in row:
                            out_cost = float(row["output_cost_per_1k_tokens"]) / 1000.0

        except Exception as e:
            logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug(
                "LiteLLM pricing/context lookup failed for %s: %s", model, e
            )

        if in_cost is None:
            in_cost = 9e9
        if out_cost is None:
            out_cost = 9e9

        self._pricing_cache[model] = (float(in_cost), float(out_cost), int(context))
        return self._pricing_cache[model]

    @staticmethod
    def _deep_get(d: dict[str, Any], path: list[str]) -> Any:
        """Safely get a nested value from a dict."""
        cur: Any = d
        for key in path:
            if not isinstance(cur, dict) or key not in cur:
                return None
            cur = cur[key]
        return cur

    @staticmethod
    def _extract_text_from_openai_like(resp: Any) -> str:
        """Normalize content extraction across dict/object forms."""
        # pydantic-like / attribute
        try:
            return resp.choices[0].message.content  # type: ignore[attr-defined]
        except Exception:
            pass
        # dict-like
        try:
            return resp["choices"][0]["message"]["content"]  # type: ignore[index]
        except Exception:
            pass
        # object-like with dict message
        try:
            return resp.choices[0].message["content"]  # type: ignore[index]
        except Exception:
            pass
        # As last resort, stringify
        return str(resp)

    def _score_override(self, cfg: LLMConfig, model: str, which: str) -> float | None:
        """
        which: 'code' or 'general'
        Accepts cfg.model_scores[model] as float (code only) or dict with keys 'code'/'general'.
        """
        if not cfg.model_scores:
            return None
        val = cfg.model_scores.get(model)
        if val is None:
            return None
        if isinstance(val, (int, float)):
            return float(val) if which == "code" else None
        if isinstance(val, dict):
            v = val.get(which)
            return float(v) if v is not None else None
        return None

    def tokenize(self, text: str, model: str | None = None) -> int:
        """
        Return the number of tokens in 'text' under the tokenizer best-suited to 'model'.

        Preference order:
        1) Local Ollama runtime -> call /api/tokenize
        2) LiteLLM's token counters (if importable)
        3) tiktoken with OpenAI-family heuristics (o200k_base vs cl100k_base)
        4) Rough heuristic fallback

        Args:
            text: The input text to tokenize.
            model: The model to use for tokenization (optional).

        Returns:
            The number of tokens in the input text.

        Raises:
            ValueError: If tokenization fails.
        """
        if not text:
            return 0

        if model is None:
            model = self._selected.name if self._selected else ""

        entry    = self.model_info.get(model, {})
        runtime  = (entry.get("runtime") or "").strip().casefold()
        is_local = bool(entry.get("local", False))
        provider = (entry.get("provider") or "").strip()

        # --- 1) Local Ollama: ask the server's tokenizer directly ---
        if is_local and runtime == "ollama":
            cfg  = self._config or LLMConfig()
            base = (cfg.ollama_base_url or "").rstrip("/")
            tag  = self._derive_ollama_tag(model, "ollama")
            if base and tag:
                try:
                    import json
                    from urllib import request
                    payload = json.dumps({"model": tag, "prompt": text}).encode(DEFAULT_ENCODING)
                    req = request.Request(f"{base}/api/tokenize",
                                        data=payload,
                                        headers={"Content-Type": "application/json"})
                    with request.urlopen(req, timeout=2.0) as resp:
                        raw = resp.read()
                    data = json.loads(raw.decode(DEFAULT_ENCODING, "replace"))
                    toks = data.get("tokens")
                    if isinstance(toks, list):
                        return len(toks)
                except Exception:
                    # fall through to other methods
                    pass

        # --- 2) LiteLLM counters (if the library is available) ---
        try:
            import importlib
            litellm = importlib.import_module("litellm")  # type: ignore

            # Preferred: get_num_tokens(model=..., text=...)
            get_num_tokens = getattr(litellm, "get_num_tokens", None)
            if callable(get_num_tokens):
                try:
                    return int(get_num_tokens(model=model, text=text))
                except Exception:
                    pass

            # Fallbacks: token_counter APIs across versions
            token_counter = getattr(litellm, "token_counter", None)
            if token_counter:
                # Some versions accept raw text
                try:
                    out = token_counter(model=model, text=text)
                    if isinstance(out, int):
                        return int(out)
                except Exception:
                    pass
                # Others want chat messages, returning a dict
                try:
                    out = token_counter(model=model, messages=[{"role": "user", "content": text}])
                    if isinstance(out, dict):
                        for k in ("input_tokens", "total_tokens", "num_tokens"):
                            v = out.get(k)
                            if isinstance(v, (int, float)):
                                return int(v)
                except Exception:
                    pass
        except Exception:
            pass

        # --- 3) tiktoken heuristics (works well for OpenAI families) ---
        try:
            import tiktoken  # type: ignore

            enc_name = "cl100k_base"
            m = model.lower()

            # Use o200k_base for OpenAI's o*/4o/4.1/5 families (long-context tokenization)
            if provider == "OpenAI" or m.startswith(("gpt", "o")):
                if any(x in m for x in ("gpt-4.1", "gpt-4o", "gpt-5", "o1", "o3", "o4", "4.1", "4o")):
                    enc_name = "o200k_base"

            try:
                enc = tiktoken.get_encoding(enc_name)
            except Exception:
                enc = tiktoken.get_encoding("cl100k_base")

            return len(enc.encode(text))
        except Exception:
            pass

        # --- 4) Rough heuristic fallback (no libs / no server tokenizer) ---
        import math
        import re
        s = text if isinstance(text, str) else str(text)
        # Count word-like + punctuation chunks; ensure at least 1
        rough = len(re.findall(r"\w+|[^\s\w]", s, flags=re.UNICODE))
        if rough == 0:
            rough = math.ceil(len(s) / 4.0) or 1
        return int(rough)


class MemoryHandler(logging.Handler):
    """A logging handler that stores logs in memory so the errors can be printed at the end."""

    def __init__(self, level: int = logging.ERROR) -> None:
        """Initialize the MemoryHandler with the specified logging level."""
        super().__init__(level)
        self.logs = []

    def emit(self, record: logging.LogRecord) -> None:
        """Capture the log record and store it in memory."""
        if record.levelno >= self.level:  # Only capture logs with the appropriate level
            self.logs.append(self.format(record))


class FlushingStreamHandler(logging.StreamHandler):
    """A logging handler that flushes the stream after emitting each log so the logs are immediately visible."""

    def emit(self, record: logging.LogRecord) -> None:
        """Emit a log record and immediately flush the stream."""
        # Call the original emit method to handle the logging
        super().emit(record)
        # Immediately flush the stream after emitting the log
        self.flush()


class MaxLevelFilter(logging.Filter):
    """A logging filter that only allows logs up to a certain level to pass through, so that error messages aren't printed multiple times."""

    def __init__(self, max_level: int) -> None:
        """Initialize the MaxLevelFilter with the specified maximum logging level."""
        self.max_level = max_level

    def filter(self, record: logging.LogRecord) -> bool:
        """Filter out log records above the maximum level."""
        return record.levelno <= self.max_level


def fallback_logging_config(log_level: int | str = logging.INFO, rawlog: bool = False) -> None:
    """
    Configure the root logger with a basic configuration if no handlers are set.
    Run this at the start of functions which might be run without first configuring logging.

    Args:
        level  : The logging level to set. Defaults to logging.INFO.
        rawlog : If True, use a simple log format without timestamps or levels.
    """
    if not logging.getLogger().handlers:
        if not rawlog:  # Use a full logging format with timestamps and levels.
            logging.basicConfig(level=log_level,
                                format="%(asctime)s - %(levelname)s - %(message)s",
                                datefmt="%Y-%m-%d %H:%M:%S")
        else:  # rawlog is True, so use a simple format without timestamps or levels.
            logging.basicConfig(level=log_level, format="%(message)s")


def configure_logging(basename: str, log_level: int | str = logging.INFO,
                      rawlog: bool = False, logdir: str | os.PathLike[str] = "") -> MemoryHandler:
    """Configure logging to write to files and stdout/stderr, and return a MemoryHandler to capture ERROR logs for later (duplicate) printing."""
    import datetime as dt

    root_logger = logging.getLogger()

    # Check if logging is already configured by checking for any handlers
    if root_logger.hasHandlers():
        for handler in root_logger.handlers:
            if isinstance(handler, MemoryHandler):
                return handler

    # Proceed with configuring logging if no MemoryHandler was found
    if not logdir:  # Default to the current working directory if no logdir is provided.
        logdir = Path.cwd().expanduser().resolve(strict=True) / "logs"
    else:
        logdir = ensure_path(logdir)
    logdir.mkdir(parents=True, exist_ok=True)

    now = dt.datetime.now()
    log_base   = f".{basename}-log-{now.strftime('%Y%m%d-%H%M%S')}"
    log_info   = logdir / (log_base + ".out")
    log_errors = logdir / (log_base + ".err")

    root_logger.handlers = []  # Reset any existing handlers

    # File handlers for logging to files
    try:
        debug_info_handler    = logging.FileHandler(log_info)
        debug_info_handler.setLevel(logging.DEBUG)
        warning_error_handler = logging.FileHandler(log_errors)
        warning_error_handler.setLevel(logging.WARNING)
    except OSError as e:
        print(f"Failed to create log files: {e}", flush=True)
        return None

    # Stream handler for stdout (WARNING and lower)
    console_handler_stdout = FlushingStreamHandler(stream=sys.stdout)
    console_handler_stdout.setLevel(logging.DEBUG)  # Set to lowest level
    console_handler_stdout.addFilter(MaxLevelFilter(logging.WARNING))  # Highest

    # Stream handler for stderr (ERROR and above)
    console_handler_stderr = FlushingStreamHandler(stream=sys.stderr)
    console_handler_stderr.setLevel(logging.ERROR)  # Only logs ERROR and higher to stderr

    memory_handler = MemoryHandler(level=logging.ERROR)  # Only capture ERROR level logs

    # Define the formatter based on the no_prefix parameter
    if rawlog:
        log_format = logging.Formatter("%(message)s")
    else:
        log_format = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

    debug_info_handler.setFormatter(    log_format)
    warning_error_handler.setFormatter( log_format)
    console_handler_stdout.setFormatter(log_format)
    console_handler_stderr.setFormatter(log_format)
    memory_handler.setFormatter(        log_format)

    root_logger.setLevel(log_level)
    root_logger.addHandler(debug_info_handler)
    root_logger.addHandler(warning_error_handler)
    root_logger.addHandler(console_handler_stdout)
    root_logger.addHandler(console_handler_stderr)
    root_logger.addHandler(memory_handler)
    if not rawlog: root_logger.info("Logging to '%s' and '%s' with level %s", log_info, log_errors, logging.getLevelName(root_logger.level))

    return memory_handler


def print_all_errors(memory_handler: MemoryHandler,
                     rawlog: bool = False) -> None:
    """Print all the captured error messages."""
    if memory_handler.logs and not rawlog:
        print("\n******************************\n"
              "******************************\n"
              "All Error messages from above:")
        for log in memory_handler.logs:
            print(log)


def my_critical_error(message: str = "A critical error occurred.",
                      choose_breakpoint: bool = False,
                      exit_code: int = 1) -> None:
    """Log a critical error message and either exit the program or enter a breakpoint."""
    fallback_logging_config()
    # Determine if an exception is being handled:
    exc_type, exc_value, exc_traceback = sys.exc_info()
    if exc_type:
        # An exception is being handled; include exception info
        logging.critical(message, exc_info=True)
    else:
        # No exception is being handled; log only the message
        logging.critical(message)
    if choose_breakpoint:
        print("Entering breakpoint while inside the my_critical_error() function. You can step outside of this function and remain paused by pressing 'n' to access variables in the calling function or press 'c' to continue running the script. If logging is enabled but the level is not set to DEBUG, you can type logging.getLogger().setLevel(logging.DEBUG) to see more detailed logs.")
        breakpoint()
    else:
        sys.exit(exit_code)


class MyPopenResult:
    """A class to store the results of a customized subprocess.Popen call."""

    def __init__(self, stdout: str, stderr: str, returncode: int) -> None:
        """Initialize the MyPopenResult with stdout, stderr, and returncode."""
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode
        self.success = (returncode == 0)


def my_popen(command_list: list, suppress_info: bool = False,
             suppress_error: bool = False) -> MyPopenResult:
    """Execute a command using subprocess.Popen and capture the output line by line using threads."""
    import threading
    import subprocess
    import shlex
    fallback_logging_config(log_level=logging.INFO if not suppress_info else logging.ERROR)
    command_list_str = [str(item) for item in command_list]
    the_statement = "Executing command: " + " ".join(shlex.quote(str(arg)) for arg in command_list_str)
    if not suppress_info:
        logging.info(the_statement)
    else:
        logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug(the_statement)

    try:
        process = subprocess.Popen(
            command_list_str,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1  # Line-buffered
        )

        stdout_lines = []
        stderr_lines = []

        def read_stdout() -> None:
            """Read stdout line by line and log it."""
            for line in process.stdout:
                stdout_lines.append(line)
                log_line = line.strip()
                if not suppress_info:
                    logging.info(log_line)
                else:
                    logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug(log_line)

        def read_stderr() -> None:
            """Read stderr line by line and log it."""
            for line in process.stderr:
                stderr_lines.append(line)
                log_line = line.strip()
                if not suppress_error:
                    logging.error(log_line)
                elif not suppress_info:
                    logging.info(log_line)
                else:
                    logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug(log_line)

        # Start threads
        stdout_thread = threading.Thread(target=read_stdout)
        stderr_thread = threading.Thread(target=read_stderr)
        stdout_thread.start()
        stderr_thread.start()

        # Wait for the process and threads to finish
        process.wait()
        stdout_thread.join()
        stderr_thread.join()

        stdout = "".join(stdout_lines)
        stderr = "".join(stderr_lines)

        return MyPopenResult(stdout=stdout, stderr=stderr, returncode=process.returncode)

    except Exception as e:  # I don't want any exception here to crash the script, so I catch it and return a MyPopenResult with an error message.
        if not suppress_error:
            logging.error("An error occurred while executing the command '%s'", command_list_str, exc_info=True)
        else:
            logging.info("An error occurred while executing the command '%s'", command_list_str, exc_info=True)
        return MyPopenResult(stdout="", stderr=str(e), returncode=-1)


def my_fopen(file_path: str | os.PathLike[str], suppress_errors: bool = False,
             rawlog: bool = False, numlines: int | None = None) -> str | bool:
    """
    Attempt to read a text file with various encodings and return the file content if successful. Optionally, specify numlines to limit the number of lines read.

    Args:
        file_path:       Path to the file to read.
        suppress_errors: If True, suppress error messages and return False instead of logging errors.
        rawlog:          If True, use a simple log format without timestamps or levels.
        numlines:        If specified, read only this many lines from the file and return them as a string.

    Returns:
        The content of the file as a string.
        Returns False:
         - if the file does not exist
         - is empty
         - is a non-text file (video, audio, image, archive)
         - cannot be read with any of the specified encodings
    """
    fallback_logging_config(log_level=logging.INFO if not suppress_errors else logging.CRITICAL,
                            rawlog=rawlog)
    file_path = ensure_path(file_path)
    if not safe_exists(file_path):
        this_message = f"File does not exist: {os.fspath(file_path)}"
        if not rawlog:
            if not suppress_errors: logging.error(this_message)
            else:                   logging.info( this_message)
        return False
    if not safe_is_file(file_path):
        this_message = f"Path is a directory, not a file: {os.fspath(file_path)}"
        if not rawlog:
            if not suppress_errors: logging.error(this_message)
            else:                   logging.info( this_message)
        return False
    if (file_path_size := safe_size(file_path)) is None:
        this_message = f"Could not determine file size: {os.fspath(file_path)}"
        if not rawlog:
            if not suppress_errors: logging.error(this_message)
            else:                   logging.info( this_message)
        return False
    if file_path_size == 0:
        this_message = f"File is empty: {os.fspath(file_path)}"
        if not rawlog:
            if not suppress_errors: logging.error(this_message)
            else:                   logging.info( this_message)
        return False
    # Does the file extension match any of these (non-text) extensions?
    casefolded_suffix = file_path.suffix.casefold()
    if casefolded_suffix in VIDEO_EXTENSIONS_SET:
        if not rawlog:
            this_message = f"Skipping video file {os.fspath(file_path)}"
            if not suppress_errors: logging.error(this_message)
            else:                   logging.info( this_message)
        return False
    if casefolded_suffix in AUDIO_EXTENSIONS_SET:
        if not rawlog:
            this_message = f"Skipping audio file {os.fspath(file_path)}"
            if not suppress_errors: logging.error(this_message)
            else:                   logging.info( this_message)
        return False
    if casefolded_suffix in IMAGE_EXTENSIONS_SET:
        if not rawlog:
            this_message = f"Skipping image file {os.fspath(file_path)}"
            if not suppress_errors: logging.error(this_message)
            else:                   logging.info( this_message)
        return False
    if casefolded_suffix in ARCHIVE_EXTENSIONS_SET:
        if not rawlog:
            this_message = f"Skipping archive file {os.fspath(file_path)}"
            if not suppress_errors: logging.error(this_message)
            else:                   logging.info( this_message)
        return False
    for encoding in TEXT_ENCODINGS:  # use the (ordered) tuple so more common encodings are tried first.
        try:
            with open(file_path, "r", encoding=encoding) as file:
                if numlines is None:
                    file_content = file.read()
                else:
                    file_content = "".join(file.readline() for _ in range(numlines))
            logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("Successfully read %s with encoding %s", os.fspath(file_path), encoding)
            return file_content  # Exit the function if reading is successful
        except UnicodeDecodeError:
            if not rawlog:
                this_message = f"Unicode decode error with encoding {encoding} reading file {os.fspath(file_path)}"
                if not suppress_errors: logging.warning(this_message, exc_info=True)
                else:                   logging.info(   this_message, exc_info=True)
            continue
        except LookupError:
            if not rawlog:
                this_message = f"Unknown codec {encoding} for file {os.fspath(file_path)}"
                if not suppress_errors: logging.warning(this_message, exc_info=True)
                else:                   logging.info(   this_message, exc_info=True)
            continue
        except Exception:  # Catch any other exceptions that might occur, but don't crash.
            if not rawlog:
                this_message = f"Error reading file {os.fspath(file_path)} with encoding {encoding}."
                if not suppress_errors: logging.error(this_message, exc_info=True)
                else:                   logging.info( this_message, exc_info=True)
            return False
    return False


def load_ast_var(var_name: str, script_path: str | os.PathLike[str],
                 rawlog: bool = False) -> Any | None:
    """
    Load a top-level literal Python variable from a module without executing it.

    Args:
        var_name:    The name of the global variable to extract from the script.
        script_path: The path to the Python script file from which to extract the variable.
        rawlog:      If True, use a simple log format without timestamps or levels.

    Returns:
        The value of the variable if found, or None.

    Raises:
        FileNotFoundError: If the script file does not exist.
        AttributeError:    If the variable is not found at the top level of the script.
        ValueError:        If the value of the variable cannot be evaluated as a literal expression.
    """
    import ast
    fallback_logging_config(rawlog=rawlog)
    script_path  = ensure_file(script_path)
    file_content = my_fopen(script_path, rawlog=rawlog)
    if not file_content:
        my_critical_error(f"Failed to open {os.fspath(script_path)}", choose_breakpoint=True)
    tree = ast.parse(file_content, script_path)
    if tree is None:
        raise SyntaxError(f"Could not parse {os.fspath(script_path)}")

    for node in tree.body:
        # handle plain assignments: var_name = <expr>
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == var_name:
                    try:
                        return ast.literal_eval(node.value)
                    except ValueError as e:
                        raise ValueError(f"Cannot literal_eval the value of {var_name}: {e}") from e
        # also handle annotated assignments: var_name: Type = <expr>
        elif isinstance(node, ast.AnnAssign):
            target = node.target
            if isinstance(target, ast.Name) and target.id == var_name and node.value:
                try:
                    return ast.literal_eval(node.value)
                except ValueError as e:
                    raise ValueError(f"Cannot literal_eval the value of {var_name}: {e}") from e

    logging.info("Top-level variable %r not found in %s", var_name, os.fspath(script_path))
    return None


def _sanitize_text_signature(sig: str | None) -> str:
    """
    Clean up a __text_signature__ string for display.

    Args:
        sig: The __text_signature__ string to clean up.

    Returns:
        A cleaned-up version of the signature string.

    Raises:
        None.
    """
    if not sig:
        return "(...)"
    s = sig
    # Replace CPython-internal placeholders
    s = s.replace("$self", "self").replace("$module", "")
    # Tidy up commas/spaces that might be left after removing $module
    s = re.sub(r"\(\s*,", "(", s)
    s = re.sub(r",\s*,", ", ", s)
    s = s.replace("(,", "(").replace(", )", ")")
    return s


def _builtin_stub(obj: object) -> str:
    """
    Return a stub definition for a built-in or C-extension function.

    Args:
        obj: The built-in function or method object.

    Returns:
        A string representing a stub definition of the function.

    Raises:
        None.
    """
    import inspect
    from textwrap import indent
    def_name = getattr(obj, "__name__", getattr(obj, "__qualname__", "<builtin>"))
    context = None
    if hasattr(obj, "__objclass__"):
        context = f"{obj.__objclass__.__name__}.{def_name}"   # e.g., "list.append"
    else:
        mod = getattr(obj, "__module__", None)
        if mod and mod != "builtins":
            context = f"{mod}.{def_name}"                     # e.g., "math.prod"
    header = f"# {context}\n" if context else ""

    try:
        sig = str(inspect.signature(obj))
    except Exception:
        sig = _sanitize_text_signature(getattr(obj, "__text_signature__", None))

    doc = inspect.getdoc(obj) or "Built-in function; Python source unavailable."
    doc = doc.replace('"""', '\\"""')  # keep our triple quotes intact
    doc = indent(doc, "    ")
    return f"{header}def {def_name}{sig}:\n    \"\"\"\n{doc}\n    \"\"\"\n    ...\n"


def show_function_source(target: object | str, *, unwrap: bool = True,
                         output: str | os.PathLike[str] | TextIO | None = None) -> str:
    """
    Print the full source text of a Python function (including comments,
    docstrings, decorators, and type hints).

    Args:
        target: A function *name* (string) or a function object.
                If a string is given, it's resolved in the caller's scope, then
                in builtins, then as a dotted path via pydoc.locate (e.g. 'pkg.mod.func').
        unwrap: If True, attempt to unwrap decorated functions to show
                the original implementation. Defaults to True.
        output: A file-like object to write to (optional, defaults to sys.stdout). More details:

    Details on the "output" argument:
    - None -> sys.stdout
    - TextIO (e.g., sys.stdout, an open text file, StringIO) -> used as-is
             (must be opened in *text* mode; binary streams are rejected)
    - str | os.PathLike[str] -> treated as a path:
             * '~' is expanded
             * parent directories are created (parents=True, exist_ok=True)
             * file is opened in append mode ('a', UTF-8)
             * a one-line note is written indicating whether we created or appended
    Notes:
    - A trailing newline is added if the source text doesn't already end with one.
    - If you pass the string "-" as the output path, it is treated as stdout.
    - If the given path is an existing directory, an IsADirectoryError is raised.
    - If you pass a binary stream, a TypeError is raised.

    Returns:
        str: The source text that was printed.

    Raises:
        NameError: If a string cannot be resolved to an object.
        OSError:   If source is unavailable (e.g., built-in/C extension or optimized away).
        TypeError: If the resolved object isn't suitable for source extraction.
    """
    import builtins
    import functools
    import inspect
    import pydoc
    import io
    # Resolve the object if 'target' is a string
    if isinstance(target, str):
        name = target
        frame = inspect.currentframe().f_back  # caller's frame
        try:
            obj = frame.f_locals.get(name)
            if obj is None:
                obj = frame.f_globals.get(name)
            if obj is None:
                obj = getattr(builtins, name, None)
            if obj is None and "." in name:
                head, *tail = name.split(".")
                base = frame.f_locals.get(head)
                if base is None:
                    base = frame.f_globals.get(head)
                if base is None:
                    base = getattr(builtins, head, None)
                if base is not None:
                    try:
                        for part in tail:
                            base = getattr(base, part)
                        obj = base
                    except Exception:
                        pass
            if obj is None:
                # Try dotted-path resolution (e.g., "pkg.module.func")
                obj = pydoc.locate(name)
        finally:
            # Avoid reference cycles
            del frame

        if obj is None:
            raise NameError(f"Could not resolve '{name}' to a function object.")
    else:
        obj = target

    # Optionally unwrap decorated functions
    if unwrap:
        try:
            obj = inspect.unwrap(obj)
        except Exception:
            pass  # not fatal if we can't unwrap

    if isinstance(obj, functools.partial):
        obj = obj.func

    if not (inspect.isroutine(obj) or inspect.ismethoddescriptor(obj)):
        if callable(obj):        # use callable(), not getattr/hasattr
            call = obj.__call__  # bound method; safe after callable()
            if inspect.isfunction(call) or inspect.ismethod(call):
                obj = call

    # Built-ins / C-extensions don't have retrievable Python source
    if inspect.isbuiltin(obj) or inspect.ismethoddescriptor(obj):
        src = _builtin_stub(obj)
    else:
        src = inspect.getsource(obj)

    # Decide where to write
    out: TextIO
    closer: Callable[[], None] | None = None  # callable to close if *we* open a file
    note: str | None = None
    if output is None:
        out = sys.stdout
    # Accept known text-mode IO bases directly
    elif isinstance(output, (io.TextIOBase, io.StringIO)):
        out = output
    # Accept "-" as a common alias for stdout
    elif isinstance(output, (str, os.PathLike)) and str(output) == "-":
        out = sys.stdout
    # Path-like or string path
    elif isinstance(output, (str, os.PathLike)):
        path = ensure_path(output).resolve()
        if safe_is_dir(path):
            raise IsADirectoryError(f"Output path is a directory: {os.fspath(path)}")
        # Ensure parents exist ('.' is fine to call mkdir() on with exist_ok=True)
        path.parent.mkdir(parents=True, exist_ok=True)
        exists = safe_exists(path)
        note = (f"# Appending to existing file: {os.fspath(path)}"
                if exists
                else f"# Creating new file: {os.fspath(path)}")
        # Try atomic write helper if available; fall back on any failure.
        _maw = globals().get("my_atomic_write")
        if callable(_maw):
            try:
                # newline hygiene: one newline after note; ensure src ends with exactly one
                payload = (note + "\n") + (src if src.endswith("\n") else src + "\n")
                _maw(path, payload, "a", encoding=DEFAULT_ENCODING)
                return src
            except Exception:
                # Non-atomic fallback below
                pass
        # newline="" lets print() manage newlines consistently across platforms
        out = path.open("a", encoding=DEFAULT_ENCODING, newline="")
        closer = out.close
    # Last chance: duck-typed "file-like" with a text write() method.
    # Reject binary streams explicitly.
    elif hasattr(output, "write"):
        if isinstance(output, (io.BufferedIOBase, io.RawIOBase)):
            raise TypeError("Binary streams are not supported; provide a text-mode stream.")
        out = output  # type: ignore[assignment]
    else:
        raise TypeError("output must be None, a path (str/os.PathLike), or a text-mode TextIO.")
    try:
        if note:
            print(note, file=out)
        print(src, file=out, end="" if src.endswith("\n") else "\n")
    finally:
        if closer is not None:
            closer()
    return src


def normalize_to_dict(value: Any, var_name: str, script_path: str | os.PathLike[str]) -> dict:
    """Ensure that 'value' is a dict. If it's a JSON-style string, try to parse it. Otherwise, log a warning and return an empty dict."""
    import json
    fallback_logging_config()
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    script_path_str = os.fspath(script_path)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                return parsed
            logging.warning("Variable %r in %r JSON-decoded to %s, expected dict.", var_name, script_path_str, type(parsed).__name__)
        except json.JSONDecodeError as e:
            logging.warning("Failed to JSON-decode variable %r from %s. Expected a dict or JSON string.", var_name, script_path_str, exc_info=e)
    else:
        logging.warning("Variable %r in %s is of type %s, expected dict or JSON string.", var_name, script_path_str, type(value).__name__)
    return {}


def return_method_name(levels_up: int = 1) -> str:
    """
    Return the caller's qualified method/function name.

    - For instance methods: ClassName.method
    - For classmethods:     ClassName.method
    - For staticmethods:    ClassName.method on Python >= 3.11 (via co_qualname),
                            otherwise just 'method' (class is not recoverable without heuristics)
    - For functions:        function

    Args:
        levels_up: How many frames up to inspect (1 = caller). If greater than
                   the stack depth, the highest available frame is used.

    Returns:
        The current method name as a string, formatted as 'ClassName.method' or 'function'.

    Raises:
        None: This function does not raise exceptions, but it may log warnings
              if sys._getframe or inspect fails.
    """
    fallback_logging_config()
    try:
        levels = int(levels_up)
    except Exception:
        levels = 1
    if levels < 1:
        levels = 1
    name = "<unknown>"
    fr   = None
    # Try sys._getframe first
    try:
        fr = sys._getframe(levels)  # Get the frame at the specified level
    except Exception as e1:
        logging.warning("return_method_name(): sys._getframe(%s) failed. Falling back to inspect...", levels, exc_info=e1)
        try:
            import inspect
            frame = inspect.currentframe()
            try:
                fr = frame
                climbed = 0
                for _ in range(levels):
                    if fr is None or fr.f_back is None:
                        break
                    fr = fr.f_back
                    climbed += 1
                if climbed < levels:
                    logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("return_method_name(): truncated at top of stack (requested levels_up=%s but only climbed=%s)", levels, climbed)
            finally:
                if frame is not None:
                    try:
                        frame.clear()
                    except Exception:
                        pass
                    del frame
        except Exception as e2:
            logging.warning("return_method_name(): inspect fallback failed", exc_info=e2)
            fr = None
    if fr is not None:
        # Python 3.11+: co_qualname gives 'Class.method' (or 'outer.<locals>.inner')
        qual = getattr(fr.f_code, "co_qualname", None)
        if isinstance(qual, str) and qual:
            # Remove all occurrences of '.<locals>.' from the qualified name.
            name = qual.replace(".<locals>.", ".")
        else:
            func     = fr.f_code.co_name
            self_obj = fr.f_locals.get("self")
            cls_obj  = fr.f_locals.get("cls")
            if self_obj is not None:
                name = f"{type(self_obj).__qualname__}.{func}"
            elif isinstance(cls_obj, type):
                name = f"{cls_obj.__qualname__}.{func}"
            else:
                argc = getattr(fr.f_code, "co_posonlyargcount", 0) + fr.f_code.co_argcount
                if argc:
                    for a in fr.f_code.co_varnames[:argc]:
                        obj = fr.f_locals.get(a)
                        if obj is not None:
                            t = obj if isinstance(obj, type) else type(obj)
                            attr = getattr(t, func, None)
                            if attr is not None:
                                name = f"{getattr(t, '__qualname__', t.__name__)}.{func}"
                                break
                    else:
                        name = func
                else:
                    name = func
    else:
        logging.warning("return_method_name(): no frame available.")
    if fr is not None:
        if name == "<module>":
            mod = fr.f_globals.get("__name__")
            if isinstance(mod, str) and mod:
                name = mod
    fr = None  # Clear the frame reference to free memory.
    return name


def get_hostname_socket(rawlog: bool = False) -> str | None:
    """Retrieves the hostname using socket.gethostname()."""
    try:
        import socket
        return socket.gethostname()
    except Exception as e:
        if not rawlog: logging.warning("Failed to retrieve hostname using %s: %s", return_method_name(), e)
        return None


def get_hostname_platform(rawlog: bool = False) -> str | None:
    """Retrieves the hostname using platform.node()."""
    try:
        import platform
        return platform.node()
    except Exception as e:
        if not rawlog: logging.warning("Failed to retrieve hostname using %s: %s", return_method_name(), e)
        return None


def get_hostname_os_uname(rawlog: bool = False) -> str | None:
    """Retrieves the hostname using os.uname().nodename."""
    try:
        return os.uname().nodename
    except Exception as e:
        if not rawlog: logging.warning("Failed to retrieve hostname using %s: %s", return_method_name(), e)
        return None


def get_hostname_subprocess_hostname(rawlog: bool = False) -> str | None:
    """Retrieves the hostname using the 'hostname' system command via subprocess."""
    try:
        import subprocess
        result = subprocess.run(["hostname"], capture_output=True, text=True)
        return result.stdout.strip()
    except Exception as e:
        if not rawlog: logging.warning("Failed to retrieve hostname using %s: %s", return_method_name(), e)
        return None


def get_hostname_subprocess_scutil(rawlog: bool = False) -> str | None:
    """Retrieves the hostname using the 'scutil --get ComputerName' command on macOS via subprocess."""
    if sys.platform == "darwin":
        try:
            import subprocess
            result = subprocess.run(["scutil", "--get", "ComputerName"],
                                    capture_output=True, text=True)
            return result.stdout.strip()
        except Exception as e:
            if not rawlog: logging.warning("Failed to retrieve hostname using %s: %s", return_method_name(), e)
    return None


def get_computer_name(rawlog: bool = False) -> str:
    """
    Attempts multiple methods to retrieve the computer's name and returns the most common one.

    Args:
        rawlog: If True, print statements are disabled.

    Returns:
        A string representing the most common computer name obtained from the methods.
        If no names were retrieved, returns "ERROR-NO-NAME".

    Raises:
        None: This function does not raise exceptions, but it may log warnings if no names are retrieved.
    """
    fallback_logging_config(rawlog=rawlog)
    methods = {
        "socket_gethostname"  : get_hostname_socket,
        "platform_node"       : get_hostname_platform,
        "os_uname_nodename"   : get_hostname_os_uname,
        "subprocess_hostname" : get_hostname_subprocess_hostname,
    }

    if sys.platform == "darwin":  # This next method is macOS-specific
        methods["subprocess_scutil_computername"] = get_hostname_subprocess_scutil

    results = {}

    for method_name, method_func in methods.items():
        try:
            name = method_func(rawlog=rawlog)
            if name:
                results[method_name] = name
        except Exception:  # Ignore all exceptions for individual methods
            if not rawlog: logging.exception("Method %s failed.", method_name)
            pass  # Skip methods that fail

    computer_name = analyze_computer_name_results(results, rawlog=rawlog)

    return computer_name


def analyze_computer_name_results(results: dict[str, str], rawlog: bool = False) -> str:
    """
    Analyzes the retrieved computer names.

    Args:
        results: Dictionary with method names as keys and computer names as values.
        rawlog:  If True, print statements are disabled.

    Returns:
        A string representing the most common computer name obtained from the methods.
        If no names were retrieved, returns "ERROR-NO-NAME".

    Raises:
        None: This function does not raise exceptions, but it may log errors or warnings if
              no names (or differing names) are retrieved.
    """
    from collections import Counter
    fallback_logging_config(rawlog=rawlog)

    if not results:
        if not rawlog: logging.error("No methods succeeded in retrieving the computer name.")
        return "ERROR-NO-NAME"

    name_values = list(results.values())
    name_counts = Counter(name_values)
    most_common = name_counts.most_common()

    if len(name_counts) == 1:
        # All names are identical
        if not rawlog: logging.info("Computer name: %s", most_common[0][0])
        return most_common[0][0]
    else:
        # Names are not identical
        primary_name, primary_count = most_common[0]
        differing = {name: count for name, count in most_common if name != primary_name}

        if not rawlog:
            the_string =   "Multiple computer names detected:\n"
            the_string += f" - Most common name: {primary_name} (appeared {primary_count} times)\n"
            the_string += f" - Other names: {', '.join(f'{name} ({count} times)' for name, count in differing.items())}\n"
            detailed_results_str = "\n".join(f"     - {method}: {name}" for method, name in results.items())
            the_string += f" - Detailed method outputs:\n{detailed_results_str}"
            logging.warning(the_string)

        return primary_name


#########################################
# Internals for is_internet_available():
#########################################

# Numeric IPs (no DNS required) on common ports to check raw connectivity.
# Keep these very stable, globally reachable, and from different operators.
IPV4_TARGETS: list[tuple[str, int]] = [
    ("1.1.1.1",        443),  # Cloudflare
    ("8.8.8.8",        853),  # Google Public DNS over TLS (TCP)
    ("9.9.9.9",        443),  # Quad9
    ("208.67.222.222", 443),  # Cisco OpenDNS
]

IPV6_TARGETS: list[tuple[str, int]] = [
    ("2606:4700:4700::1111", 443),  # Cloudflare
    ("2001:4860:4860::8888",  53),  # Google Public DNS (TCP)
]

# HTTP(S) probes:
# - gstatic 204 endpoints are explicitly designed for connectivity checks.
# - msftconnecttest verifies plain HTTP reachability and expected content.
HTTP_PROBES: list[dict[str, Any]] = [
    {
        "url"    : "https://www.gstatic.com/generate_204",
        "method" : "GET",
        "expect" : {"status": 204},
        "note"   : "Android/gstatic 204 probe",
    },
    {
        "url"    : "http://www.gstatic.com/generate_204",
        "method" : "GET",
        "expect" : {"status": 204, "length_max": 0},
        "note"   : "HTTP 204 (checks for captive portal redirects)",
    },
    {
        "url"     : "http://www.msftconnecttest.com/connecttest.txt",
        "method"  : "GET",
        "expect"  : {"status": 200, "substr": "Microsoft Connect Test"},
        "note"    : "Microsoft connect test",
    },
]

# DNS names to resolve (if DNS is healthy, at least one should work).
DNS_TEST_NAMES: list[str] = [
    "example.com",      # IANA
    "cloudflare.com",   # Cloudflare
    "google.com",       # Google
    "one.one.one.one",  # Cloudflare DNS name (usually uncached locally)
    "dns.google",       # Google DNS name
]


def _tcp_connect(host: str, port: int, timeout: float) -> bool:
    """
    Attempt a TCP connection to a numeric IP address.

    Args:
        host:    Numeric IP address (IPv4/IPv6) as a string.
        port:    Destination TCP port number.
        timeout: Per-attempt timeout (seconds).

    Returns:
        True if TCP connection is successfully established, otherwise False.

    Raises:
        None (errors are caught and logged at DEBUG level).
    """
    try:
        import socket
        logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("TCP: connecting to %s:%d (timeout=%f)", host, port, timeout)
        with socket.create_connection((host, port), timeout=timeout):
            logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("TCP: success %s:%d", host, port)
            return True
    except OSError as exc:
        logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("TCP: failure %s:%d (%s)", host, port, exc)
        return False


def _dns_resolve(name: str, timeout: float) -> bool:
    """
    Try resolving a hostname using the system resolver.

    Args:
        name:    Hostname to resolve.
        timeout: Per-attempt timeout (seconds).

    Returns:
        True if resolution returns at least one address, else False.

    Raises:
        None.
    """
    # socket has no per-call DNS timeout, so use global default temporarily.
    import socket
    default_timeout = socket.getdefaulttimeout()
    socket.setdefaulttimeout(timeout)
    try:
        logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("DNS: resolving %s (timeout=%f)", name, timeout)
        res = socket.getaddrinfo(name, None, type=socket.SOCK_STREAM)
        ok  = len(res) > 0
        logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("DNS: %s for %s", "success" if ok else "empty result", name)
        return ok
    except OSError as exc:
        logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("DNS: failure for %s (%s)", name, exc)
        return False
    finally:
        socket.setdefaulttimeout(default_timeout)


def _build_http_opener(ignore_proxies: bool) -> urllib.request.OpenerDirector:
    """
    Build a URL opener honoring or ignoring proxies, with a bound TLS context.

    Args:
        ignore_proxies: Whether to bypass environment proxy settings.

    Returns:
        Configured opener with HTTPSHandler(context=...).
    """
    import ssl
    import urllib.request
    context:  ssl.SSLContext = ssl.create_default_context()
    handlers: list[Any]      = [
        urllib.request.ProxyHandler({} if ignore_proxies else None),  # {} = bypass; None = from env
        urllib.request.HTTPSHandler(context=context),
    ]
    return urllib.request.build_opener(*handlers)


def _http_probe(url: str, method: str, timeout: float,
                opener: urllib.request.OpenerDirector) -> tuple[bool, int | None, bytes | None, str | None]:
    """
    Perform an HTTP(S) probe (HEAD/GET) to a known endpoint.

    Args:
        url:     Target URL.
        method:  HTTP method ('HEAD' or 'GET').
        timeout: Timeout in seconds.
        opener:  Pre-configured opener (proxy/no-proxy).

    Returns:
        (success, status_code, body_bytes_or_None, final_url_if_redirected)

    Raises:
        None.
    """
    import urllib.request
    import urllib.error
    req = urllib.request.Request(url=url, method=method)
    # Add a small UA header to reduce the chance of odd blocks:
    req.add_header("User-Agent", f"{Path(sys.argv[0]).stem}/{__version__} (+python-urllib)")

    try:
        logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("HTTP: %s %s (timeout=%f)", method, url, timeout)
        with opener.open(req, timeout=timeout) as resp:
            status = getattr(resp, "status", None) or resp.getcode()
            data   = b""
            final_url = resp.geturl()
            # For HEAD we don't generally read a body; for GET, read up to a ceiling.
            if method.upper() == "GET":
                # Cap read size to avoid hanging on big captive pages.
                data = resp.read(2048)
            logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("HTTP: %s %s -> %d, final_url=%s", method, url, status, final_url)
            return True, int(status), data, final_url
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read(2048) if hasattr(exc, "read") else None
        except Exception:
            body = None
        final_url = exc.geturl() if hasattr(exc, "geturl") else None  # ← keep this
        logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("HTTP: HTTPError %s %s -> %d", method, url, exc.code)
        return False, int(exc.code), body, final_url
    except Exception as exc:
        logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("HTTP: failure %s %s (%s)", method, url, exc)
        return False, None, None, None


def _http_meets_expectations(status: int | None, body: bytes | None, expect: dict[str, Any]) -> bool:
    """
    Validate HTTP response against expectations.

    Args:
        status: HTTP status code (or None on failure).
        body:   Response body (None for HEAD or on failure).
        expect: Dict of constraints, e.g.:
                {
                    "status"     : 204,
                    "length_max" : 0,
                    "substr"     : "Microsoft Connect Test",
                }

    Returns:
        True if all applicable expectations are met, else False.

    Raises:
        None.
    """
    if status is None:
        return False

    if "status" in expect and status != int(expect["status"]):
        return False

    if "length_max" in expect and body is not None:
        if len(body) > int(expect["length_max"]):
            return False

    if "substr" in expect and body is not None:
        try:
            text = body.decode(DEFAULT_ENCODING, errors="ignore")
        except Exception:
            text = ""
        if str(expect["substr"]) not in text:
            return False

    return True


def _looks_like_captive(status: int | None, final_url: str | None, body: bytes | None) -> bool:
    """
    Heuristic to detect captive portals:
      - Unexpected 200/30x with HTML body where 204 is expected.
      - Status 511 (Network Authentication Required).
      - Redirects to login/portal-like URLs.

    Args:
        status:    HTTP status (or None).
        final_url: Final URL after redirects (or None).
        body:      Response body (or None).

    Returns:
        True if it appears to be a captive portal, else False.

    Raises:
        None.
    """
    if status is None:
        return False
    if status == 511:   # Network Authentication Required
        return True
    if status in (301, 302, 303, 307, 308):
        return True
    b = (body or b"")[:256].lower()
    if status == 204 and b:
        return True
    if status == 200 and b:
        if b"<html" in b or b"login" in b or b"captive" in b or b"portal" in b:
            return True
    if final_url:
        fu = final_url.lower()
        if any(k in fu for k in ("login", "captive", "portal", "hotspot", "walledgarden")):
            return True
    return False


def _should_use_proc_cap() -> bool:
    """
    Return True only on POSIX systems where RLIMIT_NPROC is available.
    Avoids calling into Unix-only modules on Windows.
    """
    try:
        import os
        import resource  # type: ignore
        return os.name == "posix" and hasattr(resource, "RLIMIT_NPROC")
    except Exception:
        return False


def _advisory_user_proc_limit_cap(current_cap: int) -> int:
    """
    Softly cap workers to ~75% of the per-user process limit (where applicable).
    Threads usually don't count as separate "processes" everywhere, so treat this
    as an advisory upper bound, not a guarantee.
    """
    try:
        import resource  # type: ignore
        soft, _hard = resource.getrlimit(resource.RLIMIT_NPROC)
        inf         = getattr(resource, "RLIM_INFINITY", -1)
        # If unlimited or nonsensical, do nothing.
        if soft in (inf, -1) or soft is None or soft <= 0:
            return current_cap
        cap         = max(1, int(soft * 0.75))
        return min(current_cap, cap)
    except Exception:
        return current_cap


def _effective_workers(requested: int, num_tasks: int, io_bound: bool = True) -> int:
    """
    Choose a sensible max_workers value.

    Args:
        requested: Desired worker count from CLI.
        num_tasks: Number of concurrent tasks you will submit.
        io_bound:  Whether the workload is primarily I/O bound.

    Returns:
        A worker count >= 1 and no larger than the task count and a heuristic cap.

    Raises:
        None
    """
    cpu:       int = os.cpu_count() or 1
    # Heuristic caps: generous for I/O, conservative for CPU-bound.
    cap:       int = 64 if io_bound else max(1, cpu)
    n:         int = min(requested, num_tasks, cap)
    if _should_use_proc_cap():
        n = _advisory_user_proc_limit_cap(n)
    return max(1, n)


def _run_tcp_checks_with_pool(tcp_targets: list[tuple[str, int]],
                              timeout: float, requested_workers: int) -> bool:
    """
    Run the TCP checks using a thread pool with safe sizing and backoff.

    Args:
        tcp_targets:       (host, port) pairs to probe.
        timeout:           Per-connection timeout in seconds.
        requested_workers: CLI-requested max worker count.

    Returns:
        True if any TCP connection succeeded, else False.

    Raises:
        None (creation failures are handled with backoff and logging).
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    # 1) Never spawn more workers than concurrent tasks; pick a safe cap.
    n_workers: int = _effective_workers(requested=requested_workers,
                                        num_tasks=len(tcp_targets),
                                        io_bound=True)

    # 2) Backoff plan if the OS refuses to create that many threads.
    #    Try n, then n//2, then 1.
    backoff_plan: list[int] = [n_workers, max(1, n_workers // 2), 1]

    for n in backoff_plan:
        try:
            logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("ThreadPool: attempting max_workers=%d", n)
            with ThreadPoolExecutor(max_workers=n) as pool:
                futures = {pool.submit(_tcp_connect, h, p, timeout): (h, p) for (h, p) in tcp_targets}
                for fut in as_completed(futures):
                    try:
                        if fut.result():
                            try:  # Optional: stop launching/awaiting more work asap
                                pool.shutdown(cancel_futures=True)
                            except TypeError:  # Python < 3.9 doesn't support cancel_futures
                                pass
                            return True
                    except Exception as exc:
                        logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("TCP: unexpected exception: %s", exc)
            return False
        except (RuntimeError, OSError, MemoryError) as exc:
            logging.warning("Could not start thread pool with %d workers (%s). Trying fewer.", n, exc)
            continue

    # If even 1 worker fails, consider TCP unreachable.
    return False


@dataclass
class CheckResult:
    """Aggregate results from the multi-strategy connectivity check."""
    tcp_ok:           bool
    dns_ok:           bool
    http_ok:          bool
    captive_detected: bool


def _check_once(timeout:     float, workers: int,
                include_ipv6: bool, ignore_proxies: bool) -> CheckResult:
    """
    Perform one pass of the connectivity checks.

    Args:
        timeout:        Per-attempt timeout in seconds.
        workers:        Thread pool size for parallel network attempts.
        include_ipv6:   Whether to include IPv6 TCP targets.
        ignore_proxies: If True, bypass env proxies for HTTP probes.

    Returns:
        CheckResult with booleans for TCP, DNS, HTTP, and captive portal detection.

    Raises:
        None.
    """
    import socket
    tcp_targets: list[tuple[str, int]] = IPV4_TARGETS.copy()
    if include_ipv6 and getattr(socket, "has_ipv6", False):
        tcp_targets.extend(IPV6_TARGETS)

    dns_ok:           bool = False
    http_ok:          bool = False
    captive_detected: bool = False

    # --- TCP connectivity to numeric IPs (with safe sizing & backoff) ---
    tcp_ok: bool = _run_tcp_checks_with_pool(tcp_targets=tcp_targets,
                                            timeout=timeout,
                                            requested_workers=workers)

    # --- DNS resolution (sequential with quick bail-out) ---
    for name in DNS_TEST_NAMES:
        if _dns_resolve(name, timeout=timeout):
            dns_ok = True
            break

    # --- HTTP probes (sequential, quick bail-outs) ---
    opener = _build_http_opener(ignore_proxies=ignore_proxies)
    for probe in HTTP_PROBES:
        ok, status, body, final_url = _http_probe(
            url=probe["url"],
            method=probe["method"],
            timeout=timeout,
            opener=opener,
        )
        if ok and _http_meets_expectations(status, body, probe["expect"]):
            http_ok = True
            logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("HTTP probe OK: %s", probe['note'])
            break
        # Any strong hints of a captive portal?
        if _looks_like_captive(status, final_url, body):
            captive_detected = True
            logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("Captive portal suspected at %s (status=%d, final_url=%s)", probe['url'], status, final_url)
            # We can stop early—being behind a captive portal ≠ usable internet.
            break

    return CheckResult(
        tcp_ok=tcp_ok,
        dns_ok=dns_ok,
        http_ok=http_ok,
        captive_detected=captive_detected,
    )


def is_internet_available(timeout_per_step: float = 2.5,
                          retries:            int = 1,
                          workers:            int = 6,
                          include_ipv6:      bool = False,
                          strict:            bool = False,
                          ignore_proxies:    bool = False) -> bool:
    """
    Determine if the internet is available using multiple methods.

    Strategy (per attempt):
        1) TCP to multiple well-known numeric IPs (no DNS).
        2) DNS resolution of common hostnames.
        3) HTTP(S) probes with expectations and captive-portal detection.

    Aggregation logic:
        - If captive portal is detected -> return False immediately.
        - If any HTTP probe passes expectations -> return True.
        - Else if TCP OK and DNS OK -> return True.
        - Else:
            * If strict is False and TCP OK alone -> return False
              (raw TCP alone is not considered sufficient for "internet usable").
            * If strict is True -> still False.

    Args:
        timeout_per_step: Timeout (seconds) per individual network attempt.
        retries:          Number of times to repeat the full check if the result is False.
        workers:          Thread pool size for TCP checks.
        include_ipv6:     Whether to include IPv6 targets.
        strict:           Require stronger evidence of connectivity.
        ignore_proxies:   Disable env proxies for HTTP probes.

    Returns:
        True if the internet appears reachable and usable, else False.

    Raises:
        None.
    """
    attempts: int = max(1, retries + 1)
    for attempt in range(1, attempts + 1):
        logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug(f"Connectivity attempt {attempt}/{attempts}")
        res = _check_once(timeout=timeout_per_step,
                          workers=workers,
                          include_ipv6=include_ipv6,
                          ignore_proxies=ignore_proxies)

        logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug(
            "Result(tcp_ok=%s, dns_ok=%s, http_ok=%s, captive=%s)",
            res.tcp_ok, res.dns_ok, res.http_ok, res.captive_detected
        )

        if res.captive_detected:
            return False

        # HTTP probe success is the strongest positive signal (works with proxies too).
        if res.http_ok:
            return True

        # TCP + DNS (e.g., raw connectivity plus name resolution).
        if res.tcp_ok and res.dns_ok:
            return True

        # Only allow raw TCP success when NOT strict:
        if not strict and res.tcp_ok:
            return True

        # Otherwise, not enough evidence; possibly retry due to transient hiccups.
        if attempt < attempts:
            import time
            import random  # Jitter retries slightly.
            delay: float = 0.10 + 0.05 * attempt + random.uniform(0.0, 0.05)
            time.sleep(delay)
    return False


def detect_shell(options: Options) -> None:
    """
    Detect the current interactive shell, falling back to parent process name if needed.

    Args:
        options: Options object to store the detected shell information.

    Returns:
        None, but updates options.shell with the detected shell name.

    Raises:
        None, but logs an error if the shell cannot be detected via
        subprocess.CalledProcessError or FileNotFoundError.
    """
    import subprocess
    shell_path = os.getenv("SHELL")
    if not shell_path:  # If shell_path is None or empty (""), try to get the parent process name
        try:
            logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("SHELL environment variable not set, trying to detect shell from parent process.")
            ppid   = os.getppid()
            result = subprocess.run(["ps", "-p", str(ppid), "-o", "comm="],
                                    capture_output=True, text=True, check=True)
            shell_path = result.stdout.strip()
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            logging.error(f"Error detecting shell via ps: {e}")
    if shell_path:
        options.shell = ensure_path(shell_path).name.lstrip("-")
    else:
        logging.error("Could not detect shell from SHELL environment variable or parent process.")
        options.shell = None


def find_shell_rc_file(options: Options) -> None:
    """
    Find the shell configuration file for the current user, store in options.rc_file.
    For bash/zsh, also consider login‐shell files if the usual rc isn't present.

    Args:
        options: Options object containing the shell type and rc_file attribute.

    Returns:
        None, but updates options.rc_file with the path to the shell configuration file.

    Raises:
        None, but logs an error if the shell is unsupported or if no rc file is found
        for the specified shell.
    """
    candidates = []

    xdg = Path(os.environ.get("XDG_CONFIG_HOME", options.home / ".config"))
    if options.shell == "bash":
        candidates = [".bashrc", ".bash_profile", ".bash_login", ".profile"]
    elif options.shell == "zsh":
        candidates = [".zshrc", ".zprofile"]
    elif options.shell == "fish":
        candidates = [os.fspath(xdg / "fish" / "config.fish")]  # just to be consistent with the other strings.
    elif options.shell == "csh":
        candidates = [".cshrc"]
    elif options.shell == "tcsh":
        candidates = [".tcshrc"]
    else:
        logging.error(f"Unsupported shell: {options.shell}")
        options.rc_file = None
        return

    # pick the first one that actually exists
    for fname in candidates:
        path = options.home / fname
        if safe_is_file(path):
            options.rc_file = path
            break
    else:
        options.rc_file = None
        logging.error("No existing rc file found for %s shell in %s. Tried: %s.",
                      options.shell, options.home, ", ".join(candidates))


def find_additional_alias_files(options: Options) -> None:
    """Find additional alias files for the shell."""
    # Define common potential additional alias files based on the shell type.
    if options.shell == "bash":
        options.additional_alias_files.append(options.home / ".bash_aliases")
    elif options.shell == "zsh":
        options.additional_alias_files.append(options.home / ".zsh_aliases")
    elif options.shell == "fish":
        options.additional_alias_files.append(options.home / ".config" / "fish" / "conf.d" / "aliases.fish")
    elif options.shell == "csh":
        options.additional_alias_files.append(options.home / ".csh_aliases")
    elif options.shell == "tcsh":
        options.additional_alias_files.append(options.home / ".tcsh_aliases")
    else:
        logging.error(f"Unsupported shell for additional alias files: {options.shell}")
    valid_files = []
    for this_file in options.additional_alias_files:
        if safe_is_file(this_file):
            valid_files.append(this_file)
        else:
            logging.error(f"Additional alias file {this_file} does not exist for shell {options.shell}.")
    options.additional_alias_files = valid_files


def ensure_path(path: str | os.PathLike[str], absolute: bool = True) -> Path:
    """
    Ensure that the path is a Path. If not, make it a Path.

    Args:
        path:     The path to ensure is a Path object.
        absolute: If True (default), return an absolute path without resolving symlinks.

    Returns:
        A Path object (expanded for "~"). If absolute=True, it's absolute; otherwise it may be relative.
    """
    p = path if isinstance(path, Path) else Path(path)
    p = p.expanduser()  # always expand "~"
    return p.absolute() if absolute else p


def ensure_file(path: str | os.PathLike[str],
                raise_on_empty:  bool = False,
                allow_symlink:   bool = True,
                follow_symlinks: bool = True) -> Path:
    """
    Ensure that the given path is an existing file and return it as a Path object.

    Args:
        path:            The path to check.
        raise_on_empty:  If True,  raise an exception if the file is empty.
        allow_symlink:   If False, raise an exception if the path is a symlink.
        follow_symlinks: If False, do not follow symlinks when checking if it's a file.
                         If False, symlinks aren't considered files (even if allow_symlink=True).
                         With follow_symlinks=False, attribute reads (size/mtime/etc.) also don't
                         follow symlinks.

    Returns:
        A Path object representing the file.

    Raises:
        FileNotFoundError: If the file does not exist.
        IsADirectoryError: If the path exists but is a directory.
        ValueError:        If the path exists but is not a regular file, or if symlinks are not allowed.
        ValueError:        If raise_on_empty is True and the file is empty (or bad permissions, etc.)
    """
    p      = ensure_path(path)  # expanded + absolute, no symlink resolution
    exists = safe_exists(p, follow_symlinks=follow_symlinks)
    if not exists:
        raise FileNotFoundError(f"No such file: {os.fspath(p)}")
    if not allow_symlink and p.is_symlink():
        raise ValueError(f"Symlinks not allowed: {os.fspath(p)}")
    if not safe_is_file(p, follow_symlinks=follow_symlinks):
        if safe_is_dir( p, follow_symlinks=follow_symlinks):
            raise IsADirectoryError(f"Expected a file, got directory: {os.fspath(p)}")
        raise ValueError(f"Path exists but is not a regular file: {os.fspath(p)}")
    if (p_size := safe_size(p, follow_symlinks=follow_symlinks)) is not None:
        if raise_on_empty and p_size == 0:
            raise ValueError(f"File is empty: {os.fspath(p)}")
        elif p_size == 0:
            logging.warning("File is empty: %s", os.fspath(p))
    else:
        if raise_on_empty:
            raise ValueError(f"File size is unknown (permissions?): {os.fspath(p)}")
        else:
            logging.warning("File size is unknown (permissions?): %s", os.fspath(p))
    return p


def ensure_dir(path: str | os.PathLike[str],
               allow_symlink:   bool = True,
               follow_symlinks: bool = True) -> Path:
    """
    Ensure that the given path is an existing directory and return it as a Path object.

    Args:
        path:            The path to check.
        allow_symlink:   If False, raise an exception if the path is a symlink.
        follow_symlinks: If False, do not follow symlinks when checking if it's a directory.
                         If False, symlinks aren't considered directories (even if allow_symlink=True).
                         With follow_symlinks=False, attribute reads (size/mtime/etc.) also don't
                         follow symlinks.

    Returns:
        A Path object representing the directory.

    Raises:
        FileNotFoundError:  If the directory does not exist.
        NotADirectoryError: If the path exists but is not a directory.
    """
    p      = ensure_path(path)  # expanded + absolute, no symlink resolution
    exists = safe_exists(p, follow_symlinks=follow_symlinks)
    if not exists:
        raise FileNotFoundError(f"No such directory: {os.fspath(p)}")
    if not allow_symlink and p.is_symlink():
        raise ValueError(f"Symlinks not allowed: {os.fspath(p)}")
    if not safe_is_dir(p, follow_symlinks=follow_symlinks):
        raise NotADirectoryError(f"Expected a directory, got file: {os.fspath(p)}")
    return p


_IS_PY_3_13: Final[bool] = sys.version_info >= (3, 13)


def _is_file(p: Path, follow_symlinks: bool) -> bool:
    """
    Version-proof 'is regular file?' that can avoid following symlinks.
    """
    if _IS_PY_3_13:  # 3.13+ supports follow_symlinks
        return p.is_file(follow_symlinks=follow_symlinks)
    if follow_symlinks:
        return p.is_file()
    try:
        import stat
        return stat.S_ISREG(p.lstat().st_mode)
    except FileNotFoundError:
        return False


def _is_dir(p: Path, follow_symlinks: bool) -> bool:
    """
    Version-proof 'is directory?' that can avoid following symlinks.
    """
    if _IS_PY_3_13:  # 3.13+ supports follow_symlinks
        return p.is_dir(follow_symlinks=follow_symlinks)
    if follow_symlinks:
        return p.is_dir()
    try:
        import stat
        return stat.S_ISDIR(p.lstat().st_mode)
    except FileNotFoundError:
        return False


IGNORE_THESE_ERRORS: Final[frozenset[int]] = frozenset(
    e for e in {
        errno.EACCES, errno.EPERM, errno.ELOOP, errno.ENOTDIR, errno.ENOENT,
        getattr(errno, "ESTALE", None),   # NFS: stale file handle (may not exist)
    } if e is not None
)


def safe_exists(path: str | os.PathLike[str],
                follow_symlinks: bool = True) -> bool:
    """
    Like Path.exists()/os.path.lexists(), but doesn't raise on permission/loop errors.

    Args:
        path:            The path to check.
        follow_symlinks: If False, do not follow symlinks when checking if it exists.

    Returns:
        True if the path appears to exist (respecting follow_symlinks), False if it doesn't.
        For certain access/loop issues, returns True to avoid misclassifying as 'missing'.
    """
    p = path if isinstance(path, Path) else ensure_path(path)

    if not follow_symlinks:
        # lexists() doesn't raise for permission and treats a symlink itself as 'exists'
        return os.path.lexists(os.fspath(p))

    try:
        return p.exists()
    except PermissionError:
        # Treat as 'exists but inaccessible' to avoid raising FileNotFoundError upstream
        logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug(
            "%s: permission denied: %s", return_method_name(), os.fspath(p)
        )
        return True
    except OSError as e:
        # Fine-grained handling: missing vs. other transient/loop errors
        if e.errno in (errno.ENOENT, errno.ENOTDIR):
            return False
        if e.errno in IGNORE_THESE_ERRORS:
            logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug(
                "%s: suppressed errno=%s (%s): %s", return_method_name(),
                e.errno, getattr(errno, "errorcode", {}).get(e.errno, "?"), os.fspath(p)
            )
            # assume it exists but is problematic (loop, access, stale handle)
            return True
        raise


def safe_is_file(path: str | os.PathLike[str],
                 follow_symlinks: bool = True) -> bool:
    """
    Like Path.is_file(), but returns False on permission errors instead of raising.
    Uses _is_file() for pre-3.13 compatibility and no-follow mode.

    Args:
        path:            The file or directory path to check.
        follow_symlinks: Whether to follow symlinks (default: True).

    Returns:
        True if the path is a file, False otherwise.

    Raises:
        Intentionally designed to catch PermissionError, FileNotFoundError,
        some OSError variations. But not all.
    """
    p = path if isinstance(path, Path) else ensure_path(path)
    try:
        return _is_file(p, follow_symlinks=follow_symlinks)
    except PermissionError:
        logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("safe_is_file: permission denied: %s", p)
        return False
    except OSError as e:
        if e.errno in IGNORE_THESE_ERRORS:
            logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug(
                "%s: suppressed errno=%s (%s): %s", return_method_name(),
                e.errno, getattr(errno, "errorcode", {}).get(e.errno, "?"), p
            )
            return False
        raise


def safe_is_dir(path: str | os.PathLike[str],
                follow_symlinks: bool = True) -> bool:
    """
    Like Path.is_dir(), but returns False on permission errors instead of raising.
    Uses _is_dir() for pre-3.13 compatibility and no-follow mode.

    Args:
        path:            The file or directory path to check.
        follow_symlinks: Whether to follow symlinks (default: True).

    Returns:
        True if the path is a directory, False otherwise.

    Raises:
        Intentionally designed to catch PermissionError, FileNotFoundError,
        some OSError variations. But not all.
    """
    p = path if isinstance(path, Path) else ensure_path(path)
    try:
        return _is_dir(p, follow_symlinks=follow_symlinks)
    except PermissionError:
        logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("safe_is_dir: permission denied: %s", p)
        return False
    except OSError as e:
        if e.errno in IGNORE_THESE_ERRORS:
            logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug(
                "%s: suppressed errno=%s (%s): %s", return_method_name(),
                e.errno, getattr(errno, "errorcode", {}).get(e.errno, "?"), p
            )
            return False
        raise


def safe_stat(path: str | os.PathLike[str],
              follow_symlinks: bool = True) -> os.stat_result | None:
    """
    Like Path.stat()/lstat(), but returns None on permission/missing/loop errors.

    Args:
        path:            The file or directory path to stat.
        follow_symlinks: Whether to follow symlinks (default: True).
                         If true, uses Path.stat() else Path.lstat().

    Returns:
        An os.stat_result object or None if an error occurred.

    Raises:
        Intentionally designed to catch PermissionError, FileNotFoundError,
        some OSError variations. But not all.
    """
    p = path if isinstance(path, Path) else ensure_path(path)
    try:
        return p.stat() if follow_symlinks else p.lstat()
    except (PermissionError, FileNotFoundError):
        logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("%s: access/missing: %s",
                                                                          return_method_name(),
                                                                          os.fspath(p))
        return None
    except OSError as e:
        if e.errno in IGNORE_THESE_ERRORS:
            logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug(
                "%s: suppressed errno=%s (%s): %s", return_method_name(),
                e.errno, getattr(errno, "errorcode", {}).get(e.errno, "?"), p
            )
            return None
        raise


def safe_size(path: str | os.PathLike[str],
              follow_symlinks: bool = True) -> int | None:
    """
    Like Path.stat().st_size, but returns None on permission/missing/loop errors.

    Args:
        path:            The file or directory path to stat().st_size
        follow_symlinks: Whether to follow symlinks (default: True).
                         If true, uses Path.stat() else Path.lstat().

    Returns:
        The size of the file in bytes or None if an error occurred.
    """
    st = safe_stat(path, follow_symlinks=follow_symlinks)
    return None if st is None else st.st_size


def safe_mtime(path: str | os.PathLike[str],
               follow_symlinks: bool = True,
               ns: bool = False) -> int | float | None:
    """
    Return mtime (seconds float or ns int) or None on errors.

    Args:
        path:            The file or directory path to stat().st_mtime
        follow_symlinks: Whether to follow symlinks (default: True).
                         If true, uses Path.stat() else Path.lstat().
        ns:              Whether to return the result in nanoseconds (default: False).

    Returns:
        The mtime of the file in seconds or nanoseconds, or None if an error occurred.
    """
    st = safe_stat(path, follow_symlinks=follow_symlinks)
    if st is None:
        return None
    return st.st_mtime_ns if ns else st.st_mtime


def safe_ctime(path: str | os.PathLike[str],
               follow_symlinks: bool = True,
               ns: bool = False) -> int | float | None:
    """
    Return ctime (seconds float or ns int) or None on errors.
    Note: On POSIX, ctime == inode *change* time, not creation time.
          On Windows, ctime is the file *creation* time.

    Args:
        path:            The file or directory path to stat().st_ctime
        follow_symlinks: Whether to follow symlinks (default: True).
                         If true, uses Path.stat() else Path.lstat().
        ns:              Whether to return the result in nanoseconds (default: False).

    Returns:
        The ctime of the file in seconds or nanoseconds, or None if an error occurred.
    """
    st = safe_stat(path, follow_symlinks=follow_symlinks)
    if st is None:
        return None
    return st.st_ctime_ns if ns else st.st_ctime


def download_file(url: str, dest: str | os.PathLike[str], retries: int = 5,
                  chunk_size: int = 1 << 20, timeout: int = 30,
                  headers: dict[str, str] | None = None) -> None:
    """
    Download a file to 'dest' with retry + exponential backoff.
    Writes to a temporary .part file and renames atomically on success.
    Verifies Content-Length if provided.
    Logs progress by bytes (rough).
    Also checks free disk space (if size is known) before downloading.

    Args:
        url:        The source URL to download from.
        dest:       Destination file path.
        retries:    Number of attempts (default 5 is a good balance for transient errors).
        chunk_size: Bytes per read chunk (default 1MiB).
        timeout:    Per-attempt socket timeout (seconds).
        headers:    Optional dict of HTTP headers to include in the request.

    Returns:
        None. Writes the file to 'dest'.

    Raises:
        SystemExit on failure after retries or if insufficient free space is detected.
    """
    import time
    from urllib.request import Request, urlopen
    from urllib.error import URLError, HTTPError
    import socket

    fallback_logging_config()
    dest = ensure_path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    temp = dest.with_suffix(dest.suffix + ".part")

    base_headers = {"Accept-Encoding" : "identity",
                    "User-Agent"      : "python-download/1.0", }
    eff_headers  = {**base_headers, **(headers or {})}

    succeeded = False  # Track if download succeeded

    # Remove any stale partial to avoid skewing free-space checks.
    try:
        if safe_exists(temp):
            temp.unlink()
    except OSError:
        # If we can't remove it, we'll truncate on open later; free-space check may be conservative.
        pass

    # Pre-flight: attempt to learn expected size and check free space.
    expected: int | None = None
    try:
        req_head = Request(url, headers=eff_headers, method="HEAD")
        with urlopen(req_head, timeout=timeout) as r:
            cl = r.headers.get("Content-Length")
            if cl:
                try:
                    expected = int(cl.strip())
                except ValueError:
                    expected = None
    except Exception as e:
        logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("HEAD probe failed (%s); proceeding without pre-known size.", e)

    if expected is not None:
        # Skip re-download if size matches on disk already.
        if safe_exists(dest):
            try:
                if (dest_size := safe_size(dest)) is not None and dest_size == expected:
                    logging.info("File already present with expected size; skipping: %s", os.fspath(dest))
                    return
                elif dest_size is not None:
                    logging.info("File already present but size mismatch (have %s, need %s); re-downloading: %s",
                                 human_bytesize(dest_size), human_bytesize(expected), os.fspath(dest))
                elif dest_size is None:
                    logging.warning("File size is unknown (permissions?): %s", os.fspath(dest))
                    sys.exit(1)
                else:
                    logging.error(f"File {os.fspath(dest)} exists but has a VERY CONFUSING size mismatch (have {dest_size}, need {expected}).")
            except OSError:
                pass
        free_bytes = query_free_space(dest)
        if free_bytes < expected:
            raise SystemExit(f"Not enough disk space: need {human_bytesize(expected)}, have {human_bytesize(free_bytes)}")

    backoff = 1.0
    last_err: Exception | None = None

    for attempt in range(1, max(1, retries) + 1):
        try:
            logging.info("Downloading %s → %s (attempt %d/%d)", url, dest, attempt, retries)
            req = Request(url, headers=eff_headers)
            with urlopen(req, timeout=timeout) as resp:
                total = resp.headers.get("Content-Length")
                total_i = None
                if total:
                    try:
                        total_i = int(total.strip())
                    except ValueError:
                        pass
                # Re-check space at the moment of download if size is known.
                if total_i is not None:
                    free_bytes = query_free_space(dest)
                    if free_bytes < total_i:
                        raise SystemExit(
                            f"Not enough disk space: need {human_bytesize(total_i)}, have {human_bytesize(free_bytes)}"
                        )

                with temp.open("wb") as f:
                    downloaded = 0
                    last_bucket = -1
                    while True:
                        chunk = resp.read(chunk_size)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_i:
                            # Lightweight textual progress (kept minimal for logging)
                            pct = int(downloaded * 100 / total_i)
                            bucket = pct // 10
                            # Log just once every ~10% but not at 0%
                            if pct and pct % 10 == 0 and bucket != last_bucket:
                                logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("... %d%% (%s out of %s)", pct, human_bytesize(downloaded), human_bytesize(total_i))
                                last_bucket = bucket
                    f.flush()
                    os.fsync(f.fileno())

            # Verify size if Content-Length available
            if total_i is not None:
                if (actual_size := safe_size(temp)) is None:
                    raise IOError(f"Could not determine size of downloaded file {os.fspath(temp)}")
                if actual_size != total_i:
                    raise IOError(f"Incomplete download: expected {total_i} bytes, got {actual_size} bytes")
            temp.replace(dest)
            logging.info("Saved %s (%s)", os.fspath(dest), human_bytesize(safe_size(dest)))
            succeeded = True
            return
        except (HTTPError, URLError, socket.timeout, IOError) as e:
            last_err = e
            logging.warning("Download failed (%s).", e)
            if attempt >= retries:
                break
            sleep_s = backoff
            backoff = min(backoff * 2, 30.0)  # cap backoff
            logging.info("Retrying in %.1f seconds...", sleep_s)
            time.sleep(sleep_s)
        except Exception as e:
            # Unexpected errors: don't loop indefinitely
            last_err = e
            logging.exception("Unexpected error during download.")
            break
        finally:
            try:
                if not succeeded and safe_exists(temp):
                    temp.unlink()
            except OSError:
                pass

    raise SystemExit(f"Failed to download {url} after {retries} attempts. Last error: {last_err}")


def query_free_space(path: str | os.PathLike[str]) -> int:
    """
    Return the free space (in bytes) available to the current user on the
    filesystem that contains 'path'. Works for files or directories, and
    for paths that don't yet exist (it climbs to the nearest existing parent).

    Args:
        path: A file or directory path.

    Returns:
        Free space in bytes available to the current user on the filesystem.

    Raises:
        FileNotFoundError: If no existing parent directory is found.
        OSError:           If the filesystem information cannot be retrieved.
    """
    p = ensure_path(path)

    # Use the path itself if it's an existing directory; otherwise use its parent.
    base = p if safe_is_dir(p) else p.parent

    # Climb up until we find an existing directory.
    while not safe_exists(base):
        if base == base.parent:
            raise FileNotFoundError(f"No existing parent found for {path!r}")
        base = base.parent

    # POSIX: prefer statvfs to get user-available bytes (excludes reserved blocks).
    if hasattr(os, "statvfs"):
        st = os.statvfs(base)
        return st.f_bavail * st.f_frsize

    # Windows / others: fallback to shutil.disk_usage
    import shutil
    return shutil.disk_usage(str(base)).free


def ensure_even_dimensions(image_path: str | os.PathLike[str]) -> None:
    """Ensure the image at 'image_path' has dimensions divisible by 2, by resizing if necessary."""
    from PIL import Image
    fallback_logging_config()
    image_path = ensure_file(image_path)
    with Image.open(image_path) as img:
        width, height = img.size
        new_width  = width  if width  % 2 == 0 else width  - 1
        new_height = height if height % 2 == 0 else height - 1

        if new_width != width or new_height != height:
            try:
                img = img.resize((new_width, new_height), Image.LANCZOS)
                img.save(image_path)
                logging.info("Resized image to even dimensions: width = %d, height = %d", new_width, new_height)
            except OSError as e:
                raise ValueError(f"Could not resize image {os.fspath(image_path)} to even dimensions: {e}") from e
        else:
            logging.info("Image already has even dimensions: width = %d, height = %d", width, height)


def find_ffmpeg() -> str | None:
    """
    Return a full path to an ffmpeg executable if found, else None.
    Tries: env vars, PATH, common Conda and Windows/Cygwin/MSYS installs,
    and (optionally) imageio-ffmpeg if available.

    Args:
        None

    Returns:
        A string containing the path to the ffmpeg executable or None if not found.

    Raises:
        None
    """
    import shutil
    # 1) Explicit env vars (user can set one of these)
    for env_key in ("FFMPEG", "FFMPEG_PATH", "IMAGEIO_FFMPEG_EXE"):
        p = os.environ.get(env_key)
        if p:
            p = ensure_file(p)
            return os.fspath(p)

    # 2) On PATH (handles .exe on Windows automatically)
    for name in ("ffmpeg", "ffmpeg.exe"):
        p = shutil.which(name)
        if p:
            p = ensure_file(p)
            return os.fspath(p)

    # 3) Typical Conda/Miniconda/Mambaforge locations
    sp = Path(sys.prefix)  # current Python env prefix
    candidates = [
        sp / "bin"     / "ffmpeg",              # Unix-like
        sp / "Library" / "bin" / "ffmpeg.exe",  # Windows (Conda)
        sp / "Scripts" / "ffmpeg.exe",          # Windows (alt)
    ]

    # 4) Common Windows installs (adjust or extend as you like)
    candidates += [
        Path(r"C:\Program Files\ffmpeg\bin\ffmpeg.exe"),
        Path(r"C:\Program Files (x86)\ffmpeg\bin\ffmpeg.exe"),
        Path(r"C:\ffmpeg\bin\ffmpeg.exe"),
        Path(r"C:\cygwin64\bin\ffmpeg.exe"),
        Path(r"C:\msys64\usr\bin\ffmpeg.exe"),
    ]

    # 5) Optional: imageio-ffmpeg packaged binary if user has it
    try:
        import imageio_ffmpeg  # type: ignore
        p = imageio_ffmpeg.get_ffmpeg_exe()
        if p:
            p = ensure_file(p)
            return os.fspath(p)
    except Exception:
        pass

    for c in candidates:
        if safe_exists(c):
            return os.fspath(c)

    return None


def human_bytesize(num: float | int | None, *, suffix: str = "B", si: bool = False, precision: int = 1,
                   space: bool = True, trim_trailing_zeros: bool = False, long_units: bool = False) -> str:
    """
    Formats a byte count into a human-readable string.

    Args:
        num:                 Size in bytes. Negative values are preserved with a leading minus.
                             If None, returns "None".
        suffix:              Unit suffix appended after the prefix (defaults to "B"). If long_units is True and
                             suffix is "B", "bytes" is appended in the output. Otherwise, the suffix is appended to the long name.
        si:                  If True, use powers of 1000 with SI prefixes (k, M, G, ... up to R, Q).
                             If False, use powers of 1024 with IEC prefixes (Ki, Mi, Gi, ... up to Ri, Qi).
        precision:           Digits to show after the decimal point.
        space:               If True, inserts a space between the number and the unit (ignored when long_units is True).
        trim_trailing_zeros: If True, removes trailing zeros and any dangling decimal point.
        long_units:          If True, spell out unit names ("bytes", "kibibytes", ... "quebibytes"/"quettabytes").

    Returns:
        A concise string such as "1.5KiB", "1.5 kB", or "1.5 megabytes" depending on options.
        If num is None, returns "None".
        Handles negative values with a leading minus sign and units up to "quebibytes" (2^100 = 1024^10 bytes) for IEC,
        or "quettabytes" (10^30 bytes) for SI.

    Raises:
        None.
    """
    if num is None:
        return "None"
    if precision < 0:
        raise ValueError("precision must be non-negative")
    if suffix and not isinstance(suffix, str):
        suffix = str(suffix)
    step = 1000.0 if si else 1024.0
    symbols = (["", "k", "M", "G", "T", "P", "E", "Z", "Y", "R", "Q"]
               if si else ["", "Ki", "Mi", "Gi", "Ti", "Pi", "Ei", "Zi", "Yi", "Ri", "Qi"])
    long_prefixes = (["", "kilo", "mega", "giga", "tera", "peta",
                      "exa", "zetta", "yotta", "ronna", "quetta"]
                     if si else ["", "kibi", "mebi", "gibi", "tebi",
                                 "pebi", "exbi", "zebi", "yobi", "robi", "quebi"])

    sign = "-" if num < 0 else ""
    n = abs(float(num))
    i = 0
    while n >= step and i < len(symbols) - 1:
        n /= step
        i += 1

    s = f"{n:.{precision}f}"
    if trim_trailing_zeros:
        s = s.rstrip("0").rstrip(".")

    if long_units:
        long_name = long_prefixes[i]
        if suffix == "B":
            long_name += "bytes"
        else:
            long_name += suffix
        return f"{sign}{s} {long_name}"
    else:
        sep = " " if space else ""
        return f"{sign}{s}{sep}{symbols[i]}{suffix}"


def my_plural(n: int, word: str) -> str:
    """
    Return a pluralized version of 'word' preceded by 'n'.

    Behavior:
    - If the open-source 'inflect' library is available, use it for pluralization.
    - Otherwise, fall back to a casefold()-based irregulars table, some uncountables,
      and a small set of morphological rules.

    Examples (fallback behavior):
        1 millennium -> "1 millennium"
        2 millennium -> "2 millennia"
        2 millenium  -> "2 millennia"   # (handles the common misspelling too)

    Args:
        n:    The quantity of the item.
        word: The singular form of the item.

    Raises:
        None.
    """
    if n == 1:
        return f"{n} {word}"

    # 1) Try the open-source 'inflect' library if present
    try:
        import inflect  # MIT-licensed, widely used for pluralization
        engine = getattr(my_plural, "_inflect_engine", None)
        if engine is None:
            engine = inflect.engine()
            my_plural._inflect_engine = engine

        # plural_noun returns False when it can't/shouldn't pluralize
        plural = engine.plural_noun(word)
        if not plural:
            plural = engine.plural(word)
        if plural:
            return f"{n} {plural}"
    except Exception:
        # Fall through to custom logic if inflect isn't available or errors
        pass

    # 2) Fallback: irregular/uncountable lists (case-insensitive via casefold)
    irregulars = {
        # Common irregulars
        "child"      : "children",
        "person"     : "people",
        "man"        : "men",
        "woman"      : "women",
        "mouse"      : "mice",
        "goose"      : "geese",
        "tooth"      : "teeth",
        "foot"       : "feet",
        "ox"         : "oxen",

        # Classical/latin/greek
        "cactus"     : "cacti",
        "focus"      : "foci",
        "fungus"     : "fungi",
        "nucleus"    : "nuclei",
        "syllabus"   : "syllabi",
        "analysis"   : "analyses",
        "diagnosis"  : "diagnoses",
        "thesis"     : "theses",
        "crisis"     : "crises",
        "phenomenon" : "phenomena",
        "criterion"  : "criteria",
        "datum"      : "data",
        "index"      : "indices",
        "appendix"   : "appendices",
        "matrix"     : "matrices",
        "vertex"     : "vertices",
        "radius"     : "radii",
        "alumnus"    : "alumni",
        "alumna"     : "alumnae",
        "bacterium"  : "bacteria",
        "medium"     : "media",
        "millennium" : "millennia",
        "millenium"  : "millennia",  # handle common misspelling

        # Mixed/accepted forms — pick one
        "octopus"    : "octopuses",
        "platypus"   : "platypuses",
        "virus"      : "viruses",
    }

    uncountables = {
        "sheep", "fish", "deer", "series", "species", "aircraft", "moose",
        "bison", "salmon", "trout", "swine", "rice", "information", "equipment",
        "money", "news", "offspring", "fruit"
    }

    def _preserve_simple_case(src: str, target: str) -> str:
        """Match ALLCAPS or Titlecase of 'src' onto 'target'."""
        if src.isupper():
            return target.upper()
        if src.istitle():
            # Capitalize first letter only; keeps internal case of target
            return target[:1].upper() + target[1:]
        return target

    def _basic_rules(w: str) -> str:
        """Very small set of English pluralization rules."""
        lw = w.casefold()
        # Endings that usually take 'es'
        if lw.endswith(("s", "ss", "sh", "ch", "x", "z")):
            return w + "es"

        # consonant + 'y' -> 'ies'
        vowels = set("aeiou")
        if len(w) >= 2 and w[-1] in "yY" and w[-2].casefold() not in vowels:
            return w[:-1] + "ies"

        # Words ending with 'f' / 'fe' -> 'ves' (with some common exceptions)
        f_exceptions = {"roof", "chief", "chef", "belief", "cliff", "proof", "reef", "gulf", "brief"}
        if lw.endswith("fe") and lw[:-2] not in f_exceptions:
            return w[:-2] + "ves"
        if lw.endswith("f") and lw[:-1] not in f_exceptions:
            return w[:-1] + "ves"

        # Words ending with 'o' sometimes take 'es' (common subset)
        o_es = {"potato", "tomato", "hero", "echo", "torpedo", "veto"}
        if lw.endswith("o") and lw in o_es:
            return w + "es"

        # Default: just 's'
        return w + "s"

    key = word.casefold()

    if key in uncountables:
        plural_word = word  # unchanged
    elif key in irregulars:
        plural_word = _preserve_simple_case(word, irregulars[key])
    else:
        plural_word = _basic_rules(word)

    return f"{n} {plural_word}"


def human_timespan(timespan: int | float) -> str:
    """
    Format a time span in seconds into a human-readable string.
    Negative values are treated as absolute.

    Args:
        timespan: A float or int representing the time span in seconds.

    Returns:
        A human-readable string describing the time span, such as
        "1 year, 2 weeks, 3 days, 4 hours, 5 minutes and 6.789 seconds".
        If the timespan is zero, returns "0 seconds".

    Raises:
        None.
    """
    # Work in integer milliseconds to avoid float modulo issues
    total_ms = int(round(abs(float(timespan)) * 1000))
    if total_ms == 0:
        return "0 seconds"

    MS_PER_MINUTE =         60_000
    MS_PER_HOUR   =      3_600_000
    MS_PER_DAY    =     86_400_000
    MS_PER_WEEK   =    604_800_000
    MS_PER_YEAR   = 31_557_600_000  # 365.25 days

    components: list[str] = []

    years, rem   = divmod(total_ms, MS_PER_YEAR)
    weeks, rem   = divmod(rem,      MS_PER_WEEK)
    days,  rem   = divmod(rem,      MS_PER_DAY)
    hours, rem   = divmod(rem,      MS_PER_HOUR)
    minutes, rem = divmod(rem,      MS_PER_MINUTE)
    seconds = rem / 1000.0  # in [0, 60)

    if years:   components.append(my_plural(years,     "year"))
    if weeks:   components.append(my_plural(weeks,     "week"))
    if days:    components.append(my_plural(days,       "day"))
    if hours:   components.append(my_plural(hours,     "hour"))
    if minutes: components.append(my_plural(minutes, "minute"))
    if seconds:
        s = f"{seconds:.3f}".rstrip("0").rstrip(".")
        components.append(f"{s} second" + ("" if seconds == 1.0 else "s"))

    if len(components) == 1:
        return components[0]
    return ", ".join(components[:-1]) + " and " + components[-1]


def format_date_range(date1: dt.datetime, date2: dt.datetime | None = None) -> str:
    """
    Process a pair of datetime.datetime dates and produce a formatted date range string
    where each date looks like 'Jan  7, 2025'. If date2 is not provided, it is set to date1.

    Args:
        date1: The first date as a datetime.datetime object.
        date2: The second date as a datetime.datetime object. If None, defaults to date1.

    Returns:
        A formatted string representing the date range, such as 'Jan  7, 2025' or 'Jan  7 - Feb  3, 2025'.
        If both dates are the same, it returns just one date like 'Jan  7, 2025'.

    Raises:
        ValueError: If either date1 or date2 is not a datetime.datetime object.
    """
    import datetime as dt

    month_names = {
        1: "Jan",  2: "Feb",  3: "Mar",  4: "Apr",
        5: "May",  6: "Jun",  7: "Jul",  8: "Aug",
        9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec"
    }

    # If date2 is not provided, set date2 to date1
    if date2 is None:
        date2 = date1

    # Make sure both dates are datetime.datetime objects
    if not isinstance(date1, dt.datetime) or not isinstance(date2, dt.datetime):
        raise ValueError(f"Both dates must be datetime.datetime objects, but date1 is {date1} with type {type(date1)} and date2 {date2} with type {type(date2)}.")

    # Ensure that the first date is earlier than the second.
    if date1 > date2:
        date1, date2 = date2, date1

    day1, day2     = date1.day, date2.day
    month1, month2 = month_names[date1.month], month_names[date2.month]
    year1, year2   = date1.year, date2.year

    if year1 == year2:
        if month1 == month2:
            if day1 == day2: return f"{month1} {day1:2d}, {year1}"
            else:            return f"{month1} {day1:2d} - {day2:2d}, {year1}"
        else:                return f"{month1} {day1:2d} - {month2} {day2:2d}, {year1}"
    else: return f"{month1} {day1:2d}, {year1} - {month2} {day2:2d}, {year2}"


_TIMESTAMP_PATTERN_RE: re.Pattern = re.compile(r"(\d{8}-\d{6}).pkl$")


def extract_timestamp(the_string: str) -> str | None:
    """Extract timestamp string (in format YYYYMMDD-HHMMSS) from the_string, or None if not found."""
    if (m := _TIMESTAMP_PATTERN_RE.search(the_string)):
        try:
            return m.group(1)
        except ValueError:
            return None
    return None


# Mapping of unit aliases (all in lowercase) to their equivalent in seconds
_UNIT_SECONDS = {
    **dict.fromkeys(["year", "years", "yr", "yrs", "calendar year", "calendar years"],    31_556_952),  # Average calender year = 365.2425 days (accounting for leap years)
    **dict.fromkeys(["solar year", "solar years", "tropical year", "tropical years"],     31_556_925.216),  # Average solar/tropical year = 365.24219 solar days = time for Earth to orbit the Sun once relative to the Sun/equinoxes
    **dict.fromkeys(["sidereal year", "sidereal years"],                                  31_558_149.54),  # Sidereal year = 365.25636 days = time for Earth to orbit the Sun once relative to the "fixed" stars
    **dict.fromkeys(["month", "months", "mo", "mos", "calendar month", "calendar months"], 2_629_746.0),  # Average calendar month = 30.436875 solar days
    **dict.fromkeys(["lunar month", "lunar months", "synodic month", "synodic months"],    2_551_442.9),  # Average lunar month (synodic month) = 29.53 solar days
    **dict.fromkeys(["week", "weeks", "wk", "wks"],                                          604_800.0),  # 7 solar days
    **dict.fromkeys(["day", "days", "d", "solar day", "solar days", "ephemeris day", "ephemeris days"], 86_400),  # 24 hours = time for Earth to rotate once relative to the Sun
    **dict.fromkeys(["sidereal day", "sidereal days"],                                                  86_164.0905),  # 23 hours, 56 minutes, 4.1 seconds = time for Earth to rotate once relative to the "fixed" stars
    **dict.fromkeys(["hour",         "hours",   "hr",  "hrs"],          3600),
    **dict.fromkeys(["minute",       "minutes", "min", "mins"],           60),
    **dict.fromkeys(["second",       "seconds", "sec", "secs", "s"],    1.00),
    **dict.fromkeys(["decisecond",   "deciseconds",  "ds"],            1E-01),
    **dict.fromkeys(["centisecond",  "centiseconds", "cs"],            1E-02),
    **dict.fromkeys(["millisecond",  "milliseconds", "ms"],            1E-03),
    **dict.fromkeys(["microsecond",  "microseconds", "us", "μs"],      1E-06),
    **dict.fromkeys(["nanosecond",   "nanoseconds",  "ns"],            1E-09),
    **dict.fromkeys(["picosecond",   "picoseconds",  "ps"],            1E-12),
    **dict.fromkeys(["femtosecond",  "femtoseconds", "fs"],            1E-15),
    **dict.fromkeys(["attosecond",   "attoseconds",  "as"],            1E-18),
    **dict.fromkeys(["zeptosecond",  "zeptoseconds", "zs"],            1E-21),
    **dict.fromkeys(["yoctosecond",  "yoctoseconds", "ys"],            1E-24),
    **dict.fromkeys(["planck time",  "planck times", "planck", "plancks", "pt"], 5.391_247E-44),  # Planck time
    **dict.fromkeys(["decade",       "decades"],                                315_569_252.16),  #   10 solar years
    **dict.fromkeys(["century",      "centuries"],                            3_155_692_521.60),  #  100 solar years
    **dict.fromkeys(["millennium",   "millennia"],                           31_556_925_216.00),  # 1000 solar years
    **dict.fromkeys(["megayear",     "megayears", "mya", "myr"],         31_556_925_216_000.00),  # 1E06 solar years
    **dict.fromkeys(["gigayear",     "gigayears", "gya", "gyr"],     31_556_925_216_000_000.00),  # 1E09 solar years
    **dict.fromkeys(["terayear",     "terayears", "tya", "tyr"], 31_556_925_216_000_000_000.00),  # 1E12 solar years
    **dict.fromkeys(["fortnight",    "fortnights"],                               1_209_600.00),  # 2 weeks = 604_800 * 2 seconds
    **dict.fromkeys(["decasecond",   "decaseconds",   "das"], 1E01),
    **dict.fromkeys(["hectosecond",  "hectoseconds",  "hs"],  1E02),
    **dict.fromkeys(["kilosecond",   "kiloseconds",   "ks"],  1E03),
    **dict.fromkeys(["megasecond",   "megaseconds"],          1E06),  # no Ms because .casefold() would convert it to ms
    **dict.fromkeys(["gigasecond",   "gigaseconds",   "gs"],  1E09),
    **dict.fromkeys(["terasecond",   "teraseconds",   "ts"],  1E12),
    **dict.fromkeys(["petasecond",   "petaseconds"],          1E15),  # no Ps because .casefold() would convert it to ps
    **dict.fromkeys(["exasecond",    "exaseconds",    "es"],  1E18),
    **dict.fromkeys(["zettasecond",  "zettaseconds"],         1E21),  # no Zs because .casefold() would convert it to zs
    **dict.fromkeys(["yottasecond",  "yottaseconds"],         1E24),  # no Ys because .casefold() would convert it to ys
    **dict.fromkeys(["ronnasecond",  "ronnaseconds",  "rs"],  1E27),
    **dict.fromkeys(["quettasecond", "quettaseconds", "qs"],  1E30),
}


def seconds_in_unit(unit: str) -> float:
    """Return the number of seconds in a given time unit."""
    try:
        return _UNIT_SECONDS[unit.casefold()]
    except KeyError:
        raise ValueError(f"Unknown time unit: {unit!r}")


# Common US & UTC/GMT abbreviations → IANA zone names
_TZ_ABBREV_TO_ZONE: dict[str, str] = {
    "UTC"  : "UTC",
    "GMT"  : "Etc/GMT",
    "EST"  : "America/New_York",
    "EDT"  : "America/New_York",
    "CST"  : "America/Chicago",  # WARNING! "CST" can also mean China Standard Time (Asia/Shanghai, UTC+8), so use with caution!
    "CDT"  : "America/Chicago",
    "MST"  : "America/Denver",
    "MDT"  : "America/Denver",
    "PST"  : "America/Los_Angeles",
    "PDT"  : "America/Los_Angeles",
    "HST"  : "Pacific/Honolulu",
    "AKST" : "America/Anchorage",
    "AKDT" : "America/Anchorage",
    "AST"  : "America/Puerto_Rico",  # Atlantic Standard Time
    "ADT"  : "America/Puerto_Rico",  # Atlantic Daylight Time
    "NST"  : "America/St_Johns",     # Newfoundland Standard Time
    "NDT"  : "America/St_Johns",     # Newfoundland Daylight Time
    "BST"  : "Europe/London",        # British Summer Time
    "CET"  : "Europe/Berlin",        # Central European Time
    "CEST" : "Europe/Berlin",        # Central European Summer Time
    "EET"  : "Europe/Athens",        # Eastern European Time
    "EEST" : "Europe/Athens",        # Eastern European Summer Time
    "IST"  : "Asia/Kolkata",         # Indian Standard Time - WARNING! "IST" can also mean Irish Standard Time (Europe/Dublin, UTC+1), so use with caution!
    "JST"  : "Asia/Tokyo",           # Japan Standard Time
    "KST"  : "Asia/Seoul",           # Korea Standard Time
    "HKT"  : "Asia/Hong_Kong",       # Hong Kong Time
    "SGT"  : "Asia/Singapore",       # Singapore Time
    "AEST" : "Australia/Sydney",     # Australian Eastern Standard Time
    "AEDT" : "Australia/Sydney",     # Australian Eastern Daylight Time
    "ACST" : "Australia/Adelaide",   # Australian Central Standard Time
    "ACDT" : "Australia/Adelaide",   # Australian Central Daylight Time
    "AWST" : "Australia/Perth",      # Australian Western Standard Time
    "AWDT" : "Australia/Perth",      # Australian Western Daylight Time
    "NZT"  : "Pacific/Auckland",     # New Zealand Time
    "NZST" : "Pacific/Auckland",     # New Zealand Standard Time
    "NZDT" : "Pacific/Auckland",     # New Zealand Daylight Time
    "WET"  : "Europe/Lisbon",        # Western European Time
    "WEST" : "Europe/Lisbon",        # Western European Summer Time
    # ...add any others you need
}

# Pre‐compile once for all calls.
_TZ_OFFSET_RE: re.Pattern = re.compile(r'''
    ^(?P<sign>[+-])
    (?:
        (?P<hours1>\d{1,2})[hH](?P<mins1>\d{1,2})(?:[mM])?  # +5h30m
      | (?P<hours1_only>\d{1,2})[hH]                        # +5h
      | (?P<hours2>\d{1,2}):(?P<mins2>\d{2})                # +5:30
      | (?P<hours3>\d{1,2})(?P<mins3>\d{2})                 # +0530
      | (?P<hours4>\d{1,2})                                 # +5
    )
    $
''', re.VERBOSE)


def parse_timezone(tz_arg: str | dt.tzinfo | None = None) -> dt.tzinfo | str:
    """
    Parse the given timezone string or tzinfo object into a datetime.tzinfo object.
    If tz_arg is None, return UTC timezone.
    If tz_arg is a string, it can be in one of the following formats:
      - A fixed‐offset like: "+HH:MM", "+HHMM", "+H", "+Hh", "+HhMMm" (or minus variants).
         Examples: "+05:30", "-0530", "+5h", "-5h30m".
      - A string that can be converted to a ZoneInfo object (e.g. 'America/New_York').
      - A timezone abbreviation that maps to a known IANA zone name (e.g. 'EST', 'CET').
      - "Z", "UTC", or "GMT" (case‐insensitive) to represent UTC.
      - A string "Naive" to represent a naive datetime (no timezone).
    If tz_arg is already a tzinfo object, return it as is.

    Args:
        tz_arg : A timezone string, a datetime.tzinfo object, or None.

    Returns:
        A datetime.tzinfo object representing the parsed timezone, or a string "Naive"
        if the input was "Naive".

    Raises:
        ValueError if the string cannot be converted to a valid timezone.
    """

    import datetime as dt

    # If tz_arg is None, return UTC timezone
    if tz_arg is None:
        return dt.timezone.utc

    # If tz_arg is already a tzinfo object, return it unchanged
    if isinstance(tz_arg, dt.tzinfo):
        return tz_arg

    # If tz_arg is a string, try to parse it
    if isinstance(tz_arg, str):
        s = tz_arg.strip()
        up = s.upper()

        # Handle "Naive" case
        if up == "NAIVE":
            return tz_arg

        # Bare UTC/GMT/Z
        if up in ("Z", "UTC", "GMT") and len(s) <= 3:
            return dt.timezone.utc

        # Strip leading "UTC" or "GMT" prefix
        if up.startswith(("UTC", "GMT")):
            rest = s[3:].strip()
            if rest == "":
                return dt.timezone.utc
            s = rest  # now s begins with + or -

        # Try fixed-offset patterns
        m = _TZ_OFFSET_RE.fullmatch(s)
        if m:
            sign = 1 if m.group("sign") == "+" else -1

            if m.group("hours1") is not None:
                hours   = int(m.group("hours1"))
                minutes = int(m.group("mins1"))
            elif m.group("hours1_only") is not None:
                hours   = int(m.group("hours1_only"))
                minutes = 0
            elif m.group("hours2") is not None:
                hours   = int(m.group("hours2"))
                minutes = int(m.group("mins2"))
            elif m.group("hours3") is not None:
                hours   = int(m.group("hours3"))
                minutes = int(m.group("mins3"))
            else:
                hours   = int(m.group("hours4"))
                minutes = 0

            offset = dt.timedelta(hours=hours, minutes=minutes) * sign
            return dt.timezone(offset)

        # Otherwise, fall back to ZoneInfo
        try:
            from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
        except ImportError:  # for Python < 3.9, fall back to backports.zoneinfo
            from backports.zoneinfo import ZoneInfo, ZoneInfoNotFoundError

        # Try to interpret the string as a timezone abbreviation
        if up in _TZ_ABBREV_TO_ZONE:
            zone_name = _TZ_ABBREV_TO_ZONE[up]
            return ZoneInfo(zone_name)

        # Try to interpret the string as a ZoneInfo name
        try:
            return ZoneInfo(tz_arg)
        except ZoneInfoNotFoundError as e:
            raise ValueError(f"Unknown timezone {tz_arg!r}: {e}") from e

    raise TypeError(f"Expected None, str, or tzinfo; got {type(tz_arg).__name__!r}")


def decimal_year_to_datetime(dec: float, use_astropy: bool = False) -> dt.datetime:
    """
    Convert a decimal year to a datetime object.
    If use_astropy is True, astropy.time is used for sub-second and leap-second–aware conversion.
    Usage: new_datetime_datetime_object = decimal_year_to_datetime(2002.291)
    """
    import datetime as dt
    if use_astropy:
        try:
            from astropy.time import Time
        except ImportError as e:
            raise ValueError(f"'use_astropy=True' requires the astropy package: {e}") from e
        t = Time(dec, format="jyear", scale="utc")
        return t.to_datetime().replace(tzinfo=dt.timezone.utc)

    try:
        year = int(dec)
        rem = dec - year
        start_dt = dt.datetime(year,     1, 1, tzinfo=dt.timezone.utc)
        end_dt   = dt.datetime(year + 1, 1, 1, tzinfo=dt.timezone.utc)
        year_secs = (end_dt - start_dt).total_seconds()
        return start_dt + dt.timedelta(seconds=rem * year_secs)
    except ValueError as e:
        raise ValueError(f"Failed to convert decimal year {dec} to datetime: {e}") from e


def _parse_iso(given_date: str) -> dt.datetime:
    """Parse an ISO8601 date string and return a datetime object. Raises ValueError if the date string is invalid."""
    from dateutil.parser import isoparse, ParserError

    try:
        return isoparse(given_date)
    except ParserError as e:
        raise ValueError(f"Invalid ISO8601 date '{given_date}': {e}") from e


def is_float(s: str) -> bool:
    """Check if a string can be parsed as a float."""
    try:
        float(s)
        return True
    except ValueError:
        return False


# Precompile Julian/MJD regex
# This regex is just used to check if a string looks like a JD or MJD:
_JD_MJD_SIMPLE_RE: re.Pattern  = re.compile(r"\s*(JD|MJD)?\s*[+-]?\d+(\.\d+)?\s*", re.IGNORECASE)
# This regex is used to capture the prefix (JD or MJD) and the value from a string that looks like a JD or MJD:
_JD_MJD_CAPTURE_RE: re.Pattern = re.compile(r"\s*(?P<prefix>JD|MJD)?\s*(?P<value>[+-]?\d+(?:\.\d+)?)\s*", re.IGNORECASE)
# This regex is used to check if a string has an explicit offset or Z at the end (indicating that the date should be converted by shifting the clock):
_OFFSET_IN_STR_RE: re.Pattern  = re.compile(r"(Z|[+-]\d{2}:\d{2}|[+-]\d{4})$")

# Enclose the type alias annotation in quotes because not all of these types have been imported yet.
AnyDateTimeType: TypeAlias = "str | float | int | np.datetime64 | pd.Timestamp | dt.datetime"


def _should_convert(given_date: AnyDateTimeType, format_str: str | None = None) -> bool:
    """Determine if the given date should be converted to a timezone (i.e. if the wall clock should be shifted) or if the timezone should just be attached without shifting the clock."""
    import datetime as dt

    # 1) Numbers, JD/MJD, decimal years, special keywords
    if isinstance(given_date, (int, float)) and not isinstance(given_date, bool):
        logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("Given date is a number: %s, so it will be converted by shifting the clock", given_date)
        return True
    if isinstance(given_date, str):
        u = given_date.strip().upper()
        if u in ("J2000", "UNIX", "NOW"):
            logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("Given date is a special keyword: %s, so it will be converted by shifting the clock", u)
            return True
        if format_str and format_str.upper() in ("JD", "MJD"):
            logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("Given date has a format_str: %s, so it will be converted by shifting the clock", format_str)
            return True
        if _JD_MJD_SIMPLE_RE.fullmatch(given_date):
            logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("Given date is a JD/MJD: %s, so it will be converted by shifting the clock", given_date)
            return True
        # explicit offset or Z
        if _OFFSET_IN_STR_RE.search(given_date):
            logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("Given date has an explicit offset or Z: %s, so it will be converted by shifting the clock", given_date)
            return True
    # 2) Any datetime/timestamp already aware
    if isinstance(given_date, dt.datetime) and given_date.tzinfo is not None:
        logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("Given date is an aware datetime: %s, so it will be converted by shifting the clock", given_date)
        return True

    # Otherwise treat it as local‐time → attach only
    logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("Given date is not a number, JD/MJD, or aware datetime: %s, so the timezone will be attached without shifting the clock", given_date)
    return False


def _finalize_datetime(parsed_dt: dt.datetime, original_input: AnyDateTimeType,
                       format_str: str | None, tz_arg: str | dt.tzinfo | None,
                       should_convert: bool | None = None) -> dt.datetime:
    """
    Finalize the datetime object by either converting it to the target timezone or just attaching the timezone without shifting the clock. The boolean argument 'should_convert' can override the default behavior, which is determined by the function _should_convert().

    Args:
        parsed_dt:      The datetime object that has been parsed from the original input.
        original_input: The original input that was used to parse the datetime.
        format_str:     The format string used to parse the datetime, if any.
        tz_arg:         The timezone argument, which can be a string or a datetime.tzinfo object.
        should_convert: A boolean indicating whether to convert the datetime to the specified timezone by shifting the clock (True) or just attaching the timezone without shifting (False). If None, the function will determine this based on the type of original_input and format_str.

    Returns:
        A datetime.datetime object in the specified timezone.
        If tz_arg is "Naive", the datetime will be returned without any timezone info.
        If should_convert is True, the datetime will be converted to the specified timezone by shifting the clock.
        If should_convert is False, the timezone will be attached to the datetime without shifting the clock.
        If should_convert is None, the function will determine whether to convert or not based on the type of original_input and format_str.

    Raises:
        ValueError: If the tz_arg is not a valid timezone string or tzinfo object.
        TypeError:  If the parsed_dt is not a datetime.datetime object.
    """
    if isinstance(tz_arg, str) and tz_arg.strip().upper() == "NAIVE":
        logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("Naive timezone requested, returning datetime %s without any timezone info", parsed_dt)
        return parsed_dt.replace(tzinfo=None)
    target_tz = parse_timezone(tz_arg)
    if should_convert is not False and (_should_convert(original_input, format_str) or should_convert is True):
        logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("Converting datetime %s to timezone %s by shifting the clock", parsed_dt, target_tz)
        return parsed_dt.astimezone(target_tz)
    else:
        logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("Attaching timezone %s to datetime %s without shifting the clock", target_tz, parsed_dt)
        return parsed_dt.replace(tzinfo=target_tz)


def parse_datetime(given_date: AnyDateTimeType, timezone: str | dt.tzinfo | None = None,
                   format_str: str | None = None,
                   should_convert: bool | None = None) -> dt.datetime:
    """
    Try parsing the given_date string or number into a datetime.datetime object in the specified timezone.

    If "format_str" is provided, it will be used to parse the date string. These format types are accepted:
     - "seconds" or "milliseconds" indicating the number of seconds or milliseconds since an epoch (Unix epoch by default).
     - "YYYY-MM-DD" or similar ISO8601 formats such as "YYYY-MM-DDTHH:MM:SS", "MM/DD/YYYY", etc.
     - A custom string following this pattern: "units (optional: since/after epoch)", where "units" can be anything that the function seconds_in_unit() accepts (e.g. "days", "weeks", "months", etc.). The optional epoch time can be a string, float, int, numpy.datetime64, pandas.Timestamp, or datetime.datetime object. Example: "days since 1990", "milliseconds after J2000", "sidereal days since 2000-01-01", etc. If the epoch is not specified, it defaults to the Unix epoch (1970-01-01T00:00:00Z)

    If a boolean "should_convert" is provided, it will override the default behavior of whether to convert the datetime to the specified timezone by shifting the clock or just attaching the timezone without shifting. If None, the function will determine this based on the type of given_date and format_str.

    If a given_date starts with "JD" or "MJD", it will be treated as a Julian Date or Modified Julian Date, respectively.

    Otherwise, if given_date is a float or int, treat it as a decimal year by default if format_str is not provided.

    Any call that doesn't provide a timezone argument will default to UTC.
    The timezone can be a datetime.tzinfo object or a string that can be converted to a ZoneInfo object (e.g. 'America/New_York').
    If the given_date is an "aware" datetime.datetime object which already has a timezone attached, it will be converted to the specified timezone (which may involve changing its date and time if the specified timezone is different).
    The timezone can also be a fixed‐offset like "+05:30" or "-04:00", or the string "Naive" to indicate that the datetime should be treated as a naive datetime (i.e. without any timezone information).

    Accepts:
        'NOW' (case-insensitive) → current datetime
        strings in YYYY, YYYY-MM, YYYY-MM-DD, YYYY-MM-DDTHH:MM:SS, or other ISO8601 formats (e.g. '2002-10-18T07:00:00Z', '2002-10-18 07:00:00+00:00').
        If YYYY is provided, it will default to January 1st of that year at midnight.
        If YYYY-MM is provided, it will default to the first day of that month at midnight.
        If YYYY-MM-DD is provided, it will default to midnight on that day.
        fallback to dateutil.parser.parse for free-form strings ("18 Oct 2002", "March 5th, 2020", etc.)
        floats (e.g. 2002.29178082191777) or integer (e.g. 2002) → decimal year
        numpy.datetime64 objects (e.g. np.datetime64('2002-10-18T07:00:00'))
        pandas.Timestamp objects (e.g. pd.Timestamp('2002-10-18 07:00:00'))
        datetime.datetime objects (e.g. datetime.datetime(2002, 10, 18, 7, 0, 0))

    Args:
        given_date:     The date to parse, which can be a string, float, int, numpy.datetime64,
                        pandas.Timestamp, or datetime.datetime object.
        timezone:       A string or datetime.tzinfo object representing the timezone to convert
                        the datetime to. If None, defaults to UTC.
        format_str:     A string indicating the format of the date. If None, the function will
                        try to infer the format from the given_date.
        should_convert: A boolean indicating whether to convert the datetime to the specified
                        timezone by shifting the clock (True) or just attaching the timezone
                        without shifting (False). If None, the function will determine this
                        based on the type of given_date and format_str.

    Returns:
        datetime.datetime object in the specified timezone.
        Note that datetime.datetime objects cannot represent dates before 1 January 1, 0001 or after 31 December 9999.
        So dates outside this range will raise a ValueError. Future versions of this code may support a wider range of dates (like 44 BC, 44 BCE, etc.) using libraries like 'astropy.time': https://chatgpt.com/share/685c5157-5cac-8006-b68c-4a0731927a50
        However, this will require the function to return an 'astropy.time.Time' object instead of a 'datetime.datetime' object.

    Raises:
        ValueError:  If the given_date cannot be parsed into a datetime object, or if the timezone is invalid.
        TypeError:   If the given_date is not a string, float, int, numpy.datetime64, pandas.Timestamp, or datetime.datetime object.
        ImportError: If the 'jdcal' library is not installed and the given_date is a Julian Date or Modified Julian Date.
    """
    import datetime as dt
    fallback_logging_config()  # Ensure logging is configured

    parsed_tz = parse_timezone(timezone)  # Ensure timezone is a valid tzinfo object or string

    parsed_dt = None

    # Handle special cases:
    if isinstance(given_date, str):
        if given_date.strip().upper() == "J2000":
            # J2000 is January 1, 2000, 11:58:55.816 UTC
            parsed_dt = dt.datetime(2000, 1, 1, 11, 58, 55, 816_000, tzinfo=dt.timezone.utc)
        if given_date.strip().upper() == "UNIX":
            # UNIX epoch is January 1, 1970, 00:00:00 UTC
            parsed_dt = dt.datetime(1970, 1, 1, tzinfo=dt.timezone.utc)
        if given_date.strip().upper() == "NOW":
            parsed_dt = dt.datetime.now(tz=dt.timezone.utc)

    # Handle forced or explicit Julian Date (JD) or Modified Julian Date (MJD)
    m = None
    prefix = None
    if parsed_dt is None and isinstance(given_date, str):
        m = _JD_MJD_CAPTURE_RE.fullmatch(given_date)
        if m:
            prefix = m.group("prefix")

    # Trigger JD/MJD branch only if format_str equals "JD" or "MJD", or prefix was provided
    if parsed_dt is None and (prefix is not None or (format_str and (format_str.upper() == "JD" or format_str.upper() == "MJD"))):

        try:
            import jdcal
        except ImportError:
            raise ImportError("The jdcal python library is required to parse Julian/MJD dates")

        # Determine raw value
        if isinstance(given_date, (int, float)):
            value = float(given_date)
        else:
            value = float(m.group("value"))

        # Determine if MJD conversion needed
        use_mjd = bool((format_str and format_str.upper() == "MJD") or (prefix and prefix.upper() == "MJD"))

        # Convert MJD to JD if necessary
        jd_val = value + (2_400_000.5 if use_mjd else 0.0)

        # Split into integer day and fraction
        int_part                   = int(jd_val)
        frac_part                  = jd_val - int_part
        year, month, day, day_frac = jdcal.jd2gcal(int_part, frac_part)

        # Convert day fraction to hours, minutes, seconds, microseconds
        day_int     = int(day)
        frac_of_day = (day + day_frac) - day_int
        hours       = int(frac_of_day * 24)
        mins        = int((frac_of_day * 24 - hours) * 60)
        secs_frac   = (frac_of_day * 24 - hours) * 60 - mins
        secs        = int(secs_frac * 60)
        micros      = int((secs_frac * 60 - secs) * 1e6)
        parsed_dt   = dt.datetime(year, month, day_int, hours, mins, secs, micros, tzinfo=dt.timezone.utc)

    # Check if the given_date is a string that can be parsed as a float
    if parsed_dt is None and isinstance(given_date, str) and is_float(given_date):
        given_date = float(given_date)  # Convert string to float if it represents a number
    # Check if the given_date is a float or int but NOT a boolean
    if parsed_dt is None and isinstance(given_date, (int, float)) and not isinstance(given_date, bool):
        if format_str is None:
            # If the given_date is a decimal year, convert it to datetime in the specified timezone
            # Note: This will not shift the clock, just attach the tzinfo.
            parsed_dt = decimal_year_to_datetime(float(given_date))
        else:  # If format is provided, parse the date using the specified format.
            if not isinstance(format_str, str):
                raise TypeError(f"Expected 'format' to be a string, got {type(format_str).__name__!r}")
            # Make sure the format string is a valid example of "units (optionally: since/after epoch)"
            # Try to split by since or after, whichever works:
            format_parts = re.split(r'\s+(since|after)\s+', format_str, maxsplit=1)
            logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("Parsing date with format string: '%s' split into parts: %s", format_str, format_parts)
            if len(format_parts) > 3:
                raise ValueError(f"Invalid format string: '{format_str}'. Expected at most three parts: 'units', 'since/after', and 'epoch'.")
            # The first part should be acceptable by seconds_in_unit():
            try:
                units      = format_parts[0].strip()
                multiplier = seconds_in_unit(units)  # This will raise ValueError if the unit is unknown
            except ValueError as e:
                raise ValueError(f"Invalid time unit '{units}' in format string '{format_str}': {e}") from e
            # If the format_parts list has only one part, it means the epoch defaults to the Unix epoch (1970-01-01T00:00:00Z).
            if len(format_parts) == 1:
                # If the format_parts list has only one part, it means the format is just "units" (e.g. "days", "weeks", etc.)
                # In this case, we assume the epoch is the Unix epoch (1970-01-01T00:00:00Z).
                epoch_str = "1970-01-01T00:00:00Z"
            else:
                # If the format_parts list has three parts, the third part is the epoch.
                epoch_str = format_parts[2].strip()
            try:
                epoch = parse_datetime(epoch_str, timezone=parsed_tz)
            except ValueError as e:
                raise ValueError(f"Invalid epoch '{epoch}' in format string '{format_str}': {e}") from e
            # Now we can calculate the datetime based on the given_date (and the multiplier from 'units') and the epoch
            parsed_dt = epoch + dt.timedelta(seconds=float(given_date) * multiplier)

    if parsed_dt is None and type(given_date) is dt.datetime:  # Don't use isinstance() here, because it will also match subclasses like Pandas Timestamp
        parsed_dt = given_date
    elif isinstance(given_date, dt.date):  # Handle date objects (without time) as midnight
        parsed_dt = dt.datetime.combine(given_date, dt.time.min)

    if parsed_dt is None:
        try:
            import numpy as np
        except ImportError:
            np = None
        if np is not None and isinstance(given_date, np.datetime64):
            ts_ns     = given_date.astype("datetime64[ns]").astype("int64")
            parsed_dt = dt.datetime.fromtimestamp(ts_ns/1e9, tz=parsed_tz)

    if parsed_dt is None:
        try:
            import pandas as pd
        except ImportError:
            pd = None
        if pd is not None and isinstance(given_date, pd.Timestamp):
            parsed_dt = given_date.to_pydatetime()

    error_message: str = f"The date '{given_date}' is type {type(given_date).__name__!r} in an unknown format. Please use NOW, YYYY, YYYY-MM, YYYY-MM-DD, YYYY-MM-DDTHH:MM:SS, other ISO8601 strings, or a decimal year like 2002.291. Datetimes in pandas.Timestamp, numpy.datetime64, or datetime.datetime formats are also accepted and will be converted to datetime.datetime objects in the specified timezone ({parsed_tz})."

    if parsed_dt is None and not isinstance(given_date, str):
        raise TypeError(error_message)

    if parsed_dt is None and format_str is not None:
        try:
            parsed_dt = dt.datetime.strptime(given_date, format_str)
        except ValueError as e:
            raise ValueError(f"Invalid date format '{given_date}' with specified format '{format_str}': {e}") from e

    # Try parsing the date string in various formats
    # Start with RFC 2822 format, then ISO8601, then free-form strings
    # Store any errors encountered in a list to provide feedback if all parsing attempts fail.
    errors: list[str] = []

    if parsed_dt is None:
        import email.utils
        try:
            # parses "Tue, 25 Jun 2025 14:00:00 GMT"
            parsed_dt = email.utils.parsedate_to_datetime(given_date)
        except (TypeError, ValueError) as e:
            errors.append(f"Failed to parse '{given_date}' as an RFC 2822 date: {e}")

    if parsed_dt is None:
        try:
            parsed_dt = _parse_iso(given_date)
        except ValueError as e:
            errors.append(f"Failed to parse '{given_date}' as an ISO8601 date: {e}")

    if parsed_dt is None:
        try:
            from dateutil.parser import parse as parse_fuzzy
            parsed_dt = parse_fuzzy(given_date, default=dt.datetime(1900, 1, 1))
        except ValueError as e:
            errors.append(f"Failed to parse '{given_date}' as a free-form date string: {e}")

    if parsed_dt is None:
        if np is None:
            errors.append("The numpy package is not installed, so numpy.datetime64 objects cannot be parsed.")
        if pd is None:
            errors.append("The pandas package is not installed, so pandas.Timestamp objects cannot be parsed.")
    else:
        # Finalize the datetime object by converting it to the target timezone or just attaching the timezone without shifting the clock
        return _finalize_datetime(parsed_dt, given_date, format_str, parsed_tz, should_convert)

    raise ValueError(error_message + "\n".join(map(str, errors)) + "\nPlease check the input format and try again.")


def to_jsonable(obj: Any, *, roundtrip: bool = True) -> Any:
    """
    Convert arbitrary Python objects into JSON-serializable primitives.
    If roundtrip=True, non-JSON types are wrapped with a small type tag so they can be reconstructed.
    """
    return _to_jsonable(obj, roundtrip=roundtrip, _seen=set())


def _to_jsonable(obj: Any, *, roundtrip: bool, _seen: set[int]) -> Any:
    """
    Internal helper to convert arbitrary Python objects into JSON-serializable primitives.
    If roundtrip=True, non-JSON types are wrapped with a small type tag so they can be reconstructed.
    (Helper exists to avoid exposing the _seen set in the public API.)
    """
    # Fast-path primitives
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    # Dict
    if isinstance(obj, dict):
        oid = id(obj)
        if oid in _seen:
            return {"__type__": "recursion"}
        _seen.add(oid)
        try:
            return {str(k): _to_jsonable(v, roundtrip=roundtrip, _seen=_seen) for k, v in obj.items()}
        finally:
            _seen.discard(oid)
    # List
    if isinstance(obj, list):
        oid = id(obj)
        if oid in _seen:
            return {"__type__": "recursion"}
        _seen.add(oid)
        try:
            return [_to_jsonable(x, roundtrip=roundtrip, _seen=_seen) for x in obj]
        finally:
            _seen.discard(oid)
    # Tuple
    if isinstance(obj, tuple):
        oid = id(obj)
        if oid in _seen:
            return {"__type__": "recursion"}
        _seen.add(oid)
        try:
            seq = [_to_jsonable(x, roundtrip=roundtrip, _seen=_seen) for x in obj]
        finally:
            _seen.discard(oid)
        return {"__type__": "tuple", "value": seq} if roundtrip else list(seq)
    # Set / Frozenset
    if isinstance(obj, (set, frozenset)):
        oid = id(obj)
        if oid in _seen:
            return {"__type__": "recursion"}
        _seen.add(oid)
        try:
            seq = [_to_jsonable(x, roundtrip=roundtrip, _seen=_seen) for x in obj]
        finally:
            _seen.discard(oid)
        tag = "frozenset" if isinstance(obj, frozenset) else "set"
        return {"__type__": tag, "value": seq} if roundtrip else list(seq)
    # Path
    if isinstance(obj, Path):
        s = obj.as_posix()
        return {"__type__": "path", "value": s} if roundtrip else s
    # Enum
    if isinstance(obj, Enum):
        # Store module+qualname so we *can* reconstruct if the Enum is importable.
        cls = obj.__class__
        return {
            "__type__" : "enum",
            "module"   : cls.__module__,
            "qualname" : getattr(cls, "__qualname__", cls.__name__),
            "name"     : obj.name,
        } if roundtrip else (obj.value if isinstance(obj.value, (str, int, float, bool, type(None))) else obj.name)
    # argparse.Namespace
    try:
        import argparse
        if isinstance(obj, argparse.Namespace):
            return {"__type__" : "namespace",
                    "value"    : _to_jsonable(vars(obj), roundtrip=roundtrip, _seen=_seen)} if roundtrip else vars(obj)
    except Exception:
        pass
    # datetime / date / time
    try:
        import datetime as dt
        if isinstance(obj, (dt.datetime, dt.date, dt.time)):
            iso = obj.isoformat()
            which = "datetime" if isinstance(obj, dt.datetime) else ("date" if isinstance(obj, dt.date) else "time")
            return {"__type__": which, "value": iso} if roundtrip else iso
    except Exception:
        pass
    # Decimal
    try:
        from decimal import Decimal
        if isinstance(obj, Decimal):
            return {"__type__": "decimal", "value": str(obj)} if roundtrip else float(obj)
    except Exception:
        pass
    # bytes-like
    if isinstance(obj, (bytes, bytearray, memoryview)):
        try:
            import base64
            b64  = base64.b64encode(bytes(obj)).decode("ascii")
            kind = "bytes" if isinstance(obj, bytes) else ("bytearray" if isinstance(obj, bytearray) else "memoryview")
            return {"__type__": kind, "value": b64} if roundtrip else b64
        except Exception:
            return str(obj)
    # re.Pattern (compiled regex)
    try:
        import re
        if isinstance(obj, re.Pattern):
            return {"__type__": "re_pattern", "pattern": obj.pattern, "flags": obj.flags} if roundtrip else obj.pattern
    except Exception:
        pass
    # Fallback
    stringified = str(obj)
    logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("Object of type %s is not JSON serializable; converting to string: %s", type(obj).__name__, stringified)
    return stringified if not roundtrip else {"__type__": "object", "value": stringified}


def from_jsonable(obj: Any) -> Any:
    """
    Reconstruct objects encoded with to_jsonable(..., roundtrip=True).
    If input was produced with roundtrip=False, this mostly passes values through.
    """
    # Lists first
    if isinstance(obj, list):
        return [from_jsonable(x) for x in obj]
    # Primitives / not dict
    if not isinstance(obj, dict):
        return obj

    t = obj.get("__type__")
    if not t:
        return {k: from_jsonable(v) for k, v in obj.items()}

    # Known tags
    if t == "path":
        return Path(obj["value"])
    if t == "tuple":
        return tuple(from_jsonable(x) for x in obj.get("value", []))
    if t == "set":
        return set(from_jsonable(x) for x in obj.get("value", []))
    if t == "frozenset":
        return frozenset(from_jsonable(x) for x in obj.get("value", []))
    if t == "namespace":
        try:
            import argparse
            return argparse.Namespace(**from_jsonable(obj.get("value", {})))
        except Exception:
            return from_jsonable(obj.get("value", {}))
    if t == "enum":
        # Best effort: import the Enum class and get member by name; else return the name.
        try:
            import importlib
            mod   = importlib.import_module(obj["module"])
            parts = obj["qualname"].split(".")
            cls   = mod
            for p in parts:
                cls = getattr(cls, p)
            return getattr(cls, obj["name"])
        except Exception:
            return obj.get("name")
    if t == "datetime":
        import datetime as dt
        return dt.datetime.fromisoformat(obj.get("value"))
    if t == "date":
        import datetime as dt
        return dt.date.fromisoformat(obj.get("value"))
    if t == "time":
        import datetime as dt
        return dt.time.fromisoformat(obj.get("value"))
    if t == "decimal":
        try:
            from decimal import Decimal
            return Decimal(obj.get("value", "0"))
        except Exception:
            return obj.get("value")
    if t == "bytes":
        try:
            import base64
            return base64.b64decode(obj.get("value", "").encode("ascii"))
        except Exception:
            return obj.get("value")
    if t == "bytearray":
        try:
            import base64
            return bytearray(base64.b64decode(obj.get("value", "").encode("ascii")))
        except Exception:
            return obj.get("value")
    if t == "memoryview":
        try:
            import base64
            return memoryview(base64.b64decode(obj.get("value", "").encode("ascii")))
        except Exception:
            return obj.get("value")
    if t == "recursion":
        return "<recursion>"
    if t == "object":
        return obj.get("value")
    if t == "re_pattern":
        import re
        return re.compile(obj.get("pattern", ""), obj.get("flags", 0))
    # Unknown tag → decode inner content if any
    return {k: from_jsonable(v) for k, v in obj.items()}


def _coerce_log_mode(value: Any) -> int:
    """Accept old string values like 'INFO' (or '20') and return an int."""
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        s = value.strip()
        # Handle numeric strings like "20"
        try:
            return int(s)
        except ValueError:
            pass
        # Handle level names like "INFO", "debug", etc. (case-insensitive)
        value_map = {"INFO"     : logging.INFO,
                     "DEBUG"    : logging.DEBUG,
                     "WARNING"  : logging.WARNING,
                     "WARN"     : logging.WARNING,
                     "ERROR"    : logging.ERROR,
                     "CRITICAL" : logging.CRITICAL}
        lvl = value_map.get(s.upper())
        # lvl = logging.getLevelName(s.upper())  # deprecated
        if isinstance(lvl, int):
            return lvl
    logging.warning("Unrecognized log_mode %r; defaulting to INFO", value)
    return logging.INFO


def save_options_to_json(options: Options) -> None:
    """
    Save the options object to a JSON file.

    Args:
        options: Options object containing:
            - script_dir:    Directory where the JSON file will be saved.
            - python_script: Name of the Python script (used in the JSON filename).
            - my_name:       Name of the current script (used in the JSON filename).
            - timestamp:     Current timestamp (used in the JSON filename).

    Returns:
        None - writes the options to a JSON file.

    Raises:
        IOError:    If there is an error writing to the file.
        ValueError: If the options object is invalid.
    """
    import json
    options.options_json_filepath = options.script_dir / f".{options.python_script.name}-{options.my_name}-last-used-on-{options.timestamp}.json"
    options.options_json_filepath.parent.mkdir(parents=True, exist_ok=True)

    options_dict = options.__dict__.copy()  # Convert options to a dictionary and handle sets
    payload      = to_jsonable(options_dict, roundtrip=True)  # tag for safe round-trip

    # Write the dictionary to a JSON file (ensure_ascii=False to preserve non-ASCII characters)
    with open(options.options_json_filepath, "w", encoding=DEFAULT_ENCODING) as json_file:
        json.dump(payload, json_file, indent=4, ensure_ascii=False)

    logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("Options saved to JSON file: %s",
                                                                      os.fspath(options.options_json_filepath))


def load_options_from_json(options: Options, json_file: str | os.PathLike[str]) -> Options | None:
    """
    Load the options object from a JSON file.

    Args:
        options:    An existing Options object (used for logging purposes).
        json_file:  Path to the JSON file to load.

    Returns:
        Options object loaded from the JSON file, or None if the file does not exist or cannot be read.

    Raises:
        IOError:    If there is an error reading the file.
        ValueError: If the JSON file is invalid or cannot be parsed.
    """
    import json
    import copy
    json_file = ensure_file(json_file)
    with open(json_file, "r", encoding=DEFAULT_ENCODING) as file:
        raw = json.load(file)

    options_dict = from_jsonable(raw)  # reconstruct tagged types

    # Backwards compatibility: coerce old string log levels to ints
    if "log_mode" in options_dict:
        options_dict["log_mode"] = _coerce_log_mode(options_dict["log_mode"])

    # Create a new Options object and set attributes from the dictionary
    options_FROM_JSON = copy.deepcopy(Options())  # Just in case.
    for key, value in options_dict.items():
        setattr(options_FROM_JSON, key, value)
    if not options.rawlog: logging.info("options loaded from %s", os.fspath(json_file))
    return options_FROM_JSON


def sci_exp(x: float | int, max_digits: int = 15) -> int:
    """Return floor(log10(|x|)), clamped to -max_digits for very small |x|.
    For x == 0, returns -max_digits.
    """
    import math
    if not isinstance(x, (int, float)) or isinstance(x, bool):
        raise TypeError("x must be an int or float (not bool)")
    if not math.isfinite(x):
        raise ValueError("x must be finite")
    if x == 0:
        return -max_digits
    exp = int(math.floor(math.log10(abs(x))))
    return max(exp, -max_digits)


def round_out(x: float, round_digits: int = 3, max_digits: int = 15) -> float:
    """
    Round a number away from zero (i.e. rounds up for x>0 and down for x<0) to
    the specified number of significant figures (defaults to 3).
    If the number is smaller than 10^(-max_digits), it will be returned as is.
    The max_digits parameter defaults to 15, but can be changed to a different value if needed.

    Args:
        x:             The number to round.
        round_digits:  The number of significant figures to round to (default is 3).
        max_digits:    The maximum number of digits to consider for very small numbers (default is 15).

    Returns:
        float: The rounded number, or the original number if it is smaller than 10^(-max_digits).
    """
    import numpy as np
    if np.abs(x) < 10**(-max_digits): return x
    these_digits = sci_exp(x) - round_digits + 1
    thisfactor = 10**these_digits
    x = x/thisfactor
    if x > 0: x = np.ceil(x)
    else:     x = np.floor(x)
    return x*(thisfactor*1.0)


def prompt_then_confirm(prompt: str) -> bool:
    """Prompt the user with the given message and return True if the user enters 'yes', False otherwise."""
    confirmation = input(prompt)
    return confirmation.casefold() == "yes" or confirmation.casefold() == "y"


def prompt_then_choose(prompt: str, choices: list[str], default: str = None) -> str:
    """
    Show a numbered list of choices and prompt the user to select one.

    Args:
        prompt:  The message to display before the choices.
        choices: A list of choices to present to the user.
        default: The default choice to return if the user presses Enter without inputting a choice.

    Returns:
        str : The selected choice from the list (or the default if provided).

    Raises:
        None: If the user input is invalid, it will keep prompting until a valid choice is made.
    """
    fallback_logging_config()

    logging.info(prompt)
    for i, choice in enumerate(choices, 1):
        logging.info("  %d) %s", i, choice)
    prompt = f"Select [1-{len(choices)}]"
    if default is not None:
        prompt += f" (default {default}): "
    else:
        prompt += ": "

    while True:
        ans = input(prompt).strip()
        if not ans and default:
            logging.info("No input provided, using default: %s", default)
            return default
        if ans.isdigit() and 1 <= int(ans) <= len(choices):
            logging.info("User selected choice %d: %s", int(ans), choices[int(ans)-1])
            return choices[int(ans)-1]
        logging.warning("Invalid choice, try again.")


def my_capitalize(string_to_capitalize: str) -> str:
    """Capitalize ONLY the first letter of a string and DON'T modify the rest of it."""
    if not string_to_capitalize:
        return ""
    return string_to_capitalize[0].upper() + string_to_capitalize[1:]


def my_title_case(the_title: str) -> str:
    """Capitalize the first letter of each word, but if a word already has ANY uppercase letters, leave it as is. This way, words like "WW2" or "iZombie" won't be modified."""
    words = the_title.split()
    capitalized_words = [word if any(letter.isupper() for letter in word)
                         else word.title() for word in words]
    return " ".join(capitalized_words)


def filename_format(text: str, sep: str = "_", max_length: int = None) -> str:
    """
    Turn arbitrary text into an ASCII-only, filesystem‐safe base filename.
    WARNING: Do not include an extension in the text, because this function
    might remove the dot which separates the filename from the extension.
    It attempts to recognize and remove extensions listed in ALL_KNOWN_EXTENSIONS
    but this list (actually, ordered tuple) is not exhaustive.

    Steps:
      1. Unicode → ASCII
      2. Recognize & remove common extensions (e.g. .txt, .fits, .tar.gz)
      3. Treat dots, underscores & whitespace as word separators
      4. Remove any character that isn't A-z, a–z, 0–9, dashes, or the separator
      5. Collapse runs of separators into a single one
      6. Trim separators from ends
      7. Optionally truncate to max_length (preserving word boundaries)
      8. If an extension was removed, append it back as the last step.

    Args:
        text:       Original filename or title
        sep:        Single-character separator (default: "_")
        max_length: If set, strongest‐effort truncate to this many chars

    Returns:
        A clean, filename-safe string.

    Raises:
        None: If the input text is None, it will return an empty string.
    """
    fallback_logging_config()  # Ensure logging is configured
    if not text:
        return ""
    # Normalize to ASCII
    try:
        import unidecode
        text = unidecode.unidecode(text)
    except ImportError:
        logging.warning("unidecode package not found, falling back to ASCII encoding.")
        # Fallback: encode to ASCII, ignore errors
        text = text.encode("ascii", "ignore").decode("ascii")

    # List of common extensions to recognize and (temporarily) remove
    removed_ext = ""
    for ext in ALL_KNOWN_EXTENSIONS:
        if text.casefold().endswith(ext):
            text = text[:-len(ext)]
            removed_ext = ext
            break

    # Replace common "word boundaries" with sep
    #    (dots, underscores, whitespace) but keep dashes
    #    e.g. "hello.world--foo_bar" → "hello world--foo bar"
    text = re.sub(r"[._\s]+", sep, text)

    # Remove anything but dashes, A-Z, a–z, 0–9, or our sep
    allowed = f"-A-Za-z0-9{re.escape(sep)}"
    text = re.sub(fr"[^{allowed}]+", "", text)

    # Collapse runs of sep (e.g. "__" → "_")
    text = re.sub(fr"{re.escape(sep)}{{2,}}", sep, text)

    # Strip leading/trailing seps
    text = text.strip(sep)

    # Optionally truncate (try not to cut in middle of a word)
    if max_length is not None and len(text) > max_length:
        # cut at max_length, then drop a partial trailing token if any
        truncated = text[:max_length]
        # if the next char in original isn't sep and our chop landed mid-token, trim back to last sep
        if (len(text) > max_length and not truncated.endswith(sep) and sep in truncated):
            truncated = truncated.rsplit(sep, 1)[0]
        text = truncated

    # If an extension was removed, append it back
    text += removed_ext

    return text


def if_filepath_then_read(input_string_or_filepath: str | os.PathLike[str],
                          force_string: bool = False) -> str:
    """
    If 'input_string_or_filepath' is a file path, read its contents and return as a string. If not, return the input_string as is.

    Args:
        input_string_or_filepath: The source can be a file path or a string.
        force_string:             If True, treat 'input_string_or_filepath' as a string even if
                                  it looks like a file path.

    Returns:
        str : The contents of the file if input_string_or_filepath is a file path,
              or the input_string_or_filepath itself if it is not a file path.

    Raises:
        TypeError : If input_string is not a string or a file path, or if force_string is True but input_string_or_filepath is os.PathLike.
    """
    fallback_logging_config()
    # Is "input_string" a file path, and is "force_string" False?
    # If so, read the file contents.
    if force_string and isinstance(input_string_or_filepath, os.PathLike):
        raise TypeError(f"'input_string_or_filepath' was given as a file path ({input_string_or_filepath!r}) but 'force_string' is True, so it cannot be treated as a file path.")
    # Heuristics: if it contains newlines or is ridiculously long, it's source.
    if isinstance(input_string_or_filepath, str) and ("\n" in input_string_or_filepath or len(input_string_or_filepath) > 4096):
        return input_string_or_filepath
    if not force_string and safe_is_file(file_path := ensure_path(input_string_or_filepath)):
        try:
            contents = my_fopen(file_path, suppress_errors=True)
            if not contents:
                logging.error("Could not read file: %s", os.fspath(file_path))
                return ""
            return contents
        except FileNotFoundError:
            logging.exception("File not found: %s", os.fspath(file_path))
        except PermissionError:
            logging.exception("Permission denied: %s", os.fspath(file_path))
        except UnicodeDecodeError:
            logging.exception("Could not decode %r.", os.fspath(file_path))
    else:  # Otherwise, treat "input_string" as a string.
        if not isinstance(input_string_or_filepath, str):
            raise TypeError(f"Expected 'input_string_or_filepath' to be a string or file path, got {type(input_string_or_filepath).__name__!r}")
        return input_string_or_filepath  # Just return the input string as is.


def compile_code(source_or_filepath: str | os.PathLike[str],
                 force_source: bool = False) -> bool:
    """
    Attempt to compile the given source code in 'exec' mode.
    If 'source_or_filepath' is a file path, read its contents first.

    Args:
        source_or_filepath: The source code string or file path to compile.
        force_source:       If True, treat 'source_or_filepath' as a source code string even if it looks like a file path.

    Returns:
        True if compilation succeeds, False if it fails with a SyntaxError or other exception

    Raises:
        SyntaxError: If the source code has a syntax error, it will be logged and False is returned.
        TypeError:   If 'source_or_filepath' is not a string or a file path.
    """
    fallback_logging_config()
    # Read from file if source is a file path
    source = if_filepath_then_read(source_or_filepath, force_string=force_source)
    if source != source_or_filepath:
        file_path = ensure_path(source_or_filepath)
    else:
        # If it's a string, we need to provide a dummy file path for the compiler.
        # This is just to satisfy the compiler, it won't be used.
        file_path = "<string>"
    try:
        compile(source, file_path, "exec")
    except SyntaxError as e:
        # protect against None offsets
        lineno = e.lineno or "?"
        offset = e.offset or 0
        line = (e.text or "").rstrip("\n")
        pointer = " " * (offset - 1) + "^" if offset else ""
        logging.error(f"Syntax error in {e.filename!r}, line {lineno}, column {offset}:\n"
                      f"    {line}\n"
                      f"    {pointer}\n"
                      f"    {e.msg!r}", exc_info=True)
        return False
    return True


# --------------------------------------------------------------------------------
# Note: Python resolves base classes at the moment a class statement is executed.
# That means any names used as base classes (e.g., ast.NodeVisitor) must already
# be defined in the current scope when the class is created.
#
# If we defer importing 'ast' until inside a function but still try to define
# the class at the module level, Python will raise:
#     NameError: name 'ast' is not defined
#
# Wrapping the class definition in a factory function lets us:
#   1) Import 'ast' inside the function, so it's guaranteed to be in scope
#      when we define the class.
#   2) Keep module‑level imports to a minimum (only __future__ and typing).
#   3) Return the fully‑constructed class and assign it to the module name.
#
# In short: by defining FormatChecker inside this helper, we avoid NameError
# and still get a clean, well‑typed class available at the module level.
# --------------------------------------------------------------------------------


def _make_format_checker() -> Type[Any]:
    """Factory function to create the FormatChecker class with the necessary imports."""
    import ast

    class FormatChecker(ast.NodeVisitor):
        """
        Walks a module AST and collects formatting violations:
        - missing type hints on params / return
        - missing docstring or incorrect docstring quote style
        """

        def __init__(self, source: str, doc_style: str = "None") -> None:
            """Initialize the FormatChecker with the source code string."""
            self.source = source
            self.doc_style = doc_style  # "None", "NumPy", "Google", "reStructuredText"
            self.errors: list[tuple[str, str, str, int]] = []
            self._seen_funcs: set[int] = set()  # keep track of which FunctionDef/AsyncFunctionDef nodes we've already checked

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            """Visit a FunctionDef node and check for formatting violations."""
            self._check_function(node)
            self.generic_visit(node)

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            """Visit an AsyncFunctionDef node and check for formatting violations."""
            self._check_function(node)
            self.generic_visit(node)

        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            """Visit a ClassDef node and check for formatting violations."""
            self._check_docstring(node, f'class "{node.name}"')
            init = self._find_init(node)
            if init:
                self._check_function(init, in_method=True, container=f'class "{node.name}"')
            self.generic_visit(node)

        def _find_init(self, node: ast.ClassDef) -> ast.FunctionDef | None:
            """Find the __init__ method in a class definition."""
            for elt in node.body:
                if isinstance(elt, (ast.FunctionDef, ast.AsyncFunctionDef)) and elt.name == "__init__":
                    return elt  # type: ignore
            return None

        def _check_function(self, node: ast.FunctionDef, *, in_method: bool = False, container: str | None = None) -> None:
            """Check a function or method node for formatting violations.
            If 'in_method' is True, it indicates that this is a method (e.g. inside a class).
            If 'container' is provided, it indicates the context (e.g. class name)."""
            if id(node) in self._seen_funcs:  # ←─ skip if we've already run this exact node
                return
            self._seen_funcs.add(id(node))
            who = (f'function "{node.name}"' if container is None else f'{container} → method "{node.name}"')
            self._check_docstring(node, who)

            missing: list[str] = []
            args = [a for a in node.args.args if a.arg != "self"]
            for a in args + node.args.kwonlyargs:
                if a.annotation is None:
                    missing.append(f'param "{a.arg}"')
            if node.args.vararg and node.args.vararg.annotation is None:
                missing.append(f'param "*{node.args.vararg.arg}"')
            if node.args.kwarg and node.args.kwarg.annotation is None:
                missing.append(f'param "**{node.args.kwarg.arg}"')
            if node.returns is None:
                missing.append("return")
            if missing:
                self.errors.append(("function", node.name,
                                    "missing type hints for " + ", ".join(missing),
                                    node.lineno))

        def _check_docstring(self, node: ast.AST, who: str) -> None:
            """
            Check a node for a docstring and its formatting.
            An error is added to self.errors if:
              - The node has no docstring
              - The docstring is not formatted correctly
              - There is more than one docstring
            The 'who' parameter is a string describing the context (e.g. function or class name).
            """
            if not node.body or not isinstance(node.body[0], ast.Expr):
                self.errors.append((node.__class__.__name__.casefold(), who, "no docstring",
                                    node.lineno))
                return

            expr = node.body[0]
            if not (isinstance(expr.value, ast.Constant) and isinstance(expr.value.value, str)):
                self.errors.append((node.__class__.__name__.casefold(), who, "no docstring",
                                    node.lineno))
                return

            # Recover the exact literal to verify triple-double-quote
            literal = ast.get_source_segment(self.source, expr.value) or ""
            first_line = literal.strip().splitlines()[0]
            if first_line.startswith("'''"):
                self.errors.append((node.__class__.__name__.casefold(), who,
                                    'docstring should use triple double quotes ("""...""")',
                                    node.lineno))

            # Now scan for any extra standalone triple‐quoted strings
            for extra in node.body[1:]:
                # Only look at Exprs, i.e. un‐assigned string literals
                if  isinstance(extra, ast.Expr) \
                and isinstance(extra.value, ast.Constant) \
                and isinstance(extra.value.value, str):
                    literal = ast.get_source_segment(self.source, extra.value) or ""
                    first = literal.strip().splitlines()[0]
                    # If it starts with triple quotes, it's an extra docstring
                    if first.startswith(('"""', "'''")):
                        self.errors.append((node.__class__.__name__.casefold(),
                                            who, "extra docstring", extra.lineno))

            # Check the docstring style
            self._check_docstring_style(node, who)

        def _check_docstring_style(self, node: ast.AST, who: str) -> None:
            """Dispatch to the style‑specific docstring checker."""
            if not self.doc_style or self.doc_style.casefold() == "none":
                return
            checker = {
                "Google"           : self._check_google_docstring,
                # "NumPy"              : self._check_numpy_docstring,
                # "reStructuredText" : self._check_rst_docstring,
            }.get(self.doc_style)
            logging.warning("Consider adding an exception to the docstring checker: if the function is less than 5(?) lines, allow a single line docstring without the required sections. Also, if there are no args or no return value or it doesn't raise exceptions.")
            if checker is not None:
                checker(node, who)

        def _check_google_docstring(self, node: ast.AST, who: str) -> None:
            """
            Very basic Google‑style docstring validator:
            - must have a 'Args:' and 'Returns:' section header
            - every non‑self arg must be listed under Parameters
            """
            doctype = "Google"
            # Get the cleaned docstring
            doc = ast.get_docstring(node)
            if not doc:
                return  # already flagged as missing

            lines = doc.splitlines()
            # Locate the section headers
            try:
                params_idx = next(i for i, L in enumerate(lines) if L.strip() == "Args:")
            except StopIteration:
                self.errors.append((node.__class__.__name__.casefold(), who,
                                    f"{doctype} docstring missing 'Args' section",
                                    node.lineno))
                return

            try:
                returns_idx = next(i for i, L in enumerate(lines) if L.strip() == "Returns:")
            except StopIteration:
                self.errors.append((node.__class__.__name__.casefold(), who,
                                    f"{doctype} docstring missing 'Returns' section",
                                    node.lineno))

            # Collect documented params: lines immediately under 'Parameters'
            documented = set()
            for line in lines[params_idx+1:]:
                if not line.strip():
                    break
                m = re.match(r'^(\w+)\s*:\s*(.+)$', line)
                if m:
                    documented.add(m.group(1))

            # Get function args (excluding self)
            sig_args = []
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                sig_args = [a.arg for a in node.args.args if a.arg != "self"]

            missing = [a for a in sig_args if a not in documented]
            if missing:
                self.errors.append((node.__class__.__name__.casefold(), who,
                                    f"{doctype} docstring missing parameter(s): " + ", ".join(missing), node.lineno))

        def _check_numpy_docstring(self, node: ast.AST, who: str) -> None:
            """
            Very basic NumPy‑style docstring validator:
            - must have a 'Parameters' and 'Returns' section header
            - every non‑self arg must be listed under Parameters
            """
            doctype = "NumPy"
            # Get the cleaned docstring
            doc = ast.get_docstring(node)
            if not doc:
                return  # already flagged as missing

            lines = doc.splitlines()
            # Locate the section headers
            try:
                params_idx = next(i for i, L in enumerate(lines) if L.strip() == "Parameters")
            except StopIteration:
                self.errors.append((node.__class__.__name__.casefold(), who,
                                    f"{doctype} docstring missing 'Parameters' section",
                                    node.lineno))
                return

            try:
                returns_idx = next(i for i, L in enumerate(lines) if L.strip() == "Returns")
            except StopIteration:
                self.errors.append((node.__class__.__name__.casefold(), who,
                                    f"{doctype} docstring missing 'Returns' section",
                                    node.lineno))

            # Collect documented params: lines immediately under 'Parameters'
            documented = set()
            for line in lines[params_idx+1:]:
                if not line.strip():
                    break
                m = re.match(r'^(\w+)\s*:\s*(.+)$', line)
                if m:
                    documented.add(m.group(1))

            # Get function args (excluding self)
            sig_args = []
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                sig_args = [a.arg for a in node.args.args if a.arg != "self"]

            missing = [a for a in sig_args if a not in documented]
            if missing:
                self.errors.append((node.__class__.__name__.casefold(), who,
                                    f"{doctype} docstring missing parameter(s): " + ", ".join(missing), node.lineno))

    return FormatChecker


FormatChecker = _make_format_checker()


def check_python_formatting(path: str | os.PathLike[str], diff_choice: int = 1) -> bool:
    """
    Reads a .py file at 'path' via my_fopen, makes sure it compiles, parses it with AST,
    prints any custom formatting violations to stdout,
    and asks the user to fix any backticks or curly quotes in the file. If the user quits, it returns False.

    Args:
        path:        The path to the Python file to check.
        diff_choice: How many context lines to show in the diff (0 = old-style diff, 1 = unified diff with 0 context lines, 2+ = unified diff with 'diff_choice - 1' context lines).

    Returns:
        False if the user chose to quit during any replacement prompts, True otherwise.

    Raises:
        FileNotFoundError: If the specified file does not exist.
    """
    import ast
    fallback_logging_config()
    path = ensure_file(path)
    src  = my_fopen(   path)
    if src is False:
        logging.error("❌ Failed to open file: %s", os.fspath(path))
        return

    if compile_code(src):
        logging.info("✅ %s compiled successfully.", os.fspath(path))

    logging.warning("LOOK FOR logging.debug STATEMENTS THAT USE F-STRINGS OR THAT DON'T HAVE GUARDS!!")

    if BACKTICK in src:
        logging.warning("File %s contains the backtick character (%r). Use straight quotation marks (') instead.", os.fspath(path), BACKTICK)
        if not ask_and_replace(old_str=BACKTICK, new_str="'", path=path, label="backtick",
                               diff_choice=diff_choice,
                               description=f"Replace backtick ({BACKTICK}) with straight apostrophe (')"):
            return False
    if LSQUOTE in src or RSQUOTE in src:
        logging.warning("File %s contains curly single quotation marks (%r or %r). Use straight apostrophes (') instead.", os.fspath(path), LSQUOTE, RSQUOTE)
        if not ask_and_replace(old_str=LSQUOTE, new_str="'", path=path, label="left-curly-apostrophe",
                               diff_choice=diff_choice,
                               description=f"Replace left curly apostrophe ({LSQUOTE}) with straight apostrophe (')"):
            return False
        if not ask_and_replace(old_str=RSQUOTE, new_str="'", path=path, label="right-curly-apostrophe",
                               diff_choice=diff_choice,
                               description=f"Replace right curly apostrophe ({RSQUOTE}) with straight apostrophe (')"):
            return False
    if LDQUOTE in src or RDQUOTE in src:
        logging.warning("File %s contains curly double quotation marks (%r or %r). Use straight quotation marks (\") instead.", os.fspath(path), LDQUOTE, RDQUOTE)
        if not ask_and_replace(old_str=LDQUOTE, new_str='"', path=path,
                               label="left-curly-quotation-mark",
                               diff_choice=diff_choice,
                               description=f'Replace left curly double quotation mark ({LDQUOTE}) with straight double quotation mark (")'):
            return False
        if not ask_and_replace(old_str=RDQUOTE, new_str='"', path=path, label="right-curly-quotation-mark",
                               diff_choice=diff_choice,
                               description=f'Replace right curly double quotation mark ({RDQUOTE}) with straight double quotation mark (")'):
            return False
    if HORIZONTAL_ELLIPSIS in src:
        logging.warning("File %s contains the horizontal ellipsis character (%r). Use three periods (...) instead.", os.fspath(path), HORIZONTAL_ELLIPSIS)
        if not ask_and_replace(old_str=HORIZONTAL_ELLIPSIS, new_str="...", path=path,
                               label="horizontal-ellipsis", diff_choice=diff_choice,
                               description=f"Replace horizontal ellipsis ({HORIZONTAL_ELLIPSIS}) with three periods (...)"):
            return False

    try:
        tree = ast.parse(src, path)
    except SyntaxError:
        logging.exception("❌ %s contains a syntax error.", os.fspath(path))
        return False

    checker = FormatChecker(src)
    checker.visit(tree)

    if not checker.errors:
        logging.info("🎉 All functions and classes conform to the custom formatting rules.")
    else:
        max_lineno = max(err[3] for err in checker.errors)
        the_digits = sci_exp(max_lineno) + 1
        for kind, name, msg, lineno in checker.errors:
            logging.error(f"{lineno:>{the_digits}} – {kind.capitalize()} {name}: {msg}")

    return True


def run_flake8(options: Options, path: str | os.PathLike[str],
               ignore_codes: list[str] | None = None,
               max_line_length: int = 100) -> flake8.Report:
    """
    Run Flake8 on 'path', but:
      - only flag E501 if a line exceeds 'max_line_length',
      - ignore whatever codes are in 'ignore_codes'.

    Args:
        options:         Options instance containing various settings.
        path:            The path to the Python file to check.
        ignore_codes:    A list of Flake8 error/warning codes to ignore.
        max_line_length: The (custom) maximum allowed line length for E501 checks.

    Returns:
        flake8.Report:   The Flake8 report object containing the results.

    Raises:
        FileNotFoundError: If the specified file does not exist.
    """
    from flake8.api import legacy as flake8
    # Ensures our env manager installs the plugin; no runtime effect on Flake8.
    try:  # Flake8: "no quality assurance": F401 = Pyflakes code for "module imported but unused"
        import bugbear  # noqa: F401
        # "B" = All standard Bugbear rules (B001...B8xx). "B9" = All optional/opinionated B9xx rules.
        options.bugbear_choice = "B,B9"
        logging.info("Using flake8-bugbear checks.")
    except ImportError:
        logging.error("flake8-bugbear is not installed, so no Bugbear checks will be performed.")
        options.bugbear_choice = None
    fallback_logging_config()
    if ignore_codes is None:
        ignore_codes: list[str] = []
    if not isinstance(ignore_codes, list):
        raise TypeError("'ignore_codes' must be a list of strings.")
    if not all(isinstance(code, str) for code in ignore_codes):
        raise TypeError("All elements in 'ignore_codes' must be strings.")
    path        = ensure_file(path)
    kwargs = dict(max_line_length=max_line_length, ignore=ignore_codes)
    if options.bugbear_choice:
        codes  = tuple(c.strip() for c in options.bugbear_choice.split(",") if c.strip())
        kwargs["extend_select"] = codes
        if any(c in {"B9", "B950"} for c in codes):
            kwargs["extend_ignore"] = ("E501",)  # E501 is redundant if B9xx rules are enabled
    style_guide = flake8.get_style_guide(**kwargs)
    report      = style_guide.check_files([path])
    if report.total_errors == 0:
        logging.info("✅ No Flake8 violations found in %s.", os.fspath(path))
        return report
    logging.error("Found %d total violations in %s:", report.total_errors, os.fspath(path))
    for stat in report.get_statistics(""):
        logging.error("  %s", stat)
    return report


def _gather_flake8_issues(options: Options, path: str | os.PathLike[str],
                          ignore_codes: list[str] | None = None,
                          max_line_length: int = 100) -> dict[str, str]:
    """
    Returns a dict mapping each Flake8 error code to its first-seen description
    in the file at 'path'.
    Tries the 'flake8' CLI (fast), but if it's not on PATH, falls back
    to an in-process Application/API solution.

    Args:
        options:         Options instance containing various settings. Contains:
                             - bugbear_choice: Whether to include flake8-bugbear checks (and if so, which ones?)
        path:            The path to the Python file to check.
        ignore_codes:    A list of Flake8 error/warning codes to ignore.
        max_line_length: The (custom) maximum allowed line length for E501 checks.

    Returns:
        A dictionary mapping Flake8 error codes to their descriptions.

    Raises:
        FileNotFoundError: If the specified file does not exist.
    """
    if ignore_codes is None:
        ignore_codes: list[str] = []
    try:
        return _gather_via_cli(options, path, max_line_length, ignore_codes)
    except FileNotFoundError:
        return _gather_via_app(options, path, max_line_length, ignore_codes)


def _gather_via_cli(options: Options, path: str | os.PathLike[str],
                    max_line_length: int, ignore_codes: list[str]) -> dict[str, str]:
    """Use the flake8 CLI to gather codes and descriptions."""
    import subprocess
    path = ensure_file(path)
    fmt = "%(row)d:%(col)d: %(code)s %(text)s"
    args = [  # sys.executable ensures we use the same Python interpreter (probably in a venv)
        sys.executable, "-m", "flake8",
        f"--max-line-length={max_line_length}",
        f"--ignore={','.join(ignore_codes)}",
        f"--format={fmt}",
        os.fspath(path),
    ]
    if options.bugbear_choice:
        args.insert(-1, f"--extend-select={options.bugbear_choice}")
        selected = {c.strip() for c in options.bugbear_choice.split(",") if c.strip()}
        if selected & {"B9", "B950"}:
            args.insert(-1, "--extend-ignore=E501")  # E501 is redundant if B9xx rules are enabled
    proc = subprocess.run(args, capture_output=True, text=True)
    codes: dict[str, str] = {}
    for line in proc.stdout.splitlines():
        # e.g. "12:5: E302 expected 2 blank lines, found 1"
        parts = line.split(": ", 1)
        if len(parts) != 2:
            continue
        _, rest = parts
        code, desc = rest.split(" ", 1)
        codes.setdefault(code, desc)
    return codes


def _gather_via_app(options: Options, path: str | os.PathLike[str],
                    max_line_length: int, ignore_codes: list[str]) -> dict[str, str]:
    """Use the flake8 Application API to gather codes and descriptions."""
    from flake8.main.application import Application
    from flake8.formatting.base  import BaseFormatter
    from flake8.violation        import Violation
    path = ensure_file(path)

    class CodeDictFormatter(BaseFormatter):
        """Custom formatter that collects codes and their first descriptions."""

        def __init__(self, options: dict[str, str]) -> None:
            """Initialize the formatter with options."""
            super().__init__(options)
            self.codes: dict[str, str] = {}

        def format(self, error: Violation) -> str:
            """Format a single error, capturing its code and description."""
            # capture the first description we see for each code
            self.codes.setdefault(error.code, error.text)
            # suppress any actual stdout
            return ""

    class CodeDictApp(Application):
        """Custom Application subclass to use our CodeDictFormatter."""

        def make_formatter(self) -> BaseFormatter:
            """Create a custom formatter that collects codes and descriptions."""
            # force our custom formatter
            self.formatter = CodeDictFormatter(self.options)
            return self.formatter

    app = CodeDictApp()
    # supply exactly the same CLI settings in-process
    cli_args = [f"--max-line-length={max_line_length}", f"--ignore={','.join(ignore_codes)}", os.fspath(path)]
    if options.bugbear_choice:
        cli_args.insert(-1, f"--extend-select={options.bugbear_choice}")
        selected = {c.strip() for c in options.bugbear_choice.split(",") if c.strip()}
        if selected & {"B9", "B950"}:
            cli_args.insert(-1, "--extend-ignore=E501")  # E501 is redundant if B9xx rules are enabled
    # this will parse, run checks, and invoke our formatter behind the scenes
    app.run(cli_args)
    # the formatter collected everything into .codes
    return app.formatter.codes


def get_autopep8_fixable_codes() -> set[str]:
    """
    Run 'autopep8 --list-fixes' (via subprocess) to discover exactly
    which Flake8 error‐codes autopep8 knows how to fix.
    Returns a set like {"E101","E111", ...}.
    """
    import subprocess
    fallback_logging_config()
    try:  # sys.executable ensures we use the same Python interpreter (probably in a venv)
        proc = subprocess.run([sys.executable, "-m", "autopep8", "--list-fixes"],
                              capture_output=True, text=True, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        logging.warning("autopep8 not found or failed.", exc_info=True)
        # autopep8 not on PATH or error—assume nothing fixable
        return set()

    fixable: set[str] = set()
    for line in proc.stdout.splitlines():
        # the output looks like:
        #   E101 - indentation not consistent
        #   E111 - indent does not match any outer indentation level
        # so take the code before the colon
        if " - " in line:
            code = line.split(" - ", 1)[0].strip()
            if code:
                fixable.add(code)
    return fixable


def _vis_trailing_ws(line: str) -> str:
    """
    Replace only the trailing spaces and tabs in 'line'
    with visible glyphs (· for space, → for tab).
    """
    core = line.rstrip(" \t")
    trail = line[len(core):]
    return core + trail.replace(" ", "·").replace("\t", "→")


def _vis_all_ws(s: str) -> str:
    """
    Show *all* spaces/tabs in s as visible glyphs:
      · for space, → for tab
    """
    return s.replace(" ", "·").replace("\t", "→")


def highlight_changes(orig: str, new: str, unchanged_color: str,
                      added_color: str, deleted_color: str) -> tuple[str, str]:
    """
    Compare 'orig' and 'new' strings and return a tuple
    (old_highlighted, new_highlighted), where:
    - old_highlighted has parts present only in 'orig' wrapped in deleted_color.
    - new_highlighted has parts present only in 'new' wrapped in added_color
      and unchanged parts in unchanged_color.

    Args:
        orig:            The original string.
        new:             The modified string.
        unchanged_color: The color to use for unchanged parts.
        added_color:     The color to use for added parts.
        deleted_color:   The color to use for deleted parts.

    Returns:
        A tuple of (old_highlighted, new_highlighted) strings.

    Raises:
        None.
    """
    import difflib
    sm = difflib.SequenceMatcher(None, orig, new)
    new_out: list[str] = []
    old_out: list[str] = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        old_segment = orig[i1:i2]
        new_segment =  new[j1:j2]
        if tag == "equal":
            new_out.append(f"{unchanged_color}{new_segment}{ANSI_RESET}")
            old_out.append(old_segment)
        elif tag == "replace":  # segments changed: mark old text as deleted, new text as added
            new_out.append(f"{added_color}{new_segment}{ANSI_RESET}")
            old_out.append(f"{deleted_color}{old_segment}{ANSI_RESET}")
        elif tag == "delete":  # text removed: mark in old, nothing in new
            old_out.append(f"{deleted_color}{old_segment}{ANSI_RESET}")
        elif tag == "insert":  # text added: mark in new, nothing in old
            # text added: if it's *only* whitespace, render it visibly
            if set(new_segment) <= {" ", "\t"}:
                visible = _vis_all_ws(new_segment)
            else:
                visible = new_segment
            new_out.append(f"{added_color}{visible}{ANSI_RESET}")
    return "".join(old_out), "".join(new_out)


def my_diff(orig_text:     str, changed_text: str,
            orig_path:     str | os.PathLike[str],
            changed_path:  str | os.PathLike[str] | None = None,
            diff_choice:   int = 1,
            changed_color: str = ANSI_CYAN,
            deleted_color: str = ANSI_RED,
            added_color:   str = ANSI_YELLOW) -> None:
    """
    Show a diff between 'orig_text' and 'changed_text' in the console,
    highlighting character-level changes within changed lines.

    Args:
        orig_text:      Original text to compare against.
        changed_text:   Proposed changes to the original text.
        orig_path:      Path to the original file.
        changed_path:   Optional path to the changed file (if different).
        diff_choice:    How many context lines to show in the diff ( 0 = old-style diff, 1 = unified diff with 0 context lines,
                                                                    2+ = unified diff with 'diff_choice - 1' context lines).
        changed_color:  Color to use for unchanged characters in the changed lines in the diff (default ANSI_CYAN).
        deleted_color:  Color to use for the deleted characters in orig lines (default ANSI_YELLOW).
        added_color:    Color to use for the added characters in changed lines (default ANSI_RED).

    Returns:
        None: Prints the diff to the console.

    Raises:
        None.
    """
    import difflib
    fallback_logging_config(rawlog=True)
    orig_path = ensure_path(orig_path)
    if not changed_path:
        changed_path = orig_path
    logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("At the top of the function %s(), diff_choice=%s", return_method_name(), diff_choice)
    orig_lines    =    orig_text.splitlines(keepends=True)
    changed_lines = changed_text.splitlines(keepends=True)
    the_digits    = max(len(str(len(orig_lines))), len(str(len(changed_lines))))
    last_removed  = None  # there is no last removed line initially
    # shared buffer for the current hunk's deletes/inserts
    hunk_entries: list[tuple[str, str, int, int]] = []
    # each entry is (tag, text, orig_lineno, new_lineno)
    # orig_lineno or new_lineno will be None for pure inserts/deletes.

    def process_hunk() -> None:
        """Pair up deletes and inserts in the current hunk and print them with highlights."""
        nonlocal hunk_entries
        if not hunk_entries:
            return
        # Partition current hunk entries.
        deletes = [e for e in hunk_entries if e[0] == "-"]
        inserts = [e for e in hunk_entries if e[0] == "+"]
        # We'll pair in order: kth delete with kth insert.
        pair_count = min(len(deletes), len(inserts))
        di = 0
        # Track which 'new' line numbers have already been consumed by a pairing
        # (so we can skip printing those '+' entries when the loop hits them later).
        consumed_new_line_numbers: set[int] = set()
        for tag, text, dln, nln in hunk_entries:
            if tag == "-":
                if di < pair_count:
                    # Compare this delete with its paired insert.
                    old_vis = _vis_trailing_ws(text)
                    new_text = inserts[di][1]
                    new_nln  = inserts[di][3]
                    new_vis  = _vis_trailing_ws(new_text)
                    # Mark the paired '+' as consumed, regardless of identical/different.
                    consumed_new_line_numbers.add(new_nln)
                    # If identical after visibility transform, emit nothing (no context).
                    if old_vis == new_vis:
                        di += 1
                        continue
                    # Otherwise, highlight differences.
                    old_hl, new_hl = highlight_changes(old_vis, new_vis,
                                                       unchanged_color=changed_color,
                                                       added_color=added_color,
                                                       deleted_color=deleted_color)
                    logging.info(f"< {dln:>{the_digits}}: {old_hl}{ANSI_RESET}")
                    logging.info(f"{changed_color}> {new_nln:>{the_digits}}:{ANSI_RESET} {new_hl}{ANSI_RESET}")
                    di += 1
                else:
                    # Unpaired delete (pure removal in this hunk).
                    logging.info(f"< {dln:>{the_digits}}: {deleted_color}{_vis_trailing_ws(text)}{ANSI_RESET}")
            elif tag == "+":
                # If this '+' was already paired (even if identical), skip it.
                if nln in consumed_new_line_numbers:
                    continue
                # Unpaired insert (pure addition in this hunk).
                vis = _vis_trailing_ws(text)
                logging.info(f"{changed_color}> {nln:>{the_digits}}:{ANSI_RESET} {ANSI_RED}{vis}{ANSI_RESET}")
        hunk_entries.clear()

    def flush_removed(orig_lineno: int) -> None:
        """Flush the last removed line if it exists."""
        nonlocal last_removed
        if last_removed is not None:
            highlighted_old = f"{deleted_color}{last_removed}{ANSI_RESET}"
            logging.info(f"< {orig_lineno:>{the_digits}}: {highlighted_old}")
            last_removed = None

    if diff_choice == 0:  # old style diff (difflib.Differ)
        logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("Using old-style diff for %s with %d original and %d fixed lines.", os.fspath(orig_path), len(orig_lines), len(changed_lines))
        orig_lineno = 1
        new_lineno  = 1
        for line in difflib.Differ().compare(orig_lines, changed_lines):
            tag, body = line[:2], line[2:].rstrip("\n")
            if tag == "  ":    # context line
                # end of any previous mini‑hunk
                process_hunk()
                flush_removed(orig_lineno)
                orig_lineno += 1
                new_lineno  += 1
            elif tag == "- ":  # original line
                # buffer a delete
                hunk_entries.append(("-", body, orig_lineno, None))
                orig_lineno += 1
            elif tag == "+ ":  # fixed line
                # buffer an insert
                hunk_entries.append(("+", body, None, new_lineno))
                new_lineno += 1
            # skip '? ' lines entirely
        # flush any trailing buffered pairs/inserts
        process_hunk()
        flush_removed(orig_lineno)
    elif diff_choice >= 1:  # unified or context diff
        logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("Using unified diff for %s with %d original and %d fixed lines.", os.fspath(orig_path), len(orig_lines), len(changed_lines))
        ctx  = max(diff_choice - 1, 0)
        diff = difflib.unified_diff(
            orig_lines, changed_lines,
            fromfile=os.fspath(orig_path), tofile=os.fspath(changed_path),
            n=ctx, lineterm=""
        )
        header_re = re.compile(r"@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@")
        orig_lineno = new_lineno = None
        for line in diff:
            if line.startswith("@@"):  # hunk header?
                # flush any leftover from the prior hunk
                process_hunk()
                m           = header_re.match(line)
                orig_lineno = int(m.group(1))
                new_lineno  = int(m.group(2))
                continue
            if line.startswith(("---", "+++")):  # skip file header lines
                continue
            tag, body = line[0], line[1:].rstrip("\n")
            if tag == " ":  # context line: flush and emit
                process_hunk()
                flush_removed(orig_lineno)
                logging.info(f"  {orig_lineno:>{the_digits}}: {_vis_trailing_ws(body)}")
                orig_lineno += 1
                new_lineno  += 1
            elif tag == "-":  # buffer a delete
                hunk_entries.append(("-", body, orig_lineno, None))
                orig_lineno += 1
            elif tag == "+":  # buffer an insert
                hunk_entries.append(("+", body, None, new_lineno))
                new_lineno += 1
        # final flush
        process_hunk()
        flush_removed(orig_lineno)
    else:
        logging.error("Unsupported diff_choice = %d. Must be a non-negative integer.", diff_choice)


def is_python_script(path: str | os.PathLike[str]) -> bool:
    """
    Return True if 'path' looks like a Python script:
      1. It's a file which ends in .py or .pyw
      2. Or it is executable AND its first line is a python shebang

    Args:
        path: The file path to check.

    Returns:
        True if the path is a Python script, False otherwise.

    Raises:
        IsADirectoryError: If the path is a directory.
        FileNotFoundError: If the file is not found.
        PermissionError:   If the file is not accessible due to permission issues.
    """
    path = ensure_path(path)
    if not safe_is_file(path):
        return False

    # Common extensions
    if path.suffix.casefold() in PYTHON_EXTENSIONS_SET:
        return True

    # No-extension scripts: check for executable bit + python shebang
    try:
        st = safe_stat(path)
    except OSError:
        return False

    if st is None:  # This can happen if the user doesn't have permission to stat the file.
        return False

    # Must be a regular file and executable by owner/group/other
    import stat
    if not stat.S_ISREG(st.st_mode) or not (st.st_mode & (stat.S_IXUSR|stat.S_IXGRP|stat.S_IXOTH)):
        return False

    # Try to read the first line and look for a python shebang
    first_line = my_fopen(path, suppress_errors=True, rawlog=False, numlines=1)
    if not first_line:
        return False
    return bool(re.match(r'#!.*\bpython[0-9.]*\b', first_line))


def diff_and_confirm(orig_text: str, changed_text: str,
                     path: str | os.PathLike[str], label: str = "",
                     skip_compile: bool = False, diff_choice: int = 1,
                     changed_color: str = ANSI_CYAN,
                     deleted_color: str = ANSI_RED,
                     added_color:   str = ANSI_YELLOW,
                     the_fix:       str = "", description: str = "") -> bool:
    """
    Show a unified diff of orig_text → changed_text with a number of context lines
    (determined by 'diff_choice') around each hunk, log using 'label' and 'description', then prompt.
    If the user confirms, overwrite 'path' with changed_text and return True.
    If the user chooses to quit, log a message and return False.

    Args:
        orig_text:     Original text to compare against.
        changed_text:  Proposed changes to the original text.
        path:          Path to the file being modified.
        label:         A short label for the issue being fixed (default "").
        skip_compile:  If True, do not try to compile the changed text before writing (default False).
        diff_choice:   How many context lines to show in the diff (0 = old-style diff, 1 = unified diff with 0 context lines, 2+ = unified diff with 'diff_choice - 1' context lines) (default 1).
        changed_color: Color to use for unchanged characters in the changed lines in the diff (default ANSI_CYAN).
        deleted_color: Color to use for the deleted characters in orig lines (default ANSI_YELLOW).
        added_color:   Color to use for the added characters in changed lines (default ANSI_GREEN).
        the_fix:       A string describing the fix being applied (e.g. "autopep8", "manual edit") (default "").
        description:   A longer description of the issue being fixed (default "").

    Returns:
        False if the user chose to quit; True otherwise.

    Raises:
        FileNotFoundError: If the specified file does not exist.
        ValueError: If the specified path is not a file. The function which raises this exception is my_fopen().
    """
    fallback_logging_config()
    logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("At the top of the function %s(), diff_choice=%s", return_method_name(), diff_choice)
    path = ensure_file(path)
    my_diff(orig_text, changed_text, path, diff_choice=diff_choice,
            changed_color=changed_color, deleted_color=deleted_color, added_color=added_color)
    label_str = f"{ANSI_RED}{label}{ANSI_RESET}" if label     else ""
    fix_str   = f" using {the_fix}"              if the_fix   else ""
    subject   = f"{label_str} "                  if label_str else ""
    logging.info("End of proposed %schanges to %s%s.", subject, os.fspath(path), fix_str)
    if description:
        prefix = f"{label_str}: "                if label_str else ""
        logging.info(f"{prefix}{ANSI_YELLOW}{description}{ANSI_RESET}")
    ans = input("Apply these changes? [y/N/q] ").strip().casefold()
    if ans in ("y", "yes"):
        # If the user hasn't chosen to skip compilation and this is a Python script,
        # try to compile the changed text before writing it. If compilation fails, abort the write.
        if not skip_compile and is_python_script(path) and not compile_code(changed_text, force_source=True):
            logging.error(f"{ANSI_RED}Failed to compile the changed python script. Aborting write.{ANSI_RESET}")
            return False  # Don't write if it won't compile, and don't continue.
        path.write_text(changed_text, encoding=DEFAULT_ENCODING)
        if the_fix:
            logging.info(f"{ANSI_GREEN}Applied {the_fix} to {os.fspath(path)}{ANSI_RESET}")
        else:
            logging.info(f"{ANSI_GREEN}Applied changes to {os.fspath(path)}{ANSI_RESET}")
    elif ans in ("q", "quit", "exit"):
        logging.info(f"{ANSI_YELLOW}Exiting without further changes.{ANSI_RESET}")
        return False
    else:
        logging.info(f"{ANSI_YELLOW}Skipped writing changes.{ANSI_RESET}")
    return True


def ask_and_autopep8(path: str | os.PathLike[str], code: str,
                     description:   str = "", diff_choice: int = 1,
                     changed_color: str = ANSI_CYAN,
                     deleted_color: str = ANSI_RED,
                     added_color:   str = ANSI_YELLOW) -> bool:
    """
    Prompt the user about fixing ALL occurrences of 'code' in 'path',
    and if yes, apply autopep8.fix_file with --select=code.
    The fix will be applied without saving, and the user will be shown a diff
    of the changes before saving to the file.

    Args:
        path:          The path to the file to modify.
        code:          The specific PEP 8 violation code to fix.
        description:   A description of the issue being fixed (default "").
        diff_choice:   How many context lines to show in the diff (0 = old-style diff, 1 = unified diff with 0 context lines, 2+ = unified diff with 'diff_choice - 1' context lines) (default 1).
        changed_color: Color to use for unchanged characters in the changed lines in the diff (default ANSI_CYAN).
        deleted_color: Color to use for the deleted characters in orig lines (default ANSI_YELLOW).
        added_color:   Color to use for the added characters in changed lines (default ANSI_GREEN).

    Returns:
        True if the user wants to continue, False if they want to quit.

    Raises:
        FileNotFoundError: If the specified file does not exist.
        ValueError: If the specified path is not a file. The function which raises this exception is autopep8.fix_file().
    """
    import autopep8
    fallback_logging_config()
    path = ensure_file(path)
    logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("At the top of the function %s(), diff_choice=%s", return_method_name(), diff_choice)
    # The number of blank lines expected in various contexts.
    blank_line_overrides = {
        "E301" : 1,  # expected 1 blank line, found 0
        "E302" : 2,  # expected 2 blank lines, found 1
        "E303" : 5,  # too many blank lines (give a lot of context to see what is around the blank lines)
        "E305" : 2,  # expected 2 blank lines after class/method
    }
    orig_text = my_fopen(path)
    changed_text = orig_text
    for level in (0, 1, 2):  # try with 0, 1, then 2 "-a" flags
        flags = ["-a"] * level
        the_fix = f"autopep8 {' '.join(flags)} --select={code}"
        args = [f"--select={code}", "--in-place"] + flags + [os.fspath(path)]
        opts      = autopep8.parse_args(args)
        candidate = autopep8.fix_code(orig_text, options=opts)
        if candidate != orig_text:
            changed_text = candidate
            break
    if changed_text == orig_text:
        logging.info("No changes for %s in %s using %s.", code, os.fspath(path), the_fix)
        return True
    if not isinstance(diff_choice, int) or diff_choice < 0:
        logging.error("Invalid diff_choice=%d. Must be a non-negative integer.", diff_choice)
        return False
    # If this is a blank‑line code, force unified with the number of context lines specified in blank_line_overrides.
    if code in blank_line_overrides:
        # +1 so that unified_diff(n=override‑1) gives you exactly override context
        effective = blank_line_overrides[code] + 1
    else:
        effective = diff_choice
    return diff_and_confirm(orig_text, changed_text, path, label=code, diff_choice=effective,
                            changed_color=changed_color, deleted_color=deleted_color, added_color=added_color,
                            the_fix=the_fix, description=description)


def ask_and_replace(old_str: str, new_str: str,
                    path: str | os.PathLike[str],  label: str = "",
                    diff_choice:   int = 1, description: str = "",
                    changed_color: str = ANSI_CYAN,
                    deleted_color: str = ANSI_RED,
                    added_color:   str = ANSI_YELLOW,
                    skip_compile: bool = False) -> bool:
    """
    Read 'path', do orig.replace(old, new), then show a diff and ask to confirm.

    Args:
        old_str:       Old string to search for.
        new_str:       New string to replace the old string.
        path:          Path to the file being modified.
        label:         A short label for the issue being fixed (default "").
        skip_compile:  If True, do not try to compile the changed text before writing (default False).
        diff_choice:   How many context lines to show in the diff (0 = old-style diff, 1 = unified diff with 0 context lines, 2+ = unified diff with 'diff_choice - 1' context lines) (default 1).
        changed_color: Color to use for unchanged characters in the changed lines in the diff (default ANSI_CYAN).
        deleted_color: Color to use for the deleted characters in orig lines (default ANSI_YELLOW).
        added_color:   Color to use for the added characters in changed lines (default ANSI_GREEN).
        the_fix:       A string describing the fix being applied (e.g. "autopep8", "manual edit") (default "").
        description:   A longer description of the issue being fixed (default "").

    Returns:
        False if the user chose to quit; True otherwise.

    Raises:
        IsADirectoryError: If the path is a directory.
        FileNotFoundError: If the file is not found.
        PermissionError: If the file is not accessible due to permission issues.
    """
    fallback_logging_config()
    path         = ensure_file(path)
    orig_text    = my_fopen(path)
    changed_text = orig_text.replace(old_str, new_str)
    if changed_text == orig_text:
        if label:
            logging.info("No occurrences of %s in %s.", label, os.fspath(path))
        else:
            logging.info("No occurrences of '%s' in %s.", old_str, os.fspath(path))
        return True
    the_fix = f"replace '{old_str}' with '{new_str}'"
    return diff_and_confirm(orig_text, changed_text, path, label=label, diff_choice=diff_choice,
                            changed_color=changed_color, deleted_color=deleted_color, added_color=added_color,
                            skip_compile=skip_compile, the_fix=the_fix, description=description)


def _validate_glob_pattern(pattern: str) -> None:
    """Basic validation for glob pattern (non-empty string)."""
    if not isinstance(pattern, str) or not pattern.strip():
        raise ValueError("glob_pattern must be a non-empty string.")


def _resolve_dir(dir_arg: str | None) -> Path:
    """Resolve the directory from the command line argument."""
    if dir_arg:
        p = ensure_path(dir_arg)
    else:
        p = Path.cwd().expanduser().resolve(strict=True)
    if not safe_exists(p):
        raise FileNotFoundError(f"Directory does not exist: {os.fspath(p)}")
    if not safe_is_dir(p):
        raise NotADirectoryError(f"Path is not a directory: {os.fspath(p)}")
    return p


def _collect_files(root: Path, pattern: str, recursive: bool) -> list[Path]:
    """Collect files matching the glob pattern from root."""
    search_iter: Iterable[Path]
    if recursive:
        search_iter = root.rglob(pattern)
    else:
        search_iter = root.glob(pattern)

    files = [p for p in search_iter if safe_is_file(p)]
    return files


def multireplace(options: Options) -> None:
    """
    Perform a multi-file replace operation.

    Args:
        options: The parsed command-line options. Contains:
            - old_str: The text to be replaced in the files.
            - new_str: The text to replace the old_str.
            - glob_pattern: Glob pattern of files to edit.
            - dir: Directory to search in.
            - recursive: Whether to search recursively in subdirectories.

    Returns:
        None. Modifies files in place if the user confirms the changes.

    Raises:
        ValueError:         If the glob pattern is invalid.
        FileNotFoundError:  If the specified directory does not exist.
        NotADirectoryError: If the specified path is not a directory.
    """
    fallback_logging_config()
    try:
        _validate_glob_pattern(options.args.glob_pattern)
    except Exception as e:
        logging.error(f"Invalid glob pattern: {e}")
        sys.exit(2)

    try:
        dir = _resolve_dir(options.args.dir)
    except Exception as e:
        logging.error(str(e))
        sys.exit(2)

    logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("Directory: %s", dir)
    logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("Glob pattern: %s", options.args.glob_pattern)
    logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("Recursive: %s", options.args.recursive)

    files = _collect_files(dir, options.args.glob_pattern, options.args.recursive)

    if not files:
        logging.warning("No files matched the given pattern.")
        return

    logging.info("Found %d file(s) to process:", len(files))
    num_files  = len(files)
    max_digits = len(str(num_files))
    for i, f in enumerate(files, start=1):
        logging.info(f"{i:>{max_digits}}/{num_files}: {f}")

    logging.info("==========================================")
    for f in files:
        logging.info("Processing: %s", f)
        try:
            if not ask_and_replace(old_str=options.args.old_str, new_str=options.args.new_str, path=str(f)):
                break
        except KeyboardInterrupt:
            logging.warning("Interrupted by user.")
            sys.exit(130)
        except Exception as e:
            logging.error(f"Error processing {f}: {e}")

    logging.info("Done.")


def interactive_flake8(options: Options,
                       path: str | os.PathLike[str],
                       diff_choice:     int = 1,
                       ignore_codes: list[str] | None = None,
                       max_line_length: int = 100,
                       changed_color:   str = ANSI_CYAN,
                       deleted_color:   str = ANSI_RED,
                       added_color:     str = ANSI_YELLOW) -> bool:
    """
    1) Run the flake8 API for summary counts.
    2) Shell out to flake8 CLI once to harvest one description per code.
    3) For each code, ask the user; on "yes", call autopep8 to fix only that code.

    Args:
        options:         The parsed command-line options. Contains:
                             - bugbear_choice: Whether to include flake8-bugbear checks.
        path:            Path to the Python file to check.
        diff_choice:     How many context lines to show in the diff (0 = old-style diff,
                         1  = unified diff with 0 context lines,
                         2+ = unified diff with 'diff_choice - 1' context lines).
        ignore_codes:    List of Flake8 codes to ignore (default: empty list).
        max_line_length: Maximum line length for E501 (default: 100).
        changed_color:   Color for unchanged characters in changed lines (default: ANSI_CYAN).
        deleted_color:   Color for deleted characters in original lines (default: ANSI_RED).
        added_color:     Color for added characters in changed lines (default: ANSI_YELLOW).

    Returns:
        False if the user chose to quit during any replacement prompts, True otherwise.
    """
    fallback_logging_config()
    path = ensure_file(path)
    logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("At the top of the function %s(), diff_choice=%s", return_method_name(), diff_choice)
    if ignore_codes is None:
        ignore_codes: list[str] = []
    if not run_flake8(options, path, ignore_codes=ignore_codes, max_line_length=max_line_length):
        logging.info("No flake8 errors—nothing to do.")
        return True
    codes = _gather_flake8_issues(options, path, ignore_codes=ignore_codes, max_line_length=max_line_length)
    fixable_codes = get_autopep8_fixable_codes()
    logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("Autopep8 can fix these codes: %s", fixable_codes)
    touched_code = False
    for code, desc in codes.items():
        if code not in fixable_codes:
            logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("Skipping %s: no autopep8 fixer", code)
            continue
        logging.info("\n→ %s: %s", ANSI_RED + code + ANSI_RESET, ANSI_YELLOW + desc + ANSI_RESET)
        if not ask_and_autopep8(path, code, desc, diff_choice=diff_choice,
                                changed_color=changed_color, deleted_color=deleted_color, added_color=added_color):
            return False
        touched_code = True
    if touched_code:
        logging.info("%sDone. Re-running flake8 to confirm fixes...%s", ANSI_GREEN, ANSI_RESET)
        run_flake8(options, path, ignore_codes=ignore_codes, max_line_length=max_line_length)
    else:
        logging.info("No fixable flake8 codes found or no changes made.")
    return True


def run_mypy(options: Options,
             path: str | os.PathLike[str]) -> None:
    """
    Run basic mypy static analysis on the specified file.
    
    Args:
        options: The parsed command-line options. (Currently unused but included for consistency.)
        path:    Path to the Python file to analyze.
    
    Returns:
        None.
    """
    try:
        from importlib import import_module
        mypy_api = import_module("mypy.api")
    except ModuleNotFoundError:
        logging.error("mypy is not installed.")
        return

    # Note: mypy analyzes files (not raw strings), so we pass the path.
    # This is the most basic run with default settings.
    mypy_stdout, mypy_stderr, mypy_exit = mypy_api.run([str(path)])

    # You can inspect these variables or integrate them with your own logging/handling:
    #   - mypy_stdout: str with human-readable diagnostics
    #   - mypy_stderr: str with internal mypy errors (if any)
    #   - mypy_exit:   int exit code (0 = success, 1 = type issues found, 2 = mypy failure)
    if mypy_stdout:
        logging.info("mypy output:\n%s", mypy_stdout)
    if mypy_stderr:
        logging.error("mypy internal errors:\n%s", mypy_stderr)
    if mypy_exit == 0:
        logging.info("mypy completed successfully with no type issues.")
    elif mypy_exit == 1:
        logging.warning("mypy completed with type issues found.")
    else:
        logging.error("mypy failed with exit code %d.", mypy_exit)


# - Use {str(univ_defs_dir)!r} so Windows backslashes are safely escaped in the string literal.
# - Double the braces around 'univ_defs_dir' in the f-string to keep them literal in the written file.
UNIV_DEFS_SYS_PATH_SCRIPT: str = f'''# Auto-generated helper: ensure the univ_defs directory is on sys.path
import sys
from pathlib import Path

univ_defs_dir = Path({str(Path(__file__).parent.resolve())!r}).resolve()
if not univ_defs_dir.is_dir():
    raise FileNotFoundError(f"Expected univ_defs_dir to be a directory: {{univ_defs_dir}}")
if str(univ_defs_dir) not in sys.path:
    sys.path.append(str(univ_defs_dir))
'''

MYDIFF_SCRIPT: str = r'''from __future__ import annotations
import os
import sys
import argparse
import logging
from pathlib import Path
import univ_defs_sys_path_script  # Appends sys.path with the location of univ_defs.py
import univ_defs as ud

__version__: str = "0.1.0"


class Options:
    """Class that has all global options in one place."""

    def __init__(self) -> None:
        """Initialize the Options class with default values."""
        self.my_name:  str = Path(sys.argv[0]).stem  # The invoked name of this script without the .py extension
        self.log_mode: int = logging.INFO  # Use the -debug command line argument to change to DEBUG.
        self.args: argparse.Namespace | None = None
        self.default_dir: Path = Path.cwd().expanduser().resolve(strict=True)  # Default to current working directory


def parse_arguments(options: Options) -> None:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Diff two files using ud.my_diff().")
    parser.add_argument("orig_path", type=Path, help="Path to original file.")
    parser.add_argument("changed_path", type=Path, help="Path to changed file.")
    parser.add_argument("--diff_choice", type=int, default=1,
                        help="0 = old-style diff, 1 = unified diff with 0 context lines, "
                             "2+ = unified diff with 'diff_choice - 1' context lines")
    parser.add_argument("--changed_color", type=str, default=ud.ANSI_CYAN,
                        help="Color for unchanged characters in changed lines (default: ANSI_CYAN)")
    parser.add_argument("--deleted_color", type=str, default=ud.ANSI_RED,
                        help="Color for deleted characters in original lines (default: ANSI_RED)")
    parser.add_argument("--added_color", type=str, default=ud.ANSI_GREEN,
                        help="Color for added characters in changed lines (default: ANSI_GREEN)")
    parser.add_argument("-v", "--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("-debug", "--debug", action="store_true",
                        help="Enable DEBUG logging.")
    options.args = parser.parse_args()
    if options.args.debug:
        options.log_mode = logging.DEBUG


def main() -> None:
    """Main function."""
    options = Options()
    parse_arguments(options)
    memory_handler = ud.configure_logging(options.my_name, log_level=options.log_mode,
                                          rawlog=True)
    orig_text    = ud.my_fopen(options.args.orig_path)
    changed_text = ud.my_fopen(options.args.changed_path)
    if orig_text is False:
        logging.error(f"Failed to read original file: {os.fspath(options.args.orig_path)}")
        return
    if changed_text is False:
        logging.error(f"Failed to read changed file: {os.fspath(options.args.changed_path)}")
        return
    if orig_text == changed_text:
        return  # Standard diff would show no changes
    ud.my_diff(orig_text, changed_text, options.args.orig_path,
               changed_path=options.args.changed_path, diff_choice=options.args.diff_choice,
               changed_color=options.args.changed_color, deleted_color=options.args.deleted_color,
               added_color=options.args.added_color)
    ud.print_all_errors(memory_handler)
    logging.shutdown()


if __name__ == "__main__":
    main()
'''

MYAUDIT_SCRIPT: str = r'''from __future__ import annotations
import sys
import argparse
import logging
from pathlib import Path

import univ_defs_sys_path_script  # Appends sys.path with the location of univ_defs.py
import univ_defs as ud

__version__: str = "0.1.0"


class Options:
    """Class that has all global options in one place."""

    def __init__(self) -> None:
        """Initialize the Options class with default values."""
        self.my_name:  str = Path(sys.argv[0]).stem  # The invoked name of this script without the .py extension
        self.log_mode: int = logging.INFO  # Use the -debug command line argument to change to DEBUG.
        self.args: argparse.Namespace | None = None
        self.default_dir: Path = Path.cwd().expanduser().resolve(strict=True)  # Default to current working directory


def parse_arguments(options: Options) -> None:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Check Python formatting in a file.")
    parser.add_argument("filepath", type=Path, help="Path to the Python file to check")
    parser.add_argument("--diff_choice", type=int, default=1,
                        help="0 = old-style diff, 1 = unified diff with 0 context lines, "
                             "2+ = unified diff with 'diff_choice - 1' context lines")
    parser.add_argument("--changed_color", type=str, default=ud.ANSI_CYAN,
                        help="Color for unchanged characters in changed lines (default: ANSI_CYAN)")
    parser.add_argument("--deleted_color", type=str, default=ud.ANSI_RED,
                        help="Color for deleted characters in original lines (default: ANSI_RED)")
    parser.add_argument("--added_color", type=str, default=ud.ANSI_GREEN,
                        help="Color for added characters in changed lines (default: ANSI_GREEN)")
    parser.add_argument("-v", "--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("-debug", "--debug", action="store_true",
                        help="Enable DEBUG logging.")
    options.args = parser.parse_args()
    if options.args.debug:
        options.log_mode = logging.DEBUG


def main() -> None:
    """Main function."""
    options = Options()
    parse_arguments(options)
    memory_handler = ud.configure_logging(options.my_name, log_level=options.log_mode,
                                          rawlog=True)
    if not ud.check_python_formatting(options.args.filepath, diff_choice=options.args.diff_choice):
        return
    ud.interactive_flake8(options, options.args.filepath, diff_choice=options.args.diff_choice,
                          ignore_codes=ud.IGNORED_CODES, max_line_length=1000,
                          changed_color=options.args.changed_color, deleted_color=options.args.deleted_color,
                          added_color=options.args.added_color)
    ud.run_mypy(options, options.args.filepath)
    ud.print_all_errors(memory_handler)
    logging.shutdown()


if __name__ == "__main__":
    main()
'''

MULTIREPLACE_SCRIPT: str = r'''from __future__ import annotations
import sys
import argparse
import logging
from pathlib import Path

import univ_defs_sys_path_script  # Appends sys.path with the location of univ_defs.py
import univ_defs as ud

__version__: str = "0.1.0"


class Options:
    """Class that has all global options in one place."""

    def __init__(self) -> None:
        """Initialize the Options class with default values."""
        self.my_name:  str = Path(sys.argv[0]).stem  # The invoked name of this script without the .py extension
        self.log_mode: int = logging.INFO  # Use the -debug command line argument to change to DEBUG.
        self.args: argparse.Namespace | None = None
        self.default_glob_pattern: str = "*"
        self.default_dir: Path = Path.cwd().expanduser().resolve(strict=True)  # Default to current working directory


def parse_arguments(options: Options) -> None:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Find files by glob and call ud.ask_and_replace() on each until it returns False.")
    parser.add_argument("old_str",
                        help="The text to be replaced in the files.")
    parser.add_argument("new_str",
                        help="The text to replace the old_str.")
    parser.add_argument("glob_pattern", nargs="?", default=options.default_glob_pattern, metavar="GLOB",
                        help=f'Glob pattern of files to edit (default: "{options.default_glob_pattern}"). Example: "*.py"')
    parser.add_argument("--dir", "-d", type=Path, default=options.default_dir, metavar="DIR",
                        help=f"Directory to search in (defaults to current working directory: {options.default_dir}).")
    parser.add_argument("--recursive", "-r", action="store_true",
                        help="Search recursively in subdirectories.")
    parser.add_argument("-v", "--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("-debug", "--debug", action="store_true",
                        help="Enable DEBUG logging.")
    options.args = parser.parse_args()
    if options.args.debug:
        options.log_mode = logging.DEBUG


def main() -> None:
    """Main function."""
    options = Options()
    parse_arguments(options)
    memory_handler = ud.configure_logging(options.my_name, log_level=options.log_mode,
                                          rawlog=True)
    ud.multireplace(options)
    ud.print_all_errors(memory_handler)
    logging.shutdown()


if __name__ == "__main__":
    main()
'''

DEFAULT_EXCLUDE_DIRS: set[str] = {".git", "__pycache__", ".venv", "venv", "build", "dist"}

TREEVIEW_SCRIPT: str = r'''#!/usr/bin/env python3
from __future__ import annotations

import sys
import argparse
import logging
from pathlib import Path

import univ_defs_sys_path_script  # Appends sys.path with the location of univ_defs.py
import univ_defs as ud

__version__: str = "0.1.1"


class Options:
    """Class that has all global options in one place."""

    def __init__(self) -> None:
        """Initialize the Options class with default values."""
        self.my_name:                    str = Path(sys.argv[0]).stem  # The invoked name of this script without the .py extension
        self.default_exclude_dirs:  set[str] = set(ud.DEFAULT_EXCLUDE_DIRS)
        self.default_dir:               Path = Path.cwd().expanduser().resolve(strict=True)  # Default to current working directory
        self.log_mode:                   int = logging.INFO  # Use the -debug command line argument to change to DEBUG.
        self.args: argparse.Namespace | None = None


def parse_arguments(options: Options) -> None:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Print a tree view of the specified directory.")
    parser.add_argument("directory", type=Path, nargs="?", default=options.default_dir,
                        help=f"Directory to search in (defaults to current working directory: {options.default_dir}).")
    parser.add_argument("--no-colors", action="store_true",
                        help="Do not use colors in the output.")
    parser.add_argument("--exclude-dirs", action="extend", nargs="+", default=None,
                        help=f"Directory name to exclude (can be given multiple times). Any directories given will be added to the default set: {sorted(options.default_exclude_dirs)}")
    parser.add_argument("-v", "--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("-debug", "--debug", action="store_true",
                        help="Enable DEBUG logging.")
    options.args = parser.parse_args()
    options.args.exclude_dirs = set(ud.DEFAULT_EXCLUDE_DIRS) | set(options.args.exclude_dirs or [])
    if options.args.debug:
        options.log_mode = logging.DEBUG


def main() -> None:
    """Main function."""
    options = Options()
    parse_arguments(options)
    memory_handler = ud.configure_logging(options.my_name, log_level=options.log_mode,
                                          rawlog=True)
    logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("Directory: %s", options.args.directory)
    state = {
        "excluded_dirs"   : options.args.exclude_dirs,
        "already_printed" : set(),
        "my_filepath"     : Path(__file__).expanduser().resolve(),
    }
    ud.treeview_new_files(options.args.directory, use_colors=not options.args.no_colors, state=state)
    ud.print_all_errors(memory_handler)
    logging.shutdown()


if __name__ == "__main__":
    main()
'''

PRINTALL_SCRIPT: str = r'''from __future__ import annotations

import os
import sys
import argparse
import io
import logging
import re
from pathlib import Path
from collections.abc import Iterable

import tokenize  # stdlib

import univ_defs_sys_path_script  # Appends sys.path with the location of univ_defs.py
import univ_defs as ud

__version__: str = "0.1.1"


class Options():
    """Class that has all global options in one place."""

    def __init__(self) -> None:
        """Initialize the Options class with default values."""
        self.my_name:                    str = Path(sys.argv[0]).stem  # The invoked name of this script without the extension
        self.default_exclude_dirs:  set[str] = set(ud.DEFAULT_EXCLUDE_DIRS)
        self.log_mode:                   int = logging.INFO  # Use -debug to change to logging.DEBUG.
        self.args: argparse.Namespace | None = None


def parse_arguments(options: Options) -> None:
    """
    Parse command-line arguments.
    """
    parser = argparse.ArgumentParser(description="Search Python files and print full logical statements that match a pattern.")
    parser.add_argument("paths", nargs="+", type=Path,  # parse as Path at the boundary
                        help="Files and/or directories to search.")
    parser.add_argument("-p", "--pattern", required=True, help="Search pattern (string or regex).")
    parser.add_argument("-E", "--regex", action="store_true",
                        help="Treat the pattern as a regular expression.")
    parser.add_argument("-i", "--ignore-case", action="store_true", help="Case-insensitive match.")
    parser.add_argument("-n", "--line-numbers", action="store_true",
                        help="Show line numbers in output blocks.")
    parser.add_argument("-r", "--recursive", action="store_true", help="Recurse into directories.")
    parser.add_argument("--no-glob", action="store_true",
                        help="Do not automatically filter for *.py inside directories.")
    parser.add_argument("--exclude-dirs", action="extend", nargs="+", default=None,
                        help=f"Directory name to exclude (can be given multiple times). Any directories given will be added to the default set: {sorted(options.default_exclude_dirs)}")
    parser.add_argument("-v", "--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("-debug", "--debug", action="store_true", help="Enable debug logging.")
    options.args = parser.parse_args()
    options.args.exclude_dirs = set(ud.DEFAULT_EXCLUDE_DIRS) | set(options.args.exclude_dirs or [])
    if options.args.debug:
        options.log_mode = logging.DEBUG


def _is_excluded(path: Path, excluded: set[str]) -> bool:
    """Return True if any ancestor directory name is in the excluded set."""
    # Only compare directory names (Path.name); do not do string-prefix checks.
    return any(parent.name in excluded for parent in path.parents)


def iter_files(paths: Iterable[str | os.PathLike[str]],
               recursive: bool,
               excluded: set[str],
               only_py: bool) -> Iterable[Path]:
    """
    Yield files from given paths, respecting recursion and directory excludes.

    Parameters that represent paths accept str | os.PathLike[str] at the boundary.
    Returned paths are pathlib.Path instances.
    """
    pattern = "*.py" if only_py else "*"

    for raw in paths:
        base = Path(raw)

        if ud.safe_is_dir(base):
            if recursive:
                # Prefer Path.rglob for recursion (portable across 3.9+).
                for f in base.rglob(pattern):
                    if ud.safe_is_file(f) and not _is_excluded(f, excluded):
                        yield f
            else:
                for f in base.glob(pattern):
                    if ud.safe_is_file(f) and not _is_excluded(f, excluded):
                        yield f
        else:
            # Single file (or non-existent); yield if it meets filters.
            if ud.safe_is_file(base) and (not only_py or base.suffix == ".py") and not _is_excluded(base, excluded):
                yield base


def _statement_spans(src: str) -> list[tuple[int, int]]:
    """Return list of (start_line, end_line) for each logical statement in the source."""
    reader = io.StringIO(src).readline
    spans: list[tuple[int, int]] = []
    depth = 0
    start_line: int | None = None

    for tok in tokenize.generate_tokens(reader):
        tok_type, tok_str, start, end, _ = tok

        # establish start at first meaningful token of a statement
        if start_line is None and tok_type not in (tokenize.NL, tokenize.COMMENT,
                                                   tokenize.INDENT, tokenize.DEDENT,
                                                   tokenize.ENDMARKER):
            start_line = start[0]

        if tok_type == tokenize.OP:
            if tok_str in "([{":
                depth += 1
            elif tok_str in ")]}":
                depth -= 1
            elif tok_str == ";" and depth == 0 and start_line is not None:
                spans.append((start_line, start[0]))
                start_line = None
                continue

        if tok_type == tokenize.NEWLINE and depth == 0:
            if start_line is not None:
                spans.append((start_line, end[0]))
            start_line = None

        if tok_type == tokenize.ENDMARKER:
            break

    return spans


def _mask_strings_and_comments(src: str) -> str:
    """Return source with STRING and COMMENT contents replaced by spaces (preserving positions)."""
    lines = src.splitlines(keepends=True)
    matrix = [list(line) for line in lines]
    reader = io.StringIO(src).readline
    for tok in tokenize.generate_tokens(reader):
        tok_type, _tok_str, start, end, _ = tok
        if tok_type in (tokenize.STRING, tokenize.COMMENT):
            (sr, sc), (er, ec) = start, end
            # mask all full lines covered by the token
            for r in range(sr - 1, er - 1):
                cstart = sc if r == sr - 1 else 0
                for c in range(cstart, len(matrix[r])):
                    if matrix[r][c] != "\n":
                        matrix[r][c] = " "
            # final line (partial)
            r = er - 1
            if 0 <= r < len(matrix):
                cstart = 0 if sr != er else sc
                for c in range(cstart, ec):
                    if matrix[r][c] != "\n":
                        matrix[r][c] = " "
    return "".join("".join(row) for row in matrix)


def _merge_spans(spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Merge overlapping or adjacent spans."""
    if not spans:
        return []
    spans = sorted(spans)
    merged: list[list[int]] = [[spans[0][0], spans[0][1]]]
    for s, e in spans[1:]:
        last = merged[-1]
        if s <= last[1] + 1:
            last[1] = max(last[1], e)
        else:
            merged.append([s, e])
    return [(s, e) for s, e in merged]


def _extract_blocks(src: str, spans: list[tuple[int, int]], show_line_numbers: bool) -> list[str]:
    """Return pretty-printed blocks for each span."""
    lines = src.splitlines()
    if show_line_numbers:
        max_line = max((e for _, e in spans), default=0)
        width = len(str(max_line))
    blocks: list[str] = []
    for s, e in spans:
        segment = lines[s - 1:e]
        if show_line_numbers:
            segment = [f"{i:>{width}} | {line}" for i, line in zip(range(s, e + 1), segment)]
        blocks.append("\n".join(segment))
    return blocks


def search_file(path: str | os.PathLike[str],
                pattern: str, *,
                regex: bool,
                ignore_case: bool,
                show_line_numbers: bool) -> list[str]:
    """Return matching blocks for a single file."""
    p    = ud.ensure_file(path)
    text = ud.my_fopen(p, suppress_errors=True)
    if not isinstance(text, str):
        logging.warning("Skipping %s (unreadable or non-text).", os.fspath(p))
        return []

    masked = _mask_strings_and_comments(text)
    flags  = re.IGNORECASE if ignore_case else 0
    pat    = re.compile(pattern if regex else re.escape(pattern), flags)

    # lines that contain a match (in code, not in strings/comments)
    hit_lines: set[int] = set()
    for m in pat.finditer(masked):
        before = masked[:m.start()]
        line = before.count("\n") + 1
        hit_lines.add(line)

    if not hit_lines:
        return []

    # map lines to statement spans
    spans = _statement_spans(text)
    line_to_span: dict[int, tuple[int, int]] = {}
    for s, e in spans:
        for ln in range(s, e + 1):
            line_to_span[ln] = (s, e)

    chosen: list[tuple[int, int]] = []
    for ln in sorted(hit_lines):
        sp = line_to_span.get(ln)
        if sp:
            chosen.append(sp)

    chosen = _merge_spans(chosen)
    return _extract_blocks(text, chosen, show_line_numbers)


def main() -> None:
    """
    Main function.
    """
    options = Options()
    parse_arguments(options)
    logging.basicConfig(level=options.log_mode,
                        format="%(asctime)s - %(levelname)s - %(message)s",
                        datefmt="%Y-%m-%d %H:%M:%S")

    any_hits = False

    for file in iter_files(options.args.paths, options.args.recursive,
                           options.args.exclude_dirs, only_py=not options.args.no_glob):
        results = search_file(file, options.args.pattern, regex=options.args.regex,
                              ignore_case=options.args.ignore_case,
                              show_line_numbers=options.args.line_numbers)
        if results:
            any_hits = True
            print(f"# {os.fspath(file)}")
            for block in results:
                print(block)
                print()  # extra newline between blocks

    if not any_hits:
        logging.info("No matches found.")

    logging.shutdown()


if __name__ == "__main__":
    main()
'''

SETUP_CARTOPY_SCRIPT: str = r'''import os
import matplotlib.pyplot as plt
import cartopy
cartopy.config['data_dir'] = os.getenv('CARTOPY_DATA_DIR', cartopy.config.get('data_dir'))

fig, ax = plt.subplots(subplot_kw={'projection': cartopy.crs.PlateCarree()})
ax.coastlines('110m')    # Explicitly specify resolution to ensure pre-loading
ax.add_feature(cartopy.feature.OCEAN)  # Example color; adjust as needed
ax.add_feature(cartopy.feature.LAND)   # Example color; adjust as needed

# Force feature download
temp_filename = "cartopy_test_map.png"
plt.savefig(temp_filename)
os.remove(  temp_filename)
'''


def verify_script(options: Options, thepath: str | os.PathLike[str], thescript: str) -> None:
    """
    Ensure that 'thepath' exists and contains exactly 'thescript'.
    - If 'thepath' does not exist or is not a file, it will be created and populated.
    - If it exists but its contents differ, it will be overwritten.
    - Otherwise, nothing happens.
    """
    # Check if it exists and is a file
    thepath = ensure_path(thepath)
    if not safe_is_file(thepath):
        if safe_is_dir(thepath):
            if not options.rawlog:
                logging.error(f"Expected a file at {os.fspath(thepath)}, but it is a directory.")
            return
        thepath.write_text(thescript, encoding=DEFAULT_ENCODING)
        if not options.rawlog:
            logging.info("Creating %s with the specified script.", os.fspath(thepath))
        return

    # It is a file: read and compare
    existing = thepath.read_text(encoding=DEFAULT_ENCODING)
    # Overwrite if different
    if existing != thescript:
        if not options.rawlog:
            logging.info("Contents of %s differ from the specified script in %s as follows:", os.fspath(thepath), __file__)
            my_diff(existing, thescript, thepath, diff_choice=1)
            logging.info("Overwriting %s with the specified script.", os.fspath(thepath))
        thepath.write_text(thescript, encoding=DEFAULT_ENCODING)


def decode_utf8(raw_bytes: bytes, path: str = "input string") -> str | None:
    """
    If the file at 'path' is valid UTF-8 without lone C1 controls,
    return the decoded string. Otherwise, return None.
    """
    fallback_logging_config()
    try:
        text = raw_bytes.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("%s failed to decode as UTF‑8.", path)
        return None
    if any(0x0080 <= ord(ch) <= 0x009F for ch in text):
        logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("%s contains lone C1 controls, not valid UTF-8.", os.fspath(path))
        return None
    logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("%s decoded as valid UTF‑8.", os.fspath(path))
    return text


def decode_cp1252(raw_bytes: bytes, path: str = "input string") -> str | None:
    """
    Attempt to decode CP1252 bytes and return as a string.
    If it fails, return None.
    """
    fallback_logging_config()
    try:
        text = raw_bytes.decode("cp1252", errors="strict")
        logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("%s decoded as valid CP1252.",
                                                                          os.fspath(path))
        return text
    except UnicodeDecodeError:
        logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("%s failed to decode as CP1252.", os.fspath(path), exc_info=True)
        return None


def contains_mojibake(text: str) -> bool:
    """Use ftfy.badness.is_bad() to detect any likely mojibake in the text."""
    import ftfy
    fallback_logging_config()
    try:
        mojibake_present = ftfy.badness.is_bad(text)
    except Exception:  # Catch any unexpected errors from ftfy without crashing
        logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("Failed to check for mojibake.", exc_info=True)
        mojibake_present = False
    logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("Mojibake present: %s", mojibake_present)
    # I HAVEN'T TRIED THIS NEXT LINE, BUT IT MIGHT CAUSE FEWER FALSE POSITIVES:
    # return ftfy.badness(text) > 1
    return mojibake_present


def fix_text(current_text: str, path: str | os.PathLike[str], raw_bytes: bytes) -> str | None:
    """
    Fix mojibake in a string using ftfy.fix_encoding().
    """
    import ftfy
    fallback_logging_config()
    path = ensure_file(path)
    logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("Checking %s for mojibake.",
                                                                      os.fspath(path))
    if not contains_mojibake(current_text):
        return None
    try:
        fixed = ftfy.fix_encoding(current_text)
    except Exception:  # Catch any unexpected errors from ftfy without crashing
        logging.error("Failed to fix mojibake in %s.", os.fspath(path), exc_info=True)
        return None
    # If logging level is set to DEBUG, show my diff of original vs fixed:
    if logging.getLogger().isEnabledFor(logging.DEBUG):
        try:
            # Mangle the original string to simulate browser encoding issues:
            mangled_original = raw_bytes.decode("cp1252", errors="replace")
            my_diff(mangled_original, fixed, path)
        except Exception:  # Catch any unexpected errors from decoding but don't crash.
            logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("Could not simulate browser mangling in %s.", os.fspath(path), exc_info=True)
    return fixed


def ensure_utf8_meta(html: str) -> str:
    """
    Ensure the HTML text has a <meta charset="utf-8"> tag.
    If one already exists—either as a charset attribute or
    as an http-equiv Content-Type declaration—normalize it to
    <meta charset="utf-8">. Otherwise, insert that tag right
    after the opening <head> tag.
    """
    # 1) Normalize any <meta ... charset=...> to <meta charset="utf-8">
    #    This covers both <meta charset="XYZ"> and
    #    <meta http-equiv="Content-Type" content="text/html; charset=XYZ">
    def _replace_charset_attr(match: re.Match) -> str:
        """
        Replace a <meta> tag with a charset attribute
        with a normalized <meta charset="utf-8"> tag.
        """
        # Always produce exactly: <meta charset="utf-8">
        return '<meta charset="utf-8">'

    # Pattern A: <meta ... charset=XYZ ...>
    pattern_a = r'<meta\b[^>]*\bcharset=["\']?[^"\'>\s]+["\']?[^>]*>'
    # Pattern B: <meta ... http-equiv=["\']Content-Type["\'] ... content="...; charset=XYZ"...>
    pattern_b = (r'<meta\b[^>]*\bhttp-equiv=["\']?Content-Type["\']?[^>]*'
                 r'\bcontent=["\'][^"\'>]*;\s*charset=[^"\'>]+["\'][^>]*>')

    if re.search(pattern_a, html, flags=re.IGNORECASE) or \
       re.search(pattern_b, html, flags=re.IGNORECASE):
        # First collapse any Pattern B occurrences
        html = re.sub(pattern_b, _replace_charset_attr, html, flags=re.IGNORECASE)
        # Then collapse any remaining Pattern A
        html = re.sub(pattern_a, _replace_charset_attr, html, flags=re.IGNORECASE)
        return html

    # 2) If no existing meta‐charset, insert one just after <head>
    return re.sub(r'(<head\b[^>]*>)',
                  r'\1\n    <meta charset="utf-8">',
                  html, count=1, flags=re.IGNORECASE)


def my_atomic_write(filepath: str | Path | os.PathLike[str], data: str | bytes | bytearray,
                    write_mode: Literal["w", "a"], encoding: str = DEFAULT_ENCODING,
                    lock_timeout: float = None,  # seconds to wait for lock (None = forever)
                    ) -> None:
    """
    Atomically write 'data' to 'filepath' with an advisory lock.

    - If write_mode="a" and file exists, data is appended.
    - If write_mode="a" and file does *not* exist, file is created.
    - A '.lock' file beside 'filepath' prevents concurrent writers.

    Args:
        filepath:     Path to the file to write.
        data:         Data to write (str or bytes).
        write_mode:   "w" for overwrite, "a" for append.
        encoding:     Encoding to use for text data (default: DEFAULT_ENCODING).
        lock_timeout: Maximum time to wait for the lock (default: None, meaning wait indefinitely).

    Returns:
        None: The file is written atomically.

    Raises:
        RuntimeError: If the lock cannot be acquired within the specified timeout.
    """
    from atomicwrites import atomic_write
    from filelock import FileLock, Timeout
    path = ensure_path(filepath)
    # ensure parent directory exists
    path.parent.mkdir(parents=True, exist_ok=True)
    # choose text or binary mode
    is_bytes      = isinstance(data, (bytes, bytearray))
    mode          = write_mode + ("b" if is_bytes else "")
    text_enc      = None if is_bytes else encoding
    lock_path_str = os.fspath(path) + ".lock"
    lock          = FileLock(lock_path_str, timeout=lock_timeout)
    try:
        with lock:
            # atomicwrites will write to a temp file in the same dir then os.replace()
            # overwrite=(write_mode=="w") means "w" replaces, "a" appends
            with atomic_write(path, mode=mode, overwrite=(write_mode == "w"),
                              encoding=text_enc, preserve_mode=True) as f:
                f.write(data)
    except Timeout:
        raise RuntimeError(f"Could not acquire lock on {lock_path_str!r} within {lock_timeout} seconds")


def fix_mojibake(filepath: str | os.PathLike[str], make_backup: bool = True,
                 dry_run: bool = False) -> None:
    """
    Fix mojibake in a text file, recoding from CP1252 to UTF-8 if necessary.
    If the file is already valid UTF-8, it will only fix mojibake.
    """
    import datetime as dt
    fallback_logging_config()
    filepath = ensure_file(filepath)
    if not safe_is_file(filepath):
        logging.error(f"{os.fspath(filepath)} is not a file")
        return

    try:
        with open(filepath, "rb") as f:
            raw_bytes = f.read()
    except Exception:  # Catch any unexpected errors from reading the file without crashing.
        logging.error(f"Failed to read {os.fspath(filepath)}.", exc_info=True)
        return

    original_text =      decode_utf8(raw_bytes, filepath) \
                    or decode_cp1252(raw_bytes, filepath)
    if original_text is None:
        return

    # Start with the original text but keep it in memory unmodified.
    current_text = original_text

    # Either way, check for mojibake and fix it if necessary
    maybe_fixed = fix_text(current_text, filepath, raw_bytes)
    if maybe_fixed is not None:
        current_text = maybe_fixed
        logging.info("✔ Fixed mojibake: %s", os.fspath(filepath))

    # If the text is from an HTML file, ensure it has a UTF-8 meta tag
    if filepath.suffix.casefold() in HTML_EXTENSIONS_SET:
        current_text = ensure_utf8_meta(current_text)

    # If we have fixed the text, write it back
    if current_text != original_text:
        if dry_run:
            logging.info("Dry run: would write changes to %s", os.fspath(filepath))
        else:
            if make_backup:
                current_datetime = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
                backup_path_str = f"{os.fspath(filepath)}_{current_datetime}.bak"
                try:
                    filepath.rename(backup_path_str)
                    logging.info("Backup created: %s", backup_path_str)
                except OSError:
                    logging.exception("Failed to create backup for %s.", os.fspath(filepath))
                    return
            my_atomic_write(filepath, current_text, "w", encoding="utf-8")
            logging.info("✔ Successfully fixed mojibake in %s", os.fspath(filepath))


def treeview_new_files(directory:      str | os.PathLike[str],
                       last_file_path: str | os.PathLike[str] | None = None,
                       last_mtime: float | None = None, maxlines: int = 0,
                       use_colors: bool = True, print_root: bool = True,
                       prefix: str = "", is_last: bool = True, level: int = 0,
                       state: dict = None, probe_only: bool = False) -> bool:
    """
    Recursively scan the directory, print the contents of files newer than last_file_path (if provided- if so store its modification date in last_mtime). Return True if any relevant files are found.

    Args:
        directory:      The directory to scan.
        last_file_path: The optional path to a chosen file. Only files newer than this will be printed.
        last_mtime:     The modification time of the last_file_path. If None, all files will be
                        considered.
        maxlines:       The maximum number of lines to read from each file. 0 means don't read at all,
                        -1 means read all lines, otherwise read up to maxlines (default 0).
        use_colors:     Whether to use ANSI color codes in the output (default True).
        print_root:     If True, print the root directory name (default True).
        prefix:         The prefix to use for logging output (default '').
        is_last:        Whether this is the last item in the current level (default True).
        level:          The current recursion level (default 0).
        state:          A dictionary to maintain state across recursive calls (default None).
        probe_only:     If True, do not print file contents, just check for existence of relevant
                        files (default False).

    Returns:
        True if any relevant files are found or the directory itself is newer than last_mtime,
        False otherwise.

    Raises:
        None: Catches exceptions, logs an error and returns False if the directory is not a valid
              directory or does not exist.
    """
    import datetime as dt
    fallback_logging_config(rawlog=True)

    directory = ensure_path(directory)
    if not safe_exists(directory):
        logging.error(f"{prefix}└── [Directory does not exist: {os.fspath(directory)}]")
        return False
    if not safe_is_dir(directory):
        logging.error(f"{prefix}└── [Not a directory: {os.fspath(directory)}]")
        return False

    if last_file_path is None:
        last_mtime = 0
        logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("%sNo last file path provided, considering all files.", prefix)
    else:
        last_file_path = ensure_path(last_file_path)
        if not safe_exists(last_file_path):
            logging.error("%s└── [Last file path does not exist: %s]", prefix, os.fspath(last_file_path))
            return False
        last_mtime          = safe_mtime(last_file_path)
        if last_mtime is None:
            logging.error("%s└── [Could not get mtime for last file path: %s]",
                          prefix, os.fspath(last_file_path))
            return False
        last_mtime_readable = dt.datetime.fromtimestamp(last_mtime).strftime("%Y-%m-%d %H:%M:%S")
        logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("%sLast file path: %s (mtime: %s)",
                                                                          prefix,
                                                                          os.fspath(last_file_path), last_mtime_readable)

    if use_colors:
        reset_color = ANSI_RESET
        dir_color   = ANSI_CYAN
    else:
        reset_color = ""
        dir_color   = ""

    # Get the modification time of the directory itself
    dir_mtime      = safe_mtime(directory)
    current_is_new = dir_mtime > (last_mtime or 0)

    if state is None:
        state = {"excluded_dirs"   : {"__pycache__"},
                 "already_printed" : set(),
                 "my_filepath"     : ensure_path(__file__)}
    already_printed = state['already_printed']
    excluded_dirs   = state['excluded_dirs']
    my_filepath     = state['my_filepath']

    if not probe_only:
        already_printed.add(directory)

    has_relevant_files = False  # Flag to indicate if current directory has relevant files

    try:
        entries = sorted(directory.iterdir(), key=lambda e: e.name.casefold())
    except PermissionError:
        logging.error(f"{prefix}└── [Permission Denied]")
        return False

    # Filter out entries that should be skipped at the directory level
    entries = [
        entry for entry in entries
        if not (
            (safe_is_file(entry) and (
                entry == last_file_path or
                entry == my_filepath    or
                entry.name.startswith(".")
            )) or
            ((safe_is_dir_entry := safe_is_dir(entry)) and entry.name in excluded_dirs) or
            (safe_is_dir_entry and entry.expanduser().resolve() in already_printed)
        )
    ]

    # Sort entries: directories first, then files, case-insensitive
    entries = sorted(entries, key=lambda e: (not safe_is_dir(e), e.name.casefold()))

    # Collect relevant entries
    relevant_entries = []
    subdirectories = []

    for entry in entries:
        if safe_is_file(entry):
            file_mtime = safe_mtime(entry)
            if file_mtime > last_mtime:
                relevant_entries.append(entry)
                has_relevant_files = True
        elif safe_is_dir(entry):
            sub_has_relevant = treeview_new_files(
                entry,
                last_file_path=last_file_path,
                last_mtime=last_mtime,
                maxlines=maxlines,
                use_colors=use_colors,      # use_colors doesn't matter in probe mode
                prefix=prefix,              # prefix doesn't matter in probe mode
                is_last=False,              # ignored in probe mode
                level=level + 1,
                state=state,
                probe_only=True             # probe mode: do not print contents
            )
            # Consider the subdirectory's own mtime
            sub_is_new = safe_mtime(entry) > last_mtime
            if sub_has_relevant or sub_is_new:
                subdirectories.append(entry)
            if sub_has_relevant:
                has_relevant_files = True

    # Sort subdirectories and relevant entries by name, case-insensitive
    subdirectories.sort(  key=lambda p: p.name.casefold())
    relevant_entries.sort(key=lambda p: p.name.casefold())

    should_show = has_relevant_files or current_is_new
    if probe_only:
        return should_show

    if should_show:
        if level > 0:
            # Print the directory name with a connector only if it's not the root directory
            connector = "└── " if is_last else "├── "
            logging.info(f"{prefix}{connector}{dir_color}{directory.name}/{reset_color}")

            # Update the prefix for child entries
            child_prefix = prefix + ("    " if is_last else "│   ")
        else:
            # For root level, do not print the directory name unless print_root is True
            child_prefix = prefix
            if print_root:
                # Print the root directory name with a connector
                logging.info(f"{dir_color}{directory.name}/{reset_color}")

        # Print subdirectories first
        printable_subdirs = [
            d for d in subdirectories
            if d.name not in excluded_dirs and d.expanduser().resolve() not in already_printed
        ]
        for i, subdir in enumerate(printable_subdirs):
            is_sub_last = (i == len(printable_subdirs) - 1) and (len(relevant_entries) == 0)
            # Only scan the subdirectory if it isn't excluded
            if subdir.name not in excluded_dirs and subdir.expanduser().resolve() not in already_printed:
                treeview_new_files(subdir, last_file_path=last_file_path, last_mtime=last_mtime,
                                   maxlines=maxlines, use_colors=use_colors, prefix=child_prefix,
                                   is_last=is_sub_last, level=level + 1, state=state)

        # Print relevant files next
        for i, file_entry in enumerate(relevant_entries):
            # Determine if this is the last file to adjust connector
            is_file_last = (i == len(relevant_entries) - 1)
            file_connector = "└── " if is_file_last else "├── "
            contents_str = f"{file_entry.name} contents:" if maxlines != 0 else f"{file_entry.name}"
            logging.info(f"{child_prefix}{file_connector}{contents_str}")
            try:
                if maxlines != 0:  # Only open if not disabled
                    with open(file_entry, "r", encoding=DEFAULT_ENCODING) as f:
                        if maxlines > 0:
                            # Read only up to maxlines
                            lines = []
                            for i, line in enumerate(f):
                                if i >= maxlines:
                                    break
                                lines.append(line.rstrip("\n"))
                        else:  # maxlines == -1 → read all
                            lines = [line.rstrip("\n") for line in f]
                    # Indent file contents for better readability
                    indented_contents = "\n".join(f"{child_prefix}    {line}" for line in lines)
                    logging.info(indented_contents)
            except Exception:  # Catch any unexpected errors from reading the file without crashing.
                logging.exception(f"{child_prefix}    Error reading '{file_entry}'.")
            if maxlines != 0:  # Add an empty line for separation, but only if printing contents
                logging.info("")

    return should_show


def ensure_docker_installed() -> None:
    """Check if the Docker CLI is installed; if not, raise an error."""
    import shutil
    if shutil.which("docker") is not None:
        return
    my_critical_error("Docker CLI not found. Please install Docker: https://docs.docker.com/get-docker/")


def ensure_daemon_running() -> None:
    """Check if the Docker daemon is running; if not, attempt to start it."""
    info = my_popen(["docker", "info"])
    if info.success:
        return
    logging.info("Docker daemon not running; attempting to start it...")
    if sys.platform.startswith("linux"):
        start = my_popen(["sudo", "systemctl", "start", "docker"])
        if not start.success:
            start = my_popen(["sudo", "service", "docker", "start"])
        if not start.success:
            my_critical_error(f"Could not start Docker daemon:\n{start.stderr}")
    elif sys.platform == "darwin":
        launcher = my_popen(["open", "-a", "Docker"])
        if not launcher.success:
            my_critical_error("Failed to launch Docker Desktop. Please start it from your Applications folder.")
        # Wait for the daemon to start...
        for _ in range(10):
            time.sleep(3)
            info = my_popen(["docker", "info"])
            if info.success:
                logging.info("Docker daemon is running!")
                return
        my_critical_error("Docker Desktop did not finish starting within 30 seconds.\nPlease open Docker Desktop manually.")
    else:
        my_critical_error(f"Unsupported OS for auto-starting Docker: {sys.platform}")


def ensure_image_built(image: str, *,
                       dockerfile: Path | None = None,
                       build_dir:  Path | None = None,
                       build_cmd:   str | None = None) -> None:
    """
    Ensure that a Docker image with the given name exists; if not, build it.
    You can specify either a dockerfile (whose first line is a comment with the build command)
    or a build_cmd (and optionally a build_dir). If both dockerfile and build_cmd are None,
    the function will raise an error.
    """
    inspect = my_popen(["docker", "image", "inspect", image])
    if inspect.success:
        return

    if build_cmd is None:
        if dockerfile is None:
            my_critical_error(f"Image {image} missing and no build_cmd/dockerfile provided")
        try:
            first = open(dockerfile, "r").readline().strip()
        except OSError:
            my_critical_error(f"Cannot read {os.fspath(dockerfile)} to build {image}")
        if not first.startswith("#"):
            my_critical_error(f"No build command found in {os.fspath(dockerfile)}")
        build_cmd = first.lstrip("# ").strip()
        if build_dir is None:
            build_dir = dockerfile.parent

    # run build_cmd in build_dir
    import shlex
    full_cmd = f"cd {shlex.quote(os.fspath(build_dir or Path.cwd()))} && {build_cmd}"
    build = my_popen(["sh", "-c", full_cmd])
    if not build.success:
        my_critical_error(f"Failed to build {image}:\n{build.stderr}")


def run_with_docker_fixes(base_args: list[str], *,
                          ensure_build:         Callable[[], None]  | None = None,
                          extra_fixes: Iterable[Callable[[], None]] | None = None) -> MyPopenResult:
    """
    Run a command (typically 'docker run ...') and if it fails, attempt to fix
    common Docker issues (like Docker not installed or daemon not running) and retry.
    """
    fixes = [ensure_docker_installed, ensure_daemon_running]
    if ensure_build is not None:
        fixes.append(ensure_build)
    if extra_fixes:
        fixes.extend(extra_fixes)

    last = None
    for fix in fixes:
        last = my_popen(base_args)
        if last.success:
            return last
        logging.info("docker run failed; attempting to fix: %s", fix.__name__)
        fix()

    last = my_popen(base_args)
    if last.success:
        return last
    my_critical_error(f"After applying all fixes, still failed:\n{last.stderr}")


def check_if_command_exists(command: str) -> bool:
    """
    Check if a command exists on the system.

    Args:
        command: The command to check.

    Returns:
        True if the command exists, False otherwise.
    """
    import subprocess
    return subprocess.run(["which", command], capture_output=True).returncode == 0


def open_terminal_and_run_command(the_command: str, close_after: bool = False,
                                  maximize_window: bool = False) -> None:
    """Open a GNOME terminal, source ~/.bashrc (via bash -i), run the_command,
    and optionally close or keep the window open. Optionally, maximize it."""
    import subprocess
    fallback_logging_config()
    logging.info("Opening terminal and running '%s'...", the_command)
    if sys.platform.startswith("linux"):
        terminal_args = ["gnome-terminal"]
    else:
        raise NotImplementedError(f"The function {return_method_name()} is only implemented for Linux, not for {sys.platform}")
    # if maximize_window:  # Disabled because in Ubuntu this causes the title bar to disappear.
    #     # either of these works; here we use both for clarity
    #     terminal_args += ["--window", "--maximize"]
    # Now tell bash to run the command, then exit or hand off to an interactive shell
    if close_after:
        bash_cmd = f"{the_command}; exit"
    else:
        bash_cmd = f"{the_command}; exec bash"
    terminal_args += ["--", "bash", "-ic", bash_cmd]
    subprocess.Popen(terminal_args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
# FIX PROBLEM WITH MAXIMIZING: https://chatgpt.com/share/68bcd45e-a2fc-8006-aeba-50dd177f1da6
# ALSO, ON STARTUP, TERMINAL WINDOWS CLOSE IMMEDIATELY AFTER I CTRL-C THEM EVEN IF close_after=False
# POSSIBLY RELATED: https://askubuntu.com/questions/1409826/gnome
# def open_terminal_and_run_command(cmd, close_after=False, keep_titlebar=True):
#     import subprocess, time
#     bash_cmd = f"{cmd}; exit" if close_after else f"{cmd}; exec bash"
#     # Start *not* maximized:
#     p = subprocess.Popen(["gnome-terminal", "--class=myterm", "--", "bash", "-ic", bash_cmd])
#     if keep_titlebar:
#         time.sleep(0.3)  # small delay so the window exists
#         # On X11: maximize after mapping (keeps decorations)
#         subprocess.run(["wmctrl", "-x", "-r", "myterm", "-b", "add,maximized_vert,maximized_horz"], check=False)


def get_effective_free_memory() -> float:
    """Return the "effective" free memory in bytes: free memory plus buffers plus cache."""
    if sys.platform.startswith("linux"):
        # NOTE: If your kernel supports MemAvailable, you could use that instead for a more accurate measure of usable memory
        info = {}
        with open("/proc/meminfo", "r") as f:
            for line in f:
                parts     = line.split()
                key       = parts[0].rstrip(":")
                value_kb  = int(parts[1])
                info[key] = value_kb

        mem_free_kb = info.get("MemFree", 0)
        buffers_kb  = info.get("Buffers", 0)
        cached_kb   = info.get("Cached",  0)

        effective_free_memory = (mem_free_kb + buffers_kb + cached_kb) * 1024
    else:
        raise NotImplementedError(f"The function {return_method_name()} is only implemented for Linux, not for {sys.platform}")
    return effective_free_memory


def kill_process(pname: str) -> None:
    """Kill a process by its name, then check if it is still running and retry if needed. Make sure the process name is unique to avoid killing unintended processes."""
    import time
    import signal
    import subprocess
    while True:
        # Find the process IDs of the given process name
        process_ids = []
        try:
            process_list = subprocess.check_output(["pgrep", "-f", pname]).decode(DEFAULT_ENCODING)
            process_ids = process_list.splitlines()
        except subprocess.CalledProcessError as e:
            raise ValueError(f"Failed to find process with name {pname}. Make sure the process name is correct and unique: {e}") from e

        if process_ids:
            for pid in process_ids:
                print(f"Killing {pname} process with PID: {pid}")
                try:
                    os.kill(int(pid), signal.SIGTERM)  # Send SIGTERM to terminate the process
                    print(f"Sent SIGTERM to PID {pid}")
                except ProcessLookupError as e:
                    raise ValueError(f"Process with PID {pid} not found. It may have already exited: {e}") from e
        else:
            print(f"No {pname} process found.")
            break

        # Check if the process is still running
        time.sleep(2)  # Wait for 2 seconds before checking again
        process_ids = subprocess.check_output(["pgrep", "-f", pname]).decode(DEFAULT_ENCODING).splitlines()

        if not process_ids:
            print(f"{pname} process successfully killed.")
            break  # Exit the loop when the process is no longer running
        else:
            print(f"{pname} is still running. Retrying...")


def is_process_running(process_name: str) -> bool:
    """Check if a process with the given name is running."""
    import subprocess
    fallback_logging_config()
    try:
        the_command = ["pgrep", "-f", process_name]
        results = subprocess.run(the_command, capture_output=True, text=True)
        if results.returncode != 0:
            return False
        return True
    except subprocess.CalledProcessError as e:
        logging.error(f"Error occurred: {e}")
        return False


def start_only_one_instance(process_name: str) -> None:
    """Start a process, but only if it's not already running."""
    import subprocess
    import time
    fallback_logging_config()
    if not is_process_running(process_name):
        logging.info("Starting %s...", process_name)
        subprocess.Popen([process_name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        # Wait briefly to ensure the command is processed
        time.sleep(1)
    else:
        logging.info("%s is already running.", process_name)


def open_filemanager_with_dirs(directories: list[str | os.PathLike[str]]) -> None:
    """
    Open the file manager with the specified directories.
    Note: Most file managers don't support multiple tabs via command line, so open separate windows.
    """
    import subprocess
    import time
    fallback_logging_config()
    if sys.platform.startswith("linux"):
        filemanager_command = "nemo"
    else:
        logging.error(f"The function {return_method_name()} is only implemented for Linux systems, not for {sys.platform}")
        return
    logging.info("Opening file manager with specified directories...")
    for directory in directories:
        directory = ensure_path(directory)
        if not safe_exists(directory):
            logging.error(f"Directory {os.fspath(directory)} does not exist. Skipping.")
            continue
        if not safe_is_dir(directory):
            logging.error(f"Directory {os.fspath(directory)} is not a valid directory. Skipping.")
            continue
        subprocess.Popen([filemanager_command, os.fspath(directory)], stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)
        # Optional: Wait briefly between opening directories
        time.sleep(0.5)


def detect_country(force_wtfismyip: bool = False) -> str | None:
    """
    Detect the country of the IP address using ipinfo.io service.
    If the request fails, it falls back to wtfismyip.com service.

    Args:
        force_wtfismyip: If True, always use wtfismyip.com

    Returns:
        The country name as a string, or None if detection fails.

    Raises:
        ValueError: If the IPINFO_API_TOKEN environment variable is not set.
    """
    import subprocess
    import requests
    import json
    thecountryname = None
    if not force_wtfismyip:
        logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("force_wtfismyip=%s.", force_wtfismyip)
        try:
            if "IPINFO_API_TOKEN" in os.environ:
                ipinfo_access_token = os.environ['IPINFO_API_TOKEN']
            else:
                raise ValueError("IPINFO_API_TOKEN environment variable is not set. If you don't have one, you can sign up for a free account here: https://ipinfo.io/signup")

            logging.info("Attempting to detect country using IPinfo...")
            # Uncomment the following lines if you want to use the ipinfo library instead of curl
            # import ipinfo
            # handler = ipinfo.getHandler(ipinfo_access_token,
            #                             request_options={"timeout": ipinfo_timeout_seconds})
            # details = handler.getDetails()
            # logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("IPinfo DETAILS:\n%s", details)
            # thecountryname = details.country
            the_command = ["curl", f"https://api.ipinfo.io/lite/8.8.8.8?token={ipinfo_access_token}"]
            logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("Running command: %s", " ".join(the_command))
            result = subprocess.run(the_command, capture_output=True,
                                    text=True, timeout=5)
            if result.returncode != 0:
                logging.error("curl command failed with return code %d", result.returncode)
                raise Exception("Curl command failed")
            logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("curl output: %s", result.stdout)
            dct = json.loads(result.stdout)
            thecountryname = dct.get("country", "")
            logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("Detected country from curl: %s", thecountryname)
        except (subprocess.TimeoutExpired, json.JSONDecodeError, Exception) as e:
            logging.warning("IPinfo exception: %s\nFalling back to wtfismyip.com.", e)

    if not thecountryname:
        try:
            resp = requests.get("https://wtfismyip.com/json", timeout=5)
            resp.raise_for_status()
            dct = resp.json()
            thecountryname = dct.get("YourFuckingCountry", "")
            logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("Detailed results: %s", dct)
        except requests.exceptions.RequestException as e:
            logging.error("Country detection failed (network error): %s", e)
            return None
        except (ValueError, KeyError) as e:
            logging.error("Country detection failed (bad response): %s", e)
            return None

    return thecountryname.strip() if thecountryname else None


def set_system_volume(percent: int, tolerance: int = 1,
                      change_mute: Literal["mute", "unmute"] | None = None,
                      force_pactl: bool = False) -> None:
    """
    Set the system volume to a specific level.
    On Linux, this function will:
    Try to set the PulseAudio default sink volume to 'percent'% via pulsectl,
    verify it, and if that fails, fall back to pactl.

    Args:
        percent:     Desired volume level (0–100).
        tolerance:   Allowed percent difference when verifying (default: 1%).
        change_mute: If set to "mute", the function will mute the audio instead of
                     setting a specific volume. If set to "unmute", it will unmute
                     the audio. If None, it will not change the mute state.
        force_pactl: If True, always use pactl even if pulsectl is available (default: False).

    Returns:
        None

    Raises:
        RuntimeError: If the volume could not be set or verified.
    """
    import subprocess
    import logging
    fallback_logging_config()
    if not sys.platform.startswith("linux"):
        raise RuntimeError("This set_system_volume() function is only intended to run on Linux systems.")
    fraction = percent / 100.0
    mute_arg = None
    if change_mute is not None:
        if change_mute.casefold() == "mute":
            mute_arg = 1
        elif change_mute.casefold() == "unmute":
            mute_arg = 0
        else:
            raise ValueError("change_mute must be 'mute', 'unmute', or None")
    # First, try using pulsectl to set the volume.
    if not force_pactl:
        logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("force_pactl=%s.", force_pactl)
        try:
            from pulsectl import Pulse, PulseError
            logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("[pulsectl] Attempting to set the volume to %d%% using pulsectl...", percent)
            with Pulse("volume-setter") as pulse:
                default_name = pulse.server_info().default_sink_name
                sink = pulse.get_sink_by_name(default_name)
                pulse.sink_suspend(sink.index, False)  # <— wake it up if it's suspended
                pulse.volume_set_all_chans(sink, fraction)
                # Optionally set mute
                if mute_arg is not None:
                    pulse.sink_mute(sink.index, mute_arg)
                    sink_after = pulse.get_sink_by_name(default_name)
                    # Verify mute state
                    if   mute_arg == 1 and not sink_after.mute:
                        raise RuntimeError("[pulsectl] Volume is not muted even though the user requested it to be muted.")
                    elif mute_arg == 0 and     sink_after.mute:
                        raise RuntimeError("[pulsectl] Volume is still muted even though the user requested it to be unmuted.")
                else:
                    # Fetch volume again to verify
                    sink_after = pulse.get_sink_by_name(default_name)
                vols = sink_after.volume.values  # list of channel floats 0.0–1.0
                avg = sum(vols) / len(vols)
                actual = int(round(avg * 100))
                if abs(actual - percent) > tolerance:
                    raise RuntimeError(f"[pulsectl] Expected {percent}%, but got {actual}%")
                if mute_arg is not None and sink_after.mute != mute_arg:
                    state = "muted" if sink_after.mute else "unmuted"
                    raise RuntimeError(f"Mute verify failed: got {state}")
                logging.info("[pulsectl] Volume set to %d%%, %s", actual, state)
                return  # Successfully set volume and verified
        except ImportError:
            logging.warning("[pulsectl] Not installed; falling back to pactl...")
        except PulseError as e:
            logging.error("[pulsectl] PulseError: %s; falling back to pactl...", e)
        except RuntimeError as e:
            logging.error("%s; falling back to pactl...", e)
        except Exception as e:
            logging.error("[pulsectl] Unexpected error: %s; falling back to pactl...", e)

    # Fallback to pactl if pulsectl is not available or fails
    logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("[pactl] Attempting to set the volume to %d%% using pactl...", percent)
    the_command = ["pactl", "suspend-sink", "@DEFAULT_SINK@", "0"]
    logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("[pactl] Running command: %s", " ".join(the_command))
    result = subprocess.run(the_command, check=True, capture_output=True, text=True)
    if result.stderr:
        raise RuntimeError(f"[pactl] Error waking up sink from suspension: {result.stderr.strip()}")
    the_command = ["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{percent}%"]
    logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("[pactl] Running command: %s", " ".join(the_command))
    result = subprocess.run(the_command, check=True, capture_output=True, text=True)
    if result.stderr:
        raise RuntimeError(f"[pactl] Error setting volume: {result.stderr.strip()}")
    # Set mute if requested
    if mute_arg is not None:
        cmd = ["pactl", "set-sink-mute", "@DEFAULT_SINK@", str(mute_arg)]
        logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("[pactl] %s", " ".join(cmd))
        mute_result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        if mute_result.stderr:
            raise RuntimeError(f"[pactl] Error setting mute: {mute_result.stderr.strip()}")
        # Verify mute state
        mute_check_cmd = ["pactl", "get-sink-mute", "@DEFAULT_SINK@"]
        logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("[pactl] Running command: %s", " ".join(mute_check_cmd))
        mute_result = subprocess.run(mute_check_cmd, check=True, capture_output=True, text=True)
        if mute_result.stderr:
            raise RuntimeError(f"[pactl] Error getting mute state: {mute_result.stderr.strip()}")
        mute_output = mute_result.stdout.strip()
        if   mute_arg == 1 and "yes" not in mute_output:
            raise RuntimeError("[pactl] Volume is not muted even though the user requested it to be muted.")
        elif mute_arg == 0 and "no"  not in mute_output:
            raise RuntimeError("[pactl] Volume is still muted even though the user requested it to be unmuted.")
        logging.info("[pactl] Audio %s", 'muted' if mute_arg else 'unmuted')
    # Verify volume setting with pactl
    the_command = ["pactl", "get-sink-volume", "@DEFAULT_SINK@"]
    logging.getLogger().isEnabledFor(logging.DEBUG) and logging.debug("[pactl] Running command: %s", " ".join(the_command))
    result = subprocess.run(the_command, check=True, capture_output=True, text=True)
    if result.stderr:
        raise RuntimeError(f"[pactl] Error getting volume: {result.stderr.strip()}")
    output = result.stdout.strip()
    # Example output: "Volume: front-left: 32768 / 100% / 32768 / 100%"
    parts = output.split("/")
    if len(parts) < 2:
        raise RuntimeError(f"[pactl] Unexpected pactl output: {output}")
    actual = int(parts[1].strip().replace("%", ""))
    if abs(actual - percent) > tolerance:
        raise RuntimeError(f"[pactl] Expected {percent}%, but got {actual}%")
    logging.info("[pactl] Volume set to %d%%", percent)


def open_playlist_in_VLC(playlist: str | os.PathLike[str], no_start: bool = False) -> None:
    """Open a playlist in VLC. If no_start is True, don't start playback in VLC."""
    import subprocess
    playlist = ensure_file(playlist)
    if no_start: command_list = ["vlc", "--no-playlist-autostart", os.fspath(playlist)]
    else:        command_list = ["vlc",                            os.fspath(playlist)]
    subprocess.Popen(command_list, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def open_dir_in_VLC(the_dir: str | os.PathLike[str], sort_choice: str = "sort_by_name",
                    recursive: bool = False, no_start:  bool = False) -> None:
    """Create a playlist of the files in the specified directory, then play that playlist in VLC. By default, don't search the directory recursively and sort the files by name. Optional arguments allow recursive loading or sorting by modification time. If no_start is True, don't start playback in VLC."""
    import subprocess
    if the_dir is None:
        raise ValueError("The directory path cannot be None.")
    the_dir = ensure_dir(the_dir)
    # start_flag = "--start-paused" if no_start else False # The "--start-paused" flag forces you to press play in VLC EACH TIME YOU GO TO A NEW PLAYLIST ENTRY!
    start_flag = "--no-playlist-autostart" if no_start else False
    # List to store files with their modification times
    files_with_times: list[tuple[float, Path]] = []
    dirs_with_times:  list[tuple[float, Path]] = []  # Only used if not recursive
    entries:                    Iterable[Path] = the_dir.rglob("*") if recursive else the_dir.iterdir()
    for p in entries:
        if safe_is_file(p):
            if p.suffix.casefold() in PLAYLIST_EXTENSIONS_SET:
                continue  # Exclude playlist files
            files_with_times.append((safe_mtime(p), p))
        elif not recursive and safe_is_dir(p):
            dirs_with_times.append((safe_mtime(p), p))
    if sort_choice == "sort_by_name":
        # Sort files by name, case-insensitively
        files_with_times.sort(   key=lambda x: x[1].name.casefold())
        if len(dirs_with_times) > 0:
            dirs_with_times.sort(key=lambda x: x[1].name.casefold())
    elif sort_choice == "sort_by_time":
        # Sort files by modification time (earliest first)
        files_with_times.sort(   key=lambda x: x[0])
        if len(dirs_with_times) > 0:
            dirs_with_times.sort(key=lambda x: x[0])
    # If present, put directories at the top of the list
    files_with_times = dirs_with_times + files_with_times
    # Create the .m3u playlist content with as_posix() to ensure forward slashes even on Windows
    playlist_content = "#EXTM3U\n"
    for _, file_path in files_with_times:
        playlist_content += f"#EXTINF:-1,{file_path.name.replace(',', '').replace('-', '')}" \
                            f"\n{file_path.as_posix()}\n"
    # Write the playlist to disk in the directory
    playlist_path = the_dir / f"{filename_format(the_dir.name)}_playlist.m3u"
    playlist_path.write_text(playlist_content, encoding=DEFAULT_ENCODING)
    # Open the playlist in VLC
    if start_flag: command_list = ["vlc", start_flag, os.fspath(playlist_path)]
    else:          command_list = ["vlc",             os.fspath(playlist_path)]
    subprocess.Popen(command_list, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def remove_prefix_from_filename(filepath: str | os.PathLike[str], prefix: str) -> bool:
    """
    If the given filepath's base filename starts with the given prefix:
      1. Remove the prefix (and any " _-" immediately following it).
      2. Move the file (but only if that doesn't cause errors).

    Args:
        filepath: The path to the file whose name may need to be changed.
        prefix:   The prefix to remove from the filename.

    Returns:
        True:  If the file was successfully renamed, or if it didn't need renaming.
        False: If the file was not renamed because it didn't start with the prefix,
               or if the new filename already exists.

    Raises:
        OSError: If the rename operation fails due to an OS error (e.g., permission denied).
    """
    fallback_logging_config()
    filepath = ensure_path(filepath)
    if not safe_exists(filepath):
        logging.warning("File or directory '%s' does not exist.", os.fspath(filepath))
        return False
    file = filepath.name
    if file.startswith(prefix):
        new_file = file.replace(prefix, "", 1)  # Replace only the first occurrence
        # If the first character is now in " _-", remove it:
        while new_file[0] in " _-":
            new_file = new_file[1:]
        new_filepath = filepath.parent / new_file
        if not safe_exists(new_filepath):
            try:
                filepath.rename(new_filepath)
                logging.info("Renamed '%s' to '%s'.", os.fspath(filepath), os.fspath(new_filepath))
                return True
            except OSError as e:
                raise OSError(f"Failed to rename '{os.fspath(filepath)}' to '{os.fspath(new_filepath)}': {e}") from e
        else:
            logging.warning("Cannot rename '%s' to '%s': New path already exists.",
                            os.fspath(filepath), os.fspath(new_filepath))
            return False
    else:
        return False


def remove_prefix_from_html_title(filepath: str | os.PathLike[str], prefix: str) -> bool:
    """If the given filepath is an HTML file and its title starts with the given prefix, remove the prefix from the title and save the file, then return True. Otherwise, return False."""
    fallback_logging_config()
    filepath = ensure_path(filepath)
    if not safe_is_file(filepath):
        logging.warning("File '%s' does not exist or is not a file.", os.fspath(filepath))
        return False
    if filepath.suffix.casefold() not in HTML_EXTENSIONS_SET:
        logging.warning("File '%s' is not an HTML or HTM file.", os.fspath(filepath))
        return False
    html = my_fopen(filepath)
    title_start = html.find("<title>") + len("<title>")
    title_end   = html.find("</title>", title_start)
    if title_start == -1 or title_end == -1:
        logging.warning("Could not find the title in the HTML file '%s'.", os.fspath(filepath))
        return False
    title = html[title_start:title_end]
    if title.startswith(prefix):
        new_title = title.replace(prefix, "", 1)  # Replace only the first occurrence
        new_html  = html[:title_start] + new_title + html[title_end:]
        filepath.write_text(new_html, encoding=DEFAULT_ENCODING)
        logging.info("Removed prefix '%s' from the title in '%s'.", prefix, os.fspath(filepath))
        return True
    else:
        return False


def combine_html_files(file_paths:  list[str | os.PathLike[str]],
                       output_file_path: str | os.PathLike[str]) -> None:
    """
    Combine multiple HTML files into a single HTML file.
    The first file's <head> is preserved, and all <body> contents are concatenated.

    Args:
        file_paths:       List of (presorted) file paths to the HTML files to combine.
        output_file_path: Path to save the combined HTML file.

    Returns:
        None: the combined HTML is saved to the specified output file path.

    Raises:
        Exception:         If there is an error reading any of the HTML files or writing the output file.
        FileNotFoundError: If any of the input files do not exist.
        ValueError:        If the output file path is not valid.
        ImportError:       If BeautifulSoup is not installed.
        RuntimeError:      If the output file cannot be written.
        OSError:           If there is an error during file operations.
    """
    from bs4 import BeautifulSoup
    fallback_logging_config()
    combined_body = ""
    head_content  = ""
    first_file_processed = False
    for file_path in file_paths:
        file_path     = ensure_file(file_path)
        file_contents = my_fopen(file_path)
        try:
            soup = BeautifulSoup(file_contents, "html.parser")
            # Extract <head> from the first Chapter1.html
            if not first_file_processed:
                head_content = str(soup.head)
                first_file_processed = True
            # Extract <body> content
            body_content = soup.body
            combined_body += str(body_content)
        except Exception:  # Catch any unexpected errors from BeautifulSoup without crashing.
            logging.exception(f"File {os.fspath(file_path)} encountered an error.")
    # Create the new HTML structure
    combined_html = f"<!DOCTYPE html>\n<html>\n{head_content}\n<body>\n{combined_body}\n</body>\n</html>"
    # Save to the output file path
    try:
        output_file_path = ensure_path(output_file_path)
        output_file_path.parent.mkdir(parents=True, exist_ok=True)
        output_file_path.write_text(combined_html, encoding=DEFAULT_ENCODING)
    except Exception:  # Catch any unexpected errors from writing the file without crashing.
        logging.exception("Error saving combined HTML to %s.", os.fspath(output_file_path))
    logging.info("Saved combined HTML to '%s'.", os.fspath(output_file_path))


# Map these to spaces (treat like separators)
CHARACTERS_TO_SPACE = f"._-{EM_DASH}{HORIZONTAL_ELLIPSIS}"
REPLACE_WITH_SPACE  = " " * len(CHARACTERS_TO_SPACE)
# Delete these outright (quotes of various kinds)
# Include double quote, apostrophe, backtick. Thanks to unidecode(),
# curly/angle quotes become ASCII quotes and will be removed too. However,
# just in case unidecode can't be imported, those are explicitly deleted too.
QUOTES_TO_DELETE  = f"\"'{BACKTICK}{LSQUOTE}{RSQUOTE}{LDQUOTE}{RDQUOTE}"
TRANSLATION_TABLE = str.maketrans(CHARACTERS_TO_SPACE, REPLACE_WITH_SPACE, QUOTES_TO_DELETE)


def normalize_for_search(text: str) -> str:
    """Convert text to ASCII and lowercase for case- and diacritic-insensitive comparison. Also treat some characters such as ._- the same as spaces. Remove quotes (', ", ' and their unicode variants)."""
    fallback_logging_config()
    try:
        from unidecode import unidecode
        decoded_text = unidecode(text)
    except ImportError:
        logging.warning("unidecode module not installed; diacritics will not be removed.")
        decoded_text = text
    return decoded_text.casefold().translate(TRANSLATION_TABLE)


def calculate_checksum(file_path: str | os.PathLike[str]) -> str:
    """Calculate the SHA256 checksum of a file."""
    import hashlib
    file_path   = ensure_file(file_path)
    sha256_hash = hashlib.sha256()
    with file_path.open("rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()


# A comprehensive tuple of encodings to try when reading files, with most likely encodings first.
TEXT_ENCODINGS: Final[tuple[str, ...]] = (
    "utf-8",           "latin-1",        "ascii",           "iso-8859-1",         "big5",
    "utf-8-sig",       "utf-16",         "utf-16-be",       "utf-16-le",          "utf-32",
    "utf-32-be",       "utf-32-le",      "cp1252",          "cp1251",             "cp1250",
    "cp1253",          "cp1254",         "cp1255",          "cp1256",             "cp1257",
    "cp1258",          "iso-8859-2",     "iso-8859-3",      "iso-8859-4",         "iso-8859-5",
    "iso-8859-6",      "iso-8859-7",     "iso-8859-8",      "iso-8859-9",         "iso-8859-10",
    "iso-8859-11",     "iso-8859-13",    "iso-8859-14",     "iso-8859-15",        "iso-8859-16",
    "cp437",           "cp850",          "cp852",           "cp855",              "cp857",
    "cp858",           "cp860",          "cp861",           "cp862",              "cp863",
    "cp864",           "cp865",          "cp866",           "cp869",              "cp037",
    "cp424",           "cp500",          "cp720",           "cp737",              "cp775",
    "cp874",           "cp875",          "cp932",           "cp949",              "cp950",
    "cp1006",          "cp1026",         "cp1125",          "cp1140",             "big5hkscs",
    "gb2312",          "gbk",            "gb18030",         "euc-jp",             "euc-jis-2004",
    "euc-jisx0213",    "euc-kr",         "iso2022-jp",      "iso2022-jp-1",       "iso2022-jp-2",
    "iso2022-jp-2004", "iso2022-jp-3",   "iso2022-jp-ext",  "iso2022-kr",         "johab",
    "koi8-r",          "koi8-t",         "koi8-u",          "kz1048",             "mac-cyrillic",
    "mac-greek",       "mac-iceland",    "mac-latin2",      "mac-roman",          "mac-turkish",
    "ptcp154",         "shift-jis",      "shift-jis-2004",  "shift-jisx0213",     "hz",
    "tis-620",         "utf-7",          "base64",          "bz2",                "charmap",
    "cp273",           "cp856",          "euc_jis_2004",    "euc_jisx0213",       "euc_jp",
    "euc_kr",          "hex",            "hp-roman8",       "idna",               "iso2022_jp",
    "iso2022_jp_1",    "iso2022_jp_2",   "iso2022_jp_2004", "iso2022_jp_3",       "iso2022_jp_ext",
    "iso2022_kr",      "iso8859-1",      "iso8859-10",      "iso8859-11",         "iso8859-13",
    "iso8859-14",      "iso8859-15",     "iso8859-16",      "iso8859-2",          "iso8859-3",
    "iso8859-4",       "iso8859-5",      "iso8859-6",       "iso8859-7",          "iso8859-8",
    "iso8859-9",       "mac-arabic",     "mac-croatian",    "mac-farsi",          "mac-romanian",
    "palmos",          "punycode",       "quopri",          "raw-unicode-escape", "rot-13",
    "shift_jis",       "shift_jis_2004", "shift_jisx0213",  "unicode-escape",     "uu",
    "zlib",
)
TEXT_ENCODINGS_SET: Final[frozenset[str]] = frozenset(TEXT_ENCODINGS)  # sets are faster
# # Quality control: examine encodings for any uppercase characters.
# for enc in TEXT_ENCODINGS:
#     if any(c.isupper() for c in enc):
#         raise ValueError(f"Encoding '{enc}' contains uppercase characters. All encodings should be lowercase.")
# assert len(TEXT_ENCODINGS_SET) == len(TEXT_ENCODINGS), "Duplicate text encodings?"
# def all_encodings() -> list[str]:
#     """Return a sorted list of all known Python text encodings."""
#     import pkgutil, encodings, codecs
#     from encodings.aliases import aliases as alias_map
#     names = set()
#     # 1) Try every module under encodings/
#     for m in pkgutil.iter_modules(encodings.__path__):
#         try:
#             names.add(codecs.lookup(m.name).name)
#         except LookupError:
#             # Skip helpers like 'aliases' or any non-codec modules
#             pass
#     # 2) Try all alias keys and targets
#     for n in set(alias_map) | set(alias_map.values()):
#         try:
#             names.add(codecs.lookup(n).name)
#         except LookupError:
#             # Skip platform-specific codecs not present here (e.g., 'mbcs' on Linux/macOS)
#             pass
#     return sorted(names)
# # Example usage
# encs = all_encodings()
# print(len(encs), "encodings found")
# print(f"Peek at the first few text encodings: {encs[:25]=}")
# def invalid_encodings(names: list[str]) -> list[str]:
#     """Return a list of invalid encoding names from the given list."""
#     import codecs
#     bad = []
#     for n in names:
#         try:
#             codecs.lookup(n)
#         except LookupError:
#             bad.append(n)
#     return bad
# bad = invalid_encodings(TEXT_ENCODINGS)
# print(f"Invalid encodings: {bad}" if bad else "No invalid encodings.")
# missing_encodings = []
# for enc in encs:
#     if enc not in TEXT_ENCODINGS:
#         missing_encodings.append(enc)
# print(f"{len(missing_encodings)} encodings are missing from TEXT_ENCODINGS: {missing_encodings}")

# A comprehensive list of python extensions.
PYTHON_EXTENSIONS:    Final[tuple[str, ...]] = (".py", ".pyw")
PYTHON_EXTENSIONS_SET: Final[frozenset[str]] = frozenset(PYTHON_EXTENSIONS)
# assert len(PYTHON_EXTENSIONS_SET) == len(PYTHON_EXTENSIONS), "Duplicate python extensions?"

# A comprehensive list of HTML extensions.
HTML_EXTENSIONS:    Final[tuple[str, ...]] = (".html", ".htm", ".xhtml")
HTML_EXTENSIONS_SET: Final[frozenset[str]] = frozenset(HTML_EXTENSIONS)
# assert len(HTML_EXTENSIONS_SET) == len(HTML_EXTENSIONS), "Duplicate HTML extensions?"

# A comprehensive list of text file extensions.
TEXT_EXTENSIONS: Final[tuple[str, ...]] = (
    ".txt",          ".html",     ".htm",      ".csv",        ".json",       ".xml",
    ".adoc",         ".asciidoc", ".bib",      ".cfg",        ".conf",       ".ini",
    ".log",          ".md",       ".markdown", ".properties", ".rtf",        ".rst",
    ".sgm",          ".sgml",     ".tex",      ".toml",       ".tsv",        ".xhtml",
    ".yaml",         ".yml",      ".svg",      ".rss",        ".atom",       ".opml",
    ".xsd",          ".dtd",      ".xsl",      ".xslt",       ".xaml",       ".kml",
    ".gpx",          ".mml",      ".jsonl",    ".ndjson",     ".geojson",    ".topojson",
    ".ipynb",        ".gltf",     ".mdx",      ".rmd",        ".org",        ".textile",
    ".wiki",         ".mkd",      ".mkdn",     ".mdown",      ".mmd",        ".ltx",
    ".sty",          ".cls",      ".dtx",      ".aux",        ".toc",        ".env",
    ".editorconfig", ".desktop",  ".service",  ".hcl",        ".tf",         ".tfvars",
    ".proto",        ".graphql",  ".gql",      ".cue",        ".rego",       ".edn",
    ".cff",          ".tab",      ".psv",      ".ltsv",       ".css",        ".js",
    ".mjs",          ".cjs",      ".ts",       ".tsx",        ".jsx",        ".ejs",
    ".erb",          ".pug",      ".mustache", ".hbs",        ".handlebars", ".jinja",
    ".jinja2",       ".njk",      ".twig",     ".liquid",     ".sh",         ".bash",
    ".zsh",          ".fish",     ".bat",      ".cmd",        ".ps1",        ".c",
    ".h",            ".cpp",      ".hpp",      ".java",       ".kt",         ".kts",
    ".cs",           ".go",       ".rs",       ".swift",      ".py",         ".rb",
    ".php",          ".pl",       ".lua",      ".r",          ".jl",         ".m",
    ".diff",         ".patch",    ".err",      ".out",        ".po",         ".pot",
    ".ics",          ".vcf",      ".vcard",    ".srt",        ".vtt",        ".ass",
    ".ssa",          ".lrc",      ".dot",      ".gv",         ".mermaid",    ".sgf",
    ".pgn",          ".sfv",      ".md5",      ".sha1",       ".sha256",
)
TEXT_EXTENSIONS_SET: Final[frozenset[str]] = frozenset(TEXT_EXTENSIONS)
# assert len(TEXT_EXTENSIONS_SET) == len(TEXT_EXTENSIONS), "Duplicate text extensions?"

# A comprehensive list of book / ebook extensions (textual & comic-book archives).
BOOK_EXTENSIONS: Final[tuple[str, ...]] = (
    # Open / widely supported ebooks
    ".epub",     # EPUB (most common open ebook format)
    ".pdf",      # PDF (widely used for ebooks, especially textbooks)
    ".txt",      # Plain text
    ".rtf",      # Rich Text Format
    ".html",     # HTML
    ".htm",      # HTML
    ".xhtml",    # XHTML
    ".doc",      # Microsoft Word (legacy binary format)
    ".docx",     # Microsoft Word (modern XML-based format)
    ".odt",      # OpenDocument Text

    # Amazon / Kindle family
    ".azw",      # Kindle (based on MOBI)
    ".azw1",     # Kindle Topaz (legacy)
    ".azw3",     # Kindle KF8
    ".azw4",     # Kindle Print Replica (PDF-like)
    ".azw6",     # Kindle KFX resource container
    ".kfx",      # Kindle KFX
    ".mobi",     # Mobipocket
    ".prc",      # Mobipocket (often identical container)
    ".tpz",      # Kindle Topaz (legacy)

    # Apple iBooks
    ".ibooks",

    # FictionBook
    ".fb2",
    ".fbz",      # zipped FB2

    # DjVu (scanned books)
    ".djvu",
    ".djv",

    # Legacy / less common ebook formats
    ".lit",      # Microsoft Reader
    ".oeb",      # Open eBook
    ".oebzip",   # zipped OEB
    ".pdb",      # Palm/eReader container (various subtypes)
    ".pml",      # Palm Markup Language (often paired with PDB)
    ".pmlz",     # zipped PML
    ".tr2",      # TomeRaider
    ".tr3",      # TomeRaider
    ".rb",       # Rocket eBook
    ".tcr",      # Psion/TECsoft TCR
    ".chm",      # Compiled HTML Help (commonly used for tech ebooks)
    ".snb",      # Shanda Bambook
    ".umd",      # UMD eBook (popular in some regions)

    # Comic-book archives (graphic novels / manga)
    ".cbz",      # ZIP-based
    ".cbr",      # RAR-based
    ".cb7",      # 7z-based
    ".cbt",      # TAR-based
    ".cba",      # ACE-based

    # Sony BBeB family
    ".lrf",      # Sony BBeB
    ".lrx",      # Sony BBeB (encrypted)
    ".lrs",      # Sony BBeB XML source

    # Kobo
    ".kepub",    # Kobo Kepub variant

    # Apple authoring/export
    ".iba",      # iBooks Author package/export
    ".pages",    # Apple Pages document (often used for manuscripts)

    # Apabi / CN markets
    ".ceb",      # Apabi eBook
    ".xeb",      # Apabi eBook (variant)

    # Paginated document formats
    ".xps",      # XML Paper Specification
    ".oxps",     # OpenXPS

    # Print/TeX outputs (often used for books)
    ".ps",       # PostScript
    ".dvi",      # TeX DVI

    # Source/book authoring text formats
    ".tex",      # LaTeX source
    ".rst",      # reStructuredText
    ".md",       # Markdown
    ".markdown", # Markdown (long extension)

    # Desktop publishing / layout sources
    ".indd",     # Adobe InDesign document
    ".idml",     # Adobe InDesign Markup Language
    ".qxp",      # QuarkXPress project
    ".qxd",      # QuarkXPress document
    ".sla",      # Scribus document
)
BOOK_EXTENSIONS_SET: Final[frozenset[str]] = frozenset(BOOK_EXTENSIONS)
# assert len(BOOK_EXTENSIONS_SET) == len(BOOK_EXTENSIONS), "Duplicate book extensions?"

# A comprehensive list of video file extensions.
VIDEO_EXTENSIONS: Final[tuple[str, ...]] = (
    ".mp4",   ".mkv",   ".mov",   ".avi",    ".mpg",   ".mpeg",
    ".wmv",   ".m4v",   ".flv",   ".divx",   ".vob",   ".iso",
    ".3gp",   ".webm",  ".mts",   ".m2ts",   ".ts",    ".ogv",
    ".rm",    ".rmvb",  ".asf",   ".f4v",    ".mxf",   ".dv",
    ".swf",   ".m2v",   ".svi",   ".mpe",    ".ogm",   ".bik",
    ".xvid",  ".yuv",   ".qt",    ".gvi",    ".viv",   ".fli",
    ".mjpg",  ".mjpeg", ".amv",   ".drc",    ".flc",   ".vp6",
    ".ivf",   ".mps",   ".vro",   ".hevc",   ".h265",  ".264",
    ".str",   ".evo",   ".3g2",   ".h264",   ".av1",   ".ogx",
    ".mlv",   ".ps",    ".mp2v",  ".dvs",    ".gxf",   ".webp",
    ".vp8",   ".trp",   ".f4p",   ".mk3d",   ".3gpp",  ".mod",
    ".tod",   ".cine",  ".arf",   ".wrf",    ".braw",  ".jmf",
    ".r3d",   ".dpx",   ".mpv",   ".rmx",    ".smk",   ".mj2",
    ".scm",   ".ivr",   ".xesc",  ".wtv",    ".dcr",   ".ismv",
    ".vc1",   ".vcd",   ".bin",   ".sfd",    ".m2t",   ".m2p",
    ".m1v",   ".y4m",   ".dif",   ".dvr-ms", ".tivo",  ".nuv",
    ".nsv",   ".nut",   ".bk2",   ".usm",    ".xmv",   ".thp",
    ".pmf",   ".h263",  ".h261",  ".vp9",
)
VIDEO_EXTENSIONS_SET: Final[frozenset[str]] = frozenset(VIDEO_EXTENSIONS)
# assert len(VIDEO_EXTENSIONS_SET) == len(VIDEO_EXTENSIONS), "Duplicate video extensions?"

# A comprehensive list of audio file extensions.
AUDIO_EXTENSIONS: Final[tuple[str, ...]] = (
    ".mp3",   ".wav",   ".flac",  ".aac",   ".ogg",   ".wma",
    ".m4a",   ".alac",  ".aiff",  ".opus",  ".amr",   ".pcm",
    ".au",    ".raw",   ".dts",   ".ac3",   ".mka",   ".mpc",
    ".vqf",   ".ape",   ".shn",   ".ra",    ".rm",    ".oga",
    ".spx",   ".caf",   ".snd",   ".mid",   ".midi",  ".kar",
    ".rmi",   ".asf",   ".wv",    ".mp4",   ".wave",  ".webm",
    ".aa",    ".aax",   ".dsf",   ".dff",   ".sf2",   ".g721",
    ".voc",   ".swa",   ".bwf",   ".ivs",   ".smp",   ".weba",
    ".sds",   ".brstm", ".adx",   ".hca",   ".ast",   ".psf",
    ".psf2",  ".qsf",   ".ssf",   ".usf",   ".gsf",   ".tta",
    ".dsm",   ".dmf",   ".mod",   ".s3m",   ".it",    ".xm",
    ".mt2",   ".mo3",   ".umx",   ".mogg",  ".tak",   ".trk",
    ".669",   ".abc",   ".ts",    ".ym",    ".hsq",   ".mpa",
    ".m4b",   ".m4p",   ".mp2",   ".mp1",   ".aif",   ".aifc",
    ".m4r",   ".adts",  ".eac3",  ".rf64",  ".w64",   ".sd2",
    ".sph",   ".3gp",   ".3g2",   ".3ga",   ".ofr",   ".ofs",
    ".la",    ".pac",   ".mlp",   ".thd",   ".aaxc",  ".dss",
    ".ds2",   ".awb",   ".bcstm", ".bfstm", ".bcwav", ".bfwav",
    ".fsb",   ".wem",   ".xwm",   ".lopus",
)
AUDIO_EXTENSIONS_SET: Final[frozenset[str]] = frozenset(AUDIO_EXTENSIONS)
# assert len(AUDIO_EXTENSIONS_SET) == len(AUDIO_EXTENSIONS), "Duplicate audio extensions?"

# A comprehensive list of subtitle file extensions.
SUBTITLE_EXTENSIONS: Final[tuple[str, ...]] = (
    ".srt",   ".sub",    ".idx",   ".ass",   ".ssa",   ".vtt",
    ".ttml",  ".dfxp",   ".smi",   ".smil",  ".usf",   ".psb",
    ".mks",   ".lrc",    ".stl",   ".pjs",   ".rt",    ".aqt",
    ".gsub",  ".jss",    ".dks",   ".mpl2",  ".sbt",   ".vsf",
    ".zeg",   ".webvtt", ".scc",   ".cap",   ".asc",   ".sbv",
    ".ebu",   ".sami",   ".xml",   ".itt",   ".txt",   ".sup",
    ".sst",   ".son",    ".mcc",   ".pac",   ".890",   ".mpl",
    ".onl",   ".cin",    ".tds",   ".ult",   ".ttxt",
)
SUBTITLE_EXTENSIONS_SET: Final[frozenset[str]] = frozenset(SUBTITLE_EXTENSIONS)
# assert len(SUBTITLE_EXTENSIONS_SET) == len(SUBTITLE_EXTENSIONS), "Duplicate subtitle extensions?"

# A comprehensive list of image file extensions.
IMAGE_EXTENSIONS: Final[tuple[str, ...]] = (
    ".bmp",  ".dib",   ".gif",    ".jpeg", ".jpg",  ".jpe",
    ".jfif", ".pjpeg", ".pjp",    ".png",  ".pbm",  ".pgm",
    ".ppm",  ".pnm",   ".pam",    ".tif",  ".tiff", ".sgi",
    ".rgb",  ".tga",   ".hdr",    ".exr",  ".webp", ".apng",
    ".heic", ".heif",  ".avif",   ".jp2",  ".j2k",  ".j2c",
    ".jxr",  ".svg",   ".svgz",   ".eps",  ".ai",   ".pdf",
    ".cdr",  ".emf",   ".wmf",    ".dxf",  ".dwg",  ".mng",
    ".raw",  ".arw",   ".cr2",    ".cr3",  ".dng",  ".erf",
    ".raf",  ".orf",   ".pef",    ".rw2",  ".rwl",  ".sr2",
    ".srw",  ".3fr",   ".kdc",    ".mrw",  ".mos",  ".nrw",
    ".pcx",  ".pcd",   ".pic",    ".pct",  ".xcf",  ".psd",
    ".psb",  ".kra",   ".fit",    ".fits", ".fpx",  ".djvu",
    ".djv",  ".lbm",   ".iff",    ".ico",  ".icns", ".dds",
    ".jxl",  ".xbm",   ".xpm",    ".ras",  ".jpf",  ".jpx",
    ".jpm",  ".qoi",   ".bpg",    ".flif", ".cgm",  ".ktx",
    ".ktx2", ".pvr",   ".basis",  ".nef",  ".crw",  ".dcr",
    ".k25",  ".iiq",   ".fff",    ".mef",  ".x3f",  ".hif",
    ".dcm",  ".nii",   ".gz",     ".nrrd", ".mha",  ".mhd",       # ".gz" matches ".nii.gz"
    ".mrc",  ".sid",   ".ecw",    ".bil",  ".bip",  ".aseprite",
    ".g3",   ".g4",    ".fax",    ".sff",  ".wsq",  ".pspimage",
    ".pdn",  ".psp",   ".ps",     ".ase",  ".clip", ".afphoto",
    ".bsq",
)
IMAGE_EXTENSIONS_SET: Final[frozenset[str]] = frozenset(IMAGE_EXTENSIONS)
# assert len(IMAGE_EXTENSIONS_SET) == len(IMAGE_EXTENSIONS), "Duplicate image extensions?"

# A comprehensive list of playlist file extensions.
PLAYLIST_EXTENSIONS: Final[tuple[str, ...]] = (
    ".m3u",    ".m3u8",    ".pls",  ".xspf",  ".asx",    ".wpl",
    ".zpl",    ".b4s",     ".cue",  ".smil",  ".smi",    ".ram",
    ".wax",    ".wmx",     ".wvx",  ".fpl",   ".mpcpl",  ".dpl",
    ".aimppl", ".aimppl4", ".pla",  ".xml",
)
PLAYLIST_EXTENSIONS_SET: Final[frozenset[str]] = frozenset(PLAYLIST_EXTENSIONS)
# assert len(PLAYLIST_EXTENSIONS_SET) == len(PLAYLIST_EXTENSIONS), "Duplicate playlist extensions?"

# A comprehensive list of archive file extensions.
_ARCHIVE_EXTENSIONS_1: tuple[str, ...] = (
    ".zip",     ".rar",    ".7z",    ".tar",    ".gz",      ".tgz",
    ".bz2",     ".xz",     ".tbz2",  ".tz2",    ".lzma",    ".lz",
    ".xpi",     ".crx",    ".zst",   ".cab",    ".arj",     ".ace",
    ".uue",     ".zoo",    ".jar",   ".war",    ".ear",     ".iso",
    ".img",     ".dmg",    ".lzh",   ".lha",    ".cpio",    ".deb",
    ".rpm",     ".apk",    ".pak",   ".arc",    ".a",       ".mar",
    ".b1",      ".wim",    ".shar",  ".run",    ".shk",     ".sit",
    ".sitx",    ".zpaq",   ".br",    ".zipx",   ".xar",     ".dar",
    ".ar",      ".tbz",    ".tb2",   ".txz",    ".tlz",     ".taz",
    ".tzo",     ".tzst",   ".lzo",   ".lz4",    ".phar",    ".asar",
    ".whl",     ".nupkg",  ".gem",   ".crate",  ".conda",   ".ipa",
    ".cbz",     ".cbr",    ".cb7",   ".kmz",    ".warc",    ".pk3",
    ".pk4",     ".alz",    ".cpt",   ".ha",     ".sqx",     ".uha",
    ".z01",     ".r00",    ".001",
)
# Technically this list should include .z02... and .r01... and .002...
_ARCHIVE_EXTENSIONS_2: tuple[str, ...] = tuple(f".z{num:02d}" for num in range(2, 100))
_ARCHIVE_EXTENSIONS_3: tuple[str, ...] = tuple(f".r{num:02d}" for num in range(1, 100))
_ARCHIVE_EXTENSIONS_4: tuple[str, ...] = tuple(f".{num:03d}"  for num in range(2, 100))
_ARCHIVE_CATEGORIES = (
    _ARCHIVE_EXTENSIONS_1, _ARCHIVE_EXTENSIONS_2,
    _ARCHIVE_EXTENSIONS_3, _ARCHIVE_EXTENSIONS_4,
)
ARCHIVE_EXTENSIONS: Final[tuple[str, ...]] = tuple(
    dict.fromkeys(chain.from_iterable(_ARCHIVE_CATEGORIES))
)
ARCHIVE_EXTENSIONS_SET: Final[frozenset[str]] = frozenset(ARCHIVE_EXTENSIONS)
# assert len(ARCHIVE_EXTENSIONS_SET) == len(ARCHIVE_EXTENSIONS), "Duplicate archive extensions?"

# Build the combined tuple with first-seen order across categories
_ALL_CATEGORIES = (
    PYTHON_EXTENSIONS, HTML_EXTENSIONS,  TEXT_EXTENSIONS,  BOOK_EXTENSIONS,     SUBTITLE_EXTENSIONS,
    VIDEO_EXTENSIONS,  AUDIO_EXTENSIONS, IMAGE_EXTENSIONS, PLAYLIST_EXTENSIONS, ARCHIVE_EXTENSIONS,
)
ALL_KNOWN_EXTENSIONS: Final[tuple[str, ...]] = tuple(
    dict.fromkeys(chain.from_iterable(_ALL_CATEGORIES))
)
ALL_KNOWN_EXTENSIONS_SET: Final[frozenset[str]] = frozenset(ALL_KNOWN_EXTENSIONS)
# assert len(ALL_KNOWN_EXTENSIONS) == len(ALL_KNOWN_EXTENSIONS_SET)
# # If you ever iterate the combined tuple (e.g., custom matching where longer extensions should win like .tar.gz before .gz), sort by length after dedup:
# # ALL_KNOWN_EXTENSIONS = tuple(
# #     sorted(dict.fromkeys(chain.from_iterable(_ALL_CATEGORIES)), key=len, reverse=True)
# # )
# print(f"{len(ALL_KNOWN_EXTENSIONS)} total known extensions.")
# for ext in ALL_KNOWN_EXTENSIONS:
#     if any(c.isupper() for c in ext):
#         raise ValueError(f"Extension '{ext}' in ALL_KNOWN_EXTENSIONS contains uppercase characters.")
#     if ext.count('.') > 1:
#         raise ValueError(f"Extension '{ext}' in ALL_KNOWN_EXTENSIONS contains multiple periods.")
