"""Chunking pipeline module for splitting content into processable units."""
from dataclasses import dataclass, field
from typing import List, Optional
from uuid import uuid4
import re


@dataclass
class Chunk:
    """A chunk of content with metadata for processing.
    
    Attributes:
        id: Unique identifier for the chunk
        content: The actual text content
        embedding: Optional embedding vector for semantic search
        source_type: Type of source (message, summary, tool_call, etc.)
        source_id: Reference to the source document/message
        position: Position of this chunk in the source document
        token_count: Estimated token count
        metadata: Additional metadata
    """
    id: str = field(default_factory=lambda: str(uuid4()))
    content: str = ""
    embedding: Optional[List[float]] = None
    source_type: str = "message"
    source_id: str = ""
    position: int = 0
    token_count: int = 0
    metadata: dict = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "content": self.content,
            "embedding": self.embedding,
            "source_type": self.source_type,
            "source_id": self.source_id,
            "position": self.position,
            "token_count": self.token_count,
            "metadata": self.metadata,
        }


def estimate_tokens(text: str) -> int:
    """Estimate token count using a simple heuristic.
    
    Uses roughly 4 characters per token as an approximation.
    For production, use tiktoken or similar libraries.
    """
    if not text:
        return 0
    # Simple approximation: ~4 chars per token
    return len(text) / 4


def chunk_by_tokens(
    content: str,
    chunk_size: int = 512,
    overlap: int = 0,
    source_type: str = "message",
    source_id: str = "",
) -> List[Chunk]:
    """Split content into chunks of specified token size with optional overlap.
    
    Args:
        content: The text content to chunk
        chunk_size: Target token count per chunk (256, 512, or 1024)
        overlap: Number of tokens to overlap between chunks
        source_type: Type of source document
        source_id: ID of the source document
        
    Returns:
        List of Chunk objects
    """
    if not content or not content.strip():
        return []
    
    # Normalize chunk size to valid options
    valid_sizes = [256, 512, 1024]
    if chunk_size not in valid_sizes:
        chunk_size = min(valid_sizes, key=lambda x: abs(x - chunk_size))
    
    # Calculate character-based chunk size (approximation)
    # 4 chars per token as heuristic
    char_size = chunk_size * 4
    overlap_chars = overlap * 4 if overlap else 0
    
    chunks = []
    position = 0
    start = 0
    
    content_length = len(content)
    
    while start < content_length:
        # Calculate end position
        end = start + char_size
        
        # If not at end, try to break at word boundary
        if end < content_length:
            # Look for last space or newline before end
            last_space = max(
                content.rfind(' ', 0, end),
                content.rfind('\n', 0, end),
                content.rfind('. ', 0, end - 1),
            )
            if last_space > start:
                end = last_space + 1
        
        # Extract chunk content
        chunk_text = content[start:end].strip()
        
        if chunk_text:
            chunk = Chunk(
                content=chunk_text,
                source_type=source_type,
                source_id=source_id,
                position=position,
                token_count=estimate_tokens(chunk_text),
                metadata={
                    "chunk_size": chunk_size,
                    "overlap": overlap,
                },
            )
            chunks.append(chunk)
            position += 1
        
        # Move to next chunk with overlap
        if overlap_chars > 0 and end < content_length:
            start = end - overlap_chars
        else:
            start = end
    
    return chunks


def chunk_content(
    content: str,
    chunk_size: int = 512,
    overlap: int = 50,
    source_type: str = "message",
    source_id: str = "",
) -> List[Chunk]:
    """Chunk content with default overlap handling.
    
    This is the main entry point for content chunking.
    
    Args:
        content: Text content to chunk
        chunk_size: Target token size (256, 512, or 1024)
        overlap: Number of tokens for context overlap
        source_type: Source type (message, summary, etc.)
        source_id: Source identifier
        
    Returns:
        List of Chunk objects
    """
    return chunk_by_tokens(
        content=content,
        chunk_size=chunk_size,
        overlap=overlap,
        source_type=source_type,
        source_id=source_id,
    )


# Alias for backwards compatibility
split_into_chunks = chunk_content