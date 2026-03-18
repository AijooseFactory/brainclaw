"""
Embedding generation for memory content.

This module provides embedding generation using OpenAI's embedding models
or Ollama for local embedding generation.
Supports text-embedding-3-small and text-embedding-3-large models,
as well as Ollama models like qwen3-embedding:8b.
"""

from typing import List, Optional
from dataclasses import dataclass
import os
import asyncio
import aiohttp


@dataclass
class EmbeddingConfig:
    """Configuration for embedding generation."""
    provider: str = "ollama"  # "openai" or "ollama"
    model: str = "qwen3-embedding:8b"
    api_key: Optional[str] = None
    dimensions: int = 1536
    base_url: str = "http://host.docker.internal:11434"
    
    @classmethod
    def from_env(cls) -> "EmbeddingConfig":
        provider = os.getenv("EMBEDDING_PROVIDER", "ollama")
        
        # Set defaults based on provider
        if provider == "openai":
            default_model = "text-embedding-3-small"
            default_dimensions = 1536
            default_base_url = "https://api.openai.com/v1"
        else:  # ollama
            default_model = "qwen3-embedding:8b"
            default_dimensions = 1024
            default_base_url = os.getenv("OLLAMA_BASE_URL", "http://host.docker.internal:11434")
        
        return cls(
            provider=provider,
            model=os.getenv("EMBEDDING_MODEL", default_model),
            api_key=os.getenv("OPENAI_API_KEY"),
            dimensions=int(os.getenv("EMBEDDING_DIMENSIONS", str(default_dimensions))),
            base_url=os.getenv("EMBEDDING_BASE_URL", default_base_url)
        )


class EmbeddingService:
    """Generate embeddings for memory content.
    
    Provides async embedding generation using OpenAI's API or Ollama.
    """
    
    def __init__(self, config: EmbeddingConfig):
        self.config = config
        self._client = None
        self._session = None
    
    async def initialize(self):
        """Initialize the embedding client."""
        if self.config.provider == "openai":
            from openai import AsyncOpenAI
            self._client = AsyncOpenAI(
                api_key=self.config.api_key,
                base_url=self.config.base_url
            )
        elif self.config.provider == "ollama":
            # Ollama uses HTTP directly via aiohttp
            self._session = aiohttp.ClientSession()
        else:
            raise NotImplementedError(
                f"Embedding provider not supported: {self.config.provider}. "
                f"Supported providers: openai, ollama"
            )
    
    async def close(self):
        """Close the embedding client."""
        self._client = None
        if self._session:
            await self._session.close()
            self._session = None
    
    async def generate_embedding(self, text: str) -> List[float]:
        """Generate embedding for a single text.
        
        Args:
            text: Text to generate embedding for
            
        Returns:
            List of floats representing the embedding vector
            
        Raises:
            RuntimeError: If client not initialized
            NotImplementedError: If provider not supported
        """
        if self.config.provider == "openai":
            if not self._client:
                raise RuntimeError("Embedding client not initialized. Call initialize() first.")
            response = await self._client.embeddings.create(
                model=self.config.model,
                input=text,
                dimensions=self.config.dimensions
            )
            return response.data[0].embedding
        
        elif self.config.provider == "ollama":
            if not self._session:
                raise RuntimeError("Embedding client not initialized. Call initialize() first.")
            
            # Call Ollama's /api/embeddings endpoint
            url = f"{self.config.base_url}/api/embeddings"
            payload = {
                "model": self.config.model,
                "prompt": text
            }
            
            async with self._session.post(url, json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise RuntimeError(
                        f"Ollama embedding request failed: {response.status} - {error_text}"
                    )
                result = await response.json()
                # Parse the "embedding" field from Ollama's JSON response
                return result["embedding"]
        else:
            raise NotImplementedError(f"Provider {self.config.provider} not supported")
    
    async def generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for multiple texts.
        
        Args:
            texts: List of texts to generate embeddings for
            
        Returns:
            List of embedding vectors
            
        Raises:
            RuntimeError: If client not initialized
            NotImplementedError: If provider not supported
        """
        if not texts:
            return []
        
        if self.config.provider == "openai":
            if not self._client:
                raise RuntimeError("Embedding client not initialized. Call initialize() first.")
            
            # Batch request - handle rate limits by chunking
            all_embeddings = []
            chunk_size = 1000  # OpenAI limit
            
            for i in range(0, len(texts), chunk_size):
                chunk = texts[i:i + chunk_size]
                response = await self._client.embeddings.create(
                    model=self.config.model,
                    input=chunk,
                    dimensions=self.config.dimensions
                )
                all_embeddings.extend([item.embedding for item in response.data])
            
            return all_embeddings
        
        elif self.config.provider == "ollama":
            if not self._session:
                raise RuntimeError("Embedding client not initialized. Call initialize() first.")
            
            # Ollama doesn't support batch embeddings, make individual requests
            embeddings = []
            for text in texts:
                embedding = await self.generate_embedding(text)
                embeddings.append(embedding)
            return embeddings
        
        else:
            raise NotImplementedError(f"Provider {self.config.provider} not supported")
    
    async def is_initialized(self) -> bool:
        """Check if the service is initialized.
        
        Returns:
            True if client is ready
        """
        if self.config.provider == "ollama":
            return self._session is not None
        return self._client is not None


# Convenience function for creating service from environment
def create_embedding_service() -> EmbeddingService:
    """Create an embedding service from environment variables.
    
    Returns:
        Configured EmbeddingService instance
    """
    config = EmbeddingConfig.from_env()
    return EmbeddingService(config)