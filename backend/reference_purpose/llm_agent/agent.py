import gc
import json
import time
import uuid
from dataclasses import dataclass
from typing import Any, Callable, Optional

from agno.agent import Agent, RunOutput
from agno.compression.manager import CompressionManager
from agno.run.base import RunStatus
from pydantic import BaseModel, Field
from src.app_modernization.config.settings import get_app_mod_config

from src.platform import logging
from src.platform.llm import LLMConfig, get_llm_config
from src.platform.llm.exceptions import LLMException
from src.platform.llm.metrics.workflow_names import WorkflowName
from src.platform.llm_agent.provider import SlingshotGateway
from src.platform.llm_agent.streaming import collect_agent_stream
from src.platform.llm_agent.errors import extract_run_output_error
from src.utils import fetch_proprietary_prompt

logger = logging.get_logger(__name__)


class AgentMetrics(BaseModel):
    """Metrics for agent execution."""

    input_tokens: int = -1
    output_tokens: int = -1
    total_tokens: int = -1
    timestamp: Optional[int] = None


class ToolCall(BaseModel):
    """Represents a tool call made by the agent."""

    id: Optional[str] = Field(default=None, description="Tool call ID")
    name: str = Field(description="Name of the tool called")
    arguments: dict[str, Any] = Field(
        default_factory=dict, description="Arguments passed to the tool"
    )
    tool_response: Optional[str] = Field(
        default=None, description="Response from the tool"
    )
    timestamp: Optional[int] = None


class AssistantMessage(BaseModel):
    """Represents a message from the Agent assistant."""

    content: str = Field(description="Content of the message")
    tool_calls: list[ToolCall] = Field(
        default_factory=list, description="Tool calls in this message"
    )
    metrics: Optional[AgentMetrics] = Field(
        default=None, description="Metrics for this message"
    )


class AgentMessage(BaseModel):
    """Represents a message in the agent conversation."""

    role: str = Field(description="Role of the message sender (user, assistant, tool)")
    content: Optional[str] = Field(default=None, description="Content of the message")
    tool_calls: list[ToolCall] = Field(
        default_factory=list, description="Tool calls in this message"
    )
    metrics: Optional[AgentMetrics] = Field(
        default=None, description="Metrics for this message"
    )

    class Config:
        extra = "allow"


class AgentResponse(BaseModel):
    """Structured response from the agent containing all execution details."""

    content: str = Field(description="Final content/output from the agent")
    assistant_messages: list[AssistantMessage] = Field(
        default_factory=list, description="All assistant messages in the conversation"
    )
    assistant_message_count: int = Field(
        default=0, description="Number of assistant messages (populated after metrics are extracted)"
    )

    class Config:
        extra = "allow"


@dataclass(frozen=True)
class IMarkdownParser:
    use: bool = False
    markdown_llm_model: Optional[str] = None

    def __post_init__(self):
        if self.use and self.markdown_llm_model is None:
            raise ValueError("You must specify a markdown parser model")


@dataclass
class IAuthConfig:
    user_id: Optional[str] = None
    auth_token: Optional[str] = None
    account_id: Optional[str] = None
    project_id: Optional[str] = None


class AppModAgent:
    MAX_CONTENT_LENGTH_FOR_MONITORING = 1000

    def __init__(
        self,
        agent_name: str,
        system_prompt: str,
        model: str,
        tools: list[Callable],
        max_completion_tokens: int = None,
        output_schema: type[BaseModel] | None = None,
        markdown_parser: IMarkdownParser = IMarkdownParser(),
        auth_config: IAuthConfig = IAuthConfig(),
        enable_tool_compression: bool = True,
        workflow_name: WorkflowName = WorkflowName.UNKNOWN,
        resource_id: Optional[uuid.UUID] = None,
        other_details: Optional[dict[str, Any]] = None,
    ):
        llm_config = get_llm_config()
        self.app_mod_settings = get_app_mod_config()
        self.agent_name = agent_name
        self.model = model
        self.workflow_name = workflow_name
        self.resource_id = resource_id
        self.other_details = other_details
        self._auth_config = auth_config
        self._llm_config = llm_config
        self._fallback_model = llm_config.llm_fallback_model
        max_completion_tokens = max_completion_tokens or self.app_mod_settings.spec_generation_llm_max_output_tokens
        self._max_completion_tokens = max_completion_tokens

        # Create the parser model
        parser_model = self.__create_parser_provider(
            model=markdown_parser.markdown_llm_model,
            auth=auth_config,
            llm_config=llm_config,
            max_completion_tokens=max_completion_tokens,
        )
        compression_manager = self.__create_compression_manager(auth_config, llm_config)

        # Load markdown parser prompt from YAML
        markdown_parser_prompt = None
        if markdown_parser.use:
            try:
                markdown_parser_config = fetch_proprietary_prompt("markdown-parser")
                markdown_parser_prompt = markdown_parser_config.system_prompt
                logger.info("Loaded markdown parser prompt from YAML configuration")
            except Exception as e:
                logger.warning(f"Failed to load markdown parser prompt from YAML: {e}")
                markdown_parser_prompt = None

        self.agent = Agent(
            name=agent_name,
            model=self.__create_base_provider(
                model=model, auth=auth_config, llm_config=llm_config, max_completion_tokens=max_completion_tokens
            ),
            instructions=system_prompt,
            output_schema=output_schema,
            tools=tools,
            telemetry=False,
            compression_manager=(
                compression_manager if enable_tool_compression else None
            ),
            parser_model=parser_model if markdown_parser.use else None,
            parser_model_prompt=markdown_parser_prompt,
        )
        # Keep a factory so run() can rebuild the agent with the fallback model.
        self._build_agent = lambda fallback_id: Agent(
            name=agent_name,
            model=self.__create_base_provider(
                model=fallback_id, auth=auth_config, llm_config=llm_config,
                max_completion_tokens=max_completion_tokens,
            ),
            instructions=system_prompt,
            output_schema=output_schema,
            tools=tools,
            telemetry=False,
            compression_manager=(
                compression_manager if enable_tool_compression else None
            ),
            parser_model=parser_model if markdown_parser.use else None,
            parser_model_prompt=markdown_parser_prompt,
        )

    @staticmethod
    def __create_base_provider(
        model: str, auth: IAuthConfig, llm_config: LLMConfig, max_completion_tokens: int = None
    ) -> SlingshotGateway:
        return SlingshotGateway(
            id=model if model else llm_config.default_model,
            api_key=auth.auth_token,
            base_url=llm_config.endpoint,
            timeout=llm_config.timeout,
            account_id=auth.account_id,
            project_id=auth.project_id,
            user_identifier=auth.user_id,
            # Mitigation: ensure we don't truncate spec generation unexpectedly.
            max_completion_tokens=max_completion_tokens if max_completion_tokens else llm_config.llm_max_output_tokens,
        )

    @staticmethod
    def __create_parser_provider(
        model: str, auth: IAuthConfig, llm_config: LLMConfig, max_completion_tokens: int = None
    ) -> SlingshotGateway:
        return SlingshotGateway(
            id=model,
            api_key=auth.auth_token,
            base_url=llm_config.endpoint,
            timeout=llm_config.timeout,
            account_id=auth.account_id,
            project_id=auth.project_id,
            user_identifier=auth.user_id,
             # Keep parser-model outputs bounded consistently with main completion.
            max_completion_tokens=max_completion_tokens if max_completion_tokens else llm_config.llm_max_output_tokens,
        )

    @staticmethod
    def __create_compression_manager(
        auth: IAuthConfig, llm_config: LLMConfig
    ) -> CompressionManager:
        model = SlingshotGateway(
            id=llm_config.compression_model,
            api_key=auth.auth_token,
            base_url=llm_config.endpoint,
            timeout=llm_config.timeout,
            account_id=auth.account_id,
            project_id=auth.project_id,
            user_identifier=auth.user_id,
        )

        # Load custom compression prompt from YAML
        try:
            compression_config = fetch_proprietary_prompt("tool-result-compression")
            compression_prompt = compression_config.system_prompt
            logger.info("Loaded custom compression prompt from YAML configuration")
        except Exception as e:
            logger.warning(
                f"Failed to load custom compression prompt, using default: {e}"
            )
            compression_prompt = None

        return CompressionManager(
            model=model,
            compress_token_limit=llm_config.compress_token_limit,
            compress_tool_call_instructions=compression_prompt,
        )

    @staticmethod
    def _truncate_content(content: str) -> str:
        if len(content) > AppModAgent.MAX_CONTENT_LENGTH_FOR_MONITORING:
            return content[:1000] + "...[truncated]"
        return content

    def _convert_to_structured_response(self, raw_response: RunOutput) -> AgentResponse:
        """
        Convert raw Agno agent response to structured AgentResponse.

        Args:
            raw_response: Raw response object from Agno agent

        Returns:
            Structured AgentResponse with all execution details
        """
        # Extract content - handle both structured and plain text responses
        raw_content = raw_response.content

        # If content is a MarkdownSpecification object, extract the content field
        if isinstance(raw_content, BaseModel):
            content = (
                raw_content.content
                if hasattr(raw_content, "content")
                else str(raw_content)
            )
        # If content is a JSON string with {"content": "..."}, parse it
        elif isinstance(raw_content, str) and raw_content.strip().startswith("{"):
            try:
                parsed = json.loads(raw_content)
                content = parsed.get("content", raw_content)
            except (json.JSONDecodeError, AttributeError):
                # If parsing fails, use raw content
                content = raw_content
        else:
            content = raw_content

        # Extract and convert messages
        assistant_messages = []

        # Extract tool calls and create map
        tool_call_map: dict[str, ToolCall] = {}

        for message in raw_response.messages:
            if message.role != "tool":
                continue
            tool_call_map[message.tool_call_id] = ToolCall(
                id=message.tool_call_id,
                name=message.tool_name,
                arguments=message.tool_args,
                tool_response=self._truncate_content(message.content or ""),
                timestamp=message.created_at,
            )

        # Now extract the assistant messages with tool calls
        for message in raw_response.messages:
            if message.role != "assistant":
                continue
            tool_calls: list[ToolCall] = []
            if message.tool_calls:
                for tc in message.tool_calls:
                    if tc["id"] not in tool_call_map:
                        continue
                    tool_calls.append(tool_call_map[tc["id"]])
            assistant_message = AssistantMessage(
                content=self._truncate_content(message.content or ""),
                tool_calls=tool_calls,
                metrics=AgentMetrics(
                    input_tokens=message.metrics.input_tokens,
                    output_tokens=message.metrics.output_tokens,
                    total_tokens=message.metrics.total_tokens,
                    timestamp=message.created_at,
                ),
            )
            assistant_messages.append(assistant_message)

        return AgentResponse(content=content, assistant_messages=assistant_messages)

    async def run(self, agent_input: BaseModel) -> AgentResponse:
        """
        Run the agent with the given input.

        Args:
            agent_input: Input data for the agent

        Returns:
            The Agent response
        """
        _start_time = time.time()
        try:
            raw_response = await collect_agent_stream(self.agent, agent_input)
        except LLMException:
            fallback = self._fallback_model
            if not fallback or fallback == self.model:
                raise
            logger.warning(
                "Primary model failed; retrying with fallback model",
                agent_name=self.agent_name,
                primary_model=self.model,
                fallback_model=fallback,
            )
            raw_response = await collect_agent_stream(
                self._build_agent(fallback), agent_input
            )

        if raw_response.status == RunStatus.error:
            error_msg = extract_run_output_error(raw_response)
            logger.error(
                "agent_execution_error",
                agent_name=self.agent_name,
                internal_reason=error_msg,
            )
            raise RuntimeError("Agent execution failed. Please try again.")

        if not raw_response.messages:
            logger.warn(
                "Agent responded with no messages",
                agent_name=self.agent_name,
                model=self.model,
            )
            return AgentResponse(content="", assistant_messages=[])
        else:
            response = self._convert_to_structured_response(raw_response)

        from src.platform.llm.metrics import get_metrics_service
        metrics_svc = get_metrics_service()
        if metrics_svc:
            total_input = sum(
                m.metrics.input_tokens
                for m in response.assistant_messages
                if m.metrics and m.metrics.input_tokens >= 0
            )
            total_output = sum(
                m.metrics.output_tokens
                for m in response.assistant_messages
                if m.metrics and m.metrics.output_tokens >= 0
            )
            await metrics_svc.record(
                workflow_name=self.workflow_name,
                resource_id=self.resource_id,
                model_used=self.model,
                input_tokens=total_input,
                output_tokens=total_output,
                response_time_ms=int((time.time() - _start_time) * 1000),
                other_details=self.other_details,
            )
            del raw_response
            gc.collect()

        # Snapshot the count then release the full message objects (tool arguments,
        # tool responses, etc.) so they can be GC'd before the caller processes the response.
        response.assistant_message_count = len(response.assistant_messages)
        response.assistant_messages = []

        return response
