"""Configuration classes for BrainClaw Memory System."""
from dataclasses import dataclass, field
from typing import Optional, List
import os


# RRF (Reciprocal Rank Fusion) constants
RRF_K_DEFAULT = 60  # Default RRF k constant
RRF_K_RANGE = (1, 100)  # Valid range for RRF k constant
RRF_MAX_RESULTS = 50  # Maximum results to consider from each source


# Pre-defined team constants for OpenClaw
# Environment-driven identity defaults
OPENCLAW_TENANT_ID = os.getenv("OPENCLAW_TENANT_ID", "tenant-default")

# Team members: Comma-separated list of agent IDs
team_members_env = os.getenv("OPENCLAW_TEAM_MEMBERS")
if team_members_env:
    TEAM_MEMBER_IDS = tuple(id.strip() for id in team_members_env.split(",") if id.strip())
else:
    # Default empty team: BrainClaw should be populated by the host environment
    TEAM_MEMBER_IDS = ()

# Identity Constants (Environment-defined)
COORDINATOR_AGENT_ID = os.getenv("OPENCLAW_COORDINATOR_ID", "")
AI_JOOSE_FACTORY_TEAM_MEMBERS = TEAM_MEMBER_IDS
AI_JOOSE_FACTORY_TENANT_ID = OPENCLAW_TENANT_ID


@dataclass
class AgentConfig:
    """Configuration for an agent within the memory system."""
    agent_id: str
    agent_name: str
    role: str
    team_id: str = "default-team"
    team_member_ids: List[str] = field(default_factory=lambda: list(TEAM_MEMBER_IDS))
    model: str = "llama3.2"
    capabilities: List[str] = field(default_factory=list)
    tenant_id: str = OPENCLAW_TENANT_ID

    @classmethod
    def from_env(cls, agent_name: str) -> Optional["AgentConfig"]:
        """
        Create AgentConfig from environment variables.
        
        If agent_name is provided, it looks for prefixed env vars:
        - <NAME>_AGENT_ID
        - <NAME>_AGENT_ROLE
        - <NAME>_AGENT_MODEL
        
        Otherwise falls back to global AGENT_ID, AGENT_ROLE, etc.
        """
        name_prefix = f"{agent_name.upper()}_" if agent_name else ""
        
        def get_env(key: str, default: str = "") -> str:
            val = os.getenv(f"{name_prefix}{key}")
            if val is not None:
                return val
            return os.getenv(key, default)

        # Basic identification
        agent_id = get_env("AGENT_ID")
        
        # Basic identification
        agent_id = get_env("AGENT_ID")
        
        if not agent_id:
            agent_id = f"agent-{agent_name.lower()}-uuid" if agent_name else "agent-unknown"

        role = get_env("AGENT_ROLE")
        if not role:
            role = "Assistant"

        team_id = get_env("TEAM_ID", "default-team")
        
        # Load team members
        members_str = get_env("TEAM_MEMBERS")
        if members_str:
            team_member_ids = [id.strip() for id in members_str.split(",") if id.strip()]
        else:
            team_member_ids = list(TEAM_MEMBER_IDS)

        model = get_env("MODEL", "llama3.2")
        
        # Load capabilities
        cap_str = get_env("CAPABILITIES")
        capabilities = [c.strip() for c in cap_str.split(",") if c.strip()] if cap_str else []

        return cls(
            agent_id=agent_id,
            agent_name=agent_name.lower(),
            role=role,
            team_id=team_id,
            team_member_ids=team_member_ids,
            model=model,
            capabilities=capabilities,
            tenant_id=get_env("TENANT_ID", OPENCLAW_TENANT_ID)
        )

    def is_team_member(self, other_agent_id: str) -> bool:
        """Check if another agent is in the same team."""
        return other_agent_id in self.team_member_ids

    def can_access_team_memories(self) -> bool:
        """Check if this agent can access team memories."""
        return True  # All team members can see team memories


@dataclass
class PostgresConfig:
    """PostgreSQL configuration with pgvector support."""
    host: str = "localhost"
    port: int = 5432
    database: str = "openclaw_memory"
    user: str = "openclaw"
    password: str = "openclaw_secret"
    min_pool_size: int = 5
    max_pool_size: int = 20
    
    @classmethod
    def from_url(cls, url: str) -> "PostgresConfig":
        """Parse PostgreSQL URL into config."""
        try:
            from urllib.parse import urlparse
            p = urlparse(url)
            return cls(
                host=p.hostname or "localhost",
                port=p.port or 5432,
                database=p.path.lstrip('/') or "openclaw_memory",
                user=p.username or "openclaw",
                password=p.password or "openclaw_secret",
            )
        except Exception:
            return cls.from_env()

    @classmethod
    def from_env(cls) -> "PostgresConfig":
        return cls(
            host=os.getenv("POSTGRES_HOST", "localhost"),
            port=int(os.getenv("POSTGRES_PORT", "5432")),
            database=os.getenv("POSTGRES_DB", "openclaw_memory"),
            user=os.getenv("POSTGRES_USER", "openclaw"),
            password=os.getenv("POSTGRES_PASSWORD", "openclaw_secret"),
        )


@dataclass
class WeaviateConfig:
    """Weaviate configuration for semantic/hybrid search.
    
    Connects to existing Weaviate container (ajf-weaviate) or localhost.
    """
    host: str = "localhost"
    port: int = 8080
    grpc_port: int = 50051
    api_key: Optional[str] = None
    
    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"
    
    @classmethod
    def from_url(cls, url: str) -> "WeaviateConfig":
        """Parse Weaviate URL into config."""
        try:
            from urllib.parse import urlparse
            p = urlparse(url)
            return cls(
                host=p.hostname or "localhost",
                port=p.port or 8080,
                grpc_port=int(os.getenv("WEAVIATE_GRPC_PORT", "50051")),
                api_key=os.getenv("WEAVIATE_API_KEY"),
            )
        except Exception:
            return cls.from_env()

    @classmethod
    def from_env(cls) -> "WeaviateConfig":
        return cls(
            host=os.getenv("WEAVIATE_HOST", "localhost"),
            port=int(os.getenv("WEAVIATE_PORT", "8080")),
            api_key=os.getenv("WEAVIATE_API_KEY"),
        )


@dataclass
class Neo4jConfig:
    """Neo4j configuration for relationship graph.
    
    Reads credentials from environment variables for security:
    - NEO4J_URI: Full connection URI (default: bolt://ajf-neo4j-host-proxy:7687)
    - NEO4J_USER: Username (default: neo4j)
    - NEO4J_PASSWORD: Password (must be set in environment)
    - NEO4J_DATABASE: Database name (default: ajf-openclaw-graphdb)
    
    Note: Uses ajf-neo4j-host-proxy DNS name for Docker network connectivity.
    The proxy forwards to host.docker.internal:7687 (Neo4j Desktop on Mac).
    """
    uri: str = "bolt://ajf-neo4j-host-proxy:7687"
    user: str = "neo4j"
    password: str = ""  # Must be set via NEO4J_PASSWORD env var
    database: str = "ajf-openclaw-graphdb"
    
    @classmethod
    def from_url(cls, url: str) -> "Neo4jConfig":
        """Parse Neo4j URL into config."""
        try:
            from urllib.parse import urlparse
            p = urlparse(url)
            # Neo4j URLs often include credentials
            return cls(
                uri=f"{p.scheme}://{p.hostname}:{p.port}" if p.hostname else url,
                user=p.username or "neo4j",
                password=p.password or os.getenv("NEO4J_PASSWORD", ""),
                database=os.getenv("NEO4J_DATABASE", "ajf-openclaw-graphdb"),
            )
        except Exception:
            return cls.from_env()

    @classmethod
    def from_env(cls) -> "Neo4jConfig":
        return cls(
            uri=os.getenv("NEO4J_URI", "bolt://ajf-neo4j-host-proxy:7687"),
            user=os.getenv("NEO4J_USER", "neo4j"),
            password=os.getenv("NEO4J_PASSWORD", ""),
            database=os.getenv("NEO4J_DATABASE", "ajf-openclaw-graphdb"),
        )


@dataclass
class MemoryConfig:
    """Main configuration for BrainClaw Memory System."""
    postgres: PostgresConfig
    weaviate: WeaviateConfig
    neo4j: Neo4jConfig
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536
    
    @classmethod
    def from_env(cls) -> "MemoryConfig":
        return cls(
            postgres=PostgresConfig.from_env(),
            weaviate=WeaviateConfig.from_env(),
            neo4j=Neo4jConfig.from_env(),
        )


@dataclass
class LLMConfig:
    """Configuration for LLM services."""
    ollama_base_url: str = "http://host.docker.internal:11434"
    extraction_model: str = "llama3.2"
    summarization_model: str = "llama3.2"

    @classmethod
    def from_env(cls) -> "LLMConfig":
        return cls(
            ollama_base_url=os.getenv("OLLAMA_BASE_URL", "http://host.docker.internal:11434"),
            extraction_model=os.getenv("OLLAMA_EXTRACTION_MODEL", "llama3.2"),
            summarization_model=os.getenv("OLLAMA_SUMMARIZATION_MODEL", "llama3.2"),
        )


@dataclass
class LearningConfig:
    """Configuration for active learning."""
    confidence_boost_used: float = 0.05
    confidence_boost_clicked: float = 0.03
    confidence_decay_rate: float = 0.001
    min_confidence: float = 0.1
    max_confidence: float = 1.0


@dataclass
class SummarizationConfig:
    """Configuration for auto-summarization."""
    min_memories_to_summarize: int = 5
    max_age_days: int = 30
    min_confidence: float = 0.5
    summary_window_days: int = 7


@dataclass
class ObservabilityConfig:
    """Configuration for observability (tracing, logging, metrics).
    
    Controls OpenTelemetry tracing, structured JSON logging,
    and Prometheus metrics collection.
    """
    enabled: bool = True
    otlp_endpoint: str = "http://localhost:4317"
    otlp_use_http: bool = False
    log_level: str = "INFO"
    log_format: str = "json"  # or "console" for development
    metrics_port: int = 9090
    metrics_enabled: bool = True
    
    @classmethod
    def from_env(cls) -> "ObservabilityConfig":
        """Create config from environment variables."""
        return cls(
            enabled=os.getenv("OPENCLAW_OBSERVABILITY_ENABLED", "true").lower() == "true",
            otlp_endpoint=os.getenv("OPENCLAW_OTLP_ENDPOINT", "http://localhost:4317"),
            otlp_use_http=os.getenv("OPENCLAW_OTLP_USE_HTTP", "false").lower() == "true",
            log_level=os.getenv("OPENCLAW_LOG_LEVEL", "INFO"),
            log_format=os.getenv("OPENCLAW_LOG_FORMAT", "json"),
            metrics_port=int(os.getenv("OPENCLAW_METRICS_PORT", "9090")),
            metrics_enabled=os.getenv("OPENCLAW_METRICS_ENABLED", "true").lower() == "true",
        )


@dataclass
class OpenClawMemoryConfig:
    """Configuration for OpenClaw Memory System."""
    
    # Storage backends
    postgres: PostgresConfig
    weaviate: WeaviateConfig
    neo4j: Neo4jConfig
    
    # Agent configuration
    agent_id: str  # Current agent
    agent_name: str  # Agent name
    team_id: str  # Team ID
    team_member_ids: List[str]  # Team member agent IDs
    
    # Memory settings
    default_visibility: str = 'team'  # 'agent', 'team', 'tenant', 'public'
    auto_promote_confidence_threshold: float = 0.7
    require_confirmation_for: List[str] = field(default_factory=lambda: ['decision', 'identity'])
    
    # LLM and learning configuration
    llm: LLMConfig = field(default_factory=LLMConfig)
    learning: LearningConfig = field(default_factory=LearningConfig)
    summarization: SummarizationConfig = field(default_factory=SummarizationConfig)
    
    @classmethod
    def from_env(cls) -> "OpenClawMemoryConfig":
        """Create config from environment variables."""
        # Prioritize dynamic injections from the bridge
        postgres_url = os.getenv("POSTGRES_URL")
        weaviate_url = os.getenv("WEAVIATE_URL")
        neo4j_url = os.getenv("NEO4J_URL")
        
        return cls(
            postgres=PostgresConfig.from_url(postgres_url) if postgres_url else PostgresConfig.from_env(),
            weaviate=WeaviateConfig.from_url(weaviate_url) if weaviate_url else WeaviateConfig.from_env(),
            neo4j=Neo4jConfig.from_url(neo4j_url) if neo4j_url else Neo4jConfig.from_env(),
            agent_id=os.getenv('AGENT_ID', 'agent-unknown'),
            agent_name=os.getenv('AGENT_NAME', 'unknown'),
            team_id=os.getenv('TEAM_ID', 'team-default'),
            team_member_ids=os.getenv('TEAM_MEMBER_IDS', '').split(',') if os.getenv('TEAM_MEMBER_IDS') else [],
            llm=LLMConfig.from_env(),
            learning=LearningConfig(),
            summarization=SummarizationConfig(),
        )