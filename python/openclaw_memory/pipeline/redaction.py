"""
Secrets Redaction Pipeline.

Pre-processor that scans content for sensitive data before storage.
Detects and redacts API keys, passwords, tokens, and private keys.
"""

import re
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class DetectionResult:
    """Result of a secret detection scan."""
    type: str
    pattern: str  # Truncated for logging
    position: int
    line_number: Optional[int] = None
    redacted_value: str = ""


@dataclass
class RedactionResult:
    """Result of a redaction operation."""
    original_content: str
    redacted_content: str
    detections: List[DetectionResult] = field(default_factory=list)
    scan_timestamp: datetime = field(default_factory=datetime.utcnow)
    was_modified: bool = False


class SecretsRedactor:
    """Redact sensitive data before storage.
    
    This pre-processor scans content for secrets before they are stored
    in any database (PostgreSQL, Neo4j, or Weaviate). It helps prevent
    accidental leakage of credentials and sensitive information.
    
    Supported patterns:
    - API keys (api_key, apikey)
    - Passwords (password, passwd, pwd)
    - Secrets/tokens (secret, token, auth)
    - Private keys (RSA, DSA, EC)
    - AWS keys
    - GitHub tokens
    """
    
    # Regex patterns for detecting secrets
    # IMPORTANT: Order matters! More specific patterns must come first
    PATTERNS = {
        # High-specificity patterns first (specific token types)
        'private_key': re.compile(
            r'-----BEGIN (?:RSA |DSA |EC )?PRIVATE KEY-----',
            re.IGNORECASE
        ),
        'jwt': re.compile(
            r'eyJ[a-zA-Z0-9_-]*\.eyJ[a-zA-Z0-9_-]*\.[a-zA-Z0-9_-]*',
            re.IGNORECASE
        ),
        'slack_token': re.compile(
            r'xox[baprs]-[0-9a-zA-Z-]+',
            re.IGNORECASE
        ),
        'github_token': re.compile(
            r'(?:github[_-]?token|gh_token)\s*[=:]\s*["\']?(gh[pousr]_[a-zA-Z0-9_-]{5,})["\']?|'
            r'(gh[pousr]_[a-zA-Z0-9_-]{20,})',
            re.IGNORECASE
        ),
        'aws_access_key': re.compile(
            r'(?:aws[_-]?access[_-]?key[_-]?id|aws_access_key)\s*[=:]\s*["\']?([A-Z0-9]{20})["\']?',
            re.IGNORECASE
        ),
        'aws_secret_key': re.compile(
            r'(?:aws[_-]?secret[_-]?access[_-]?key|aws_secret_key)\s*[=:]\s*["\']?([A-Za-z0-9/+=]{40})["\']?',
            re.IGNORECASE
        ),
        'bearer_token': re.compile(
            r'(?:bearer\s+token|authorization)\s*[=:]\s*["\']?(Bearer\s+[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+)["\']?',
            re.IGNORECASE
        ),
        'api_key': re.compile(
            r'(?:api[_-]?key|apikey)\s*[=:]\s*["\']?([a-zA-Z0-9_-]{1,})["\']?',
            re.IGNORECASE
        ),
        'password': re.compile(
            r'(?:password|passwd|pwd)\s*[=:]\s*["\']?([^\s"\']{1,})["\']?',
            re.IGNORECASE
        ),
        # Markdown-style credentials: "username / password" or "username: password"
        # Note: Uses _looks_like_password() heuristic to reduce false positives
        'credentials_markdown': re.compile(
            r'(?:neo4j|postgres|admin|root|user)\s*[/:\s]+\s*([^\s"\']{1,})',
            re.IGNORECASE
        ),
        # Secret pattern - generic "secret=" or "auth=" (not just "token=" which is too broad)
        'secret': re.compile(
            r'(?:secret|token|auth)\s*[=:]\s*["\']?([a-zA-Z0-9_-]{1,})["\']?',
            re.IGNORECASE
        ),
    }
    
    def __init__(
        self,
        enabled_patterns: Optional[List[str]] = None,
        custom_patterns: Optional[Dict[str, re.Pattern]] = None,
    ):
        """Initialize the SecretsRedactor.
        
        Args:
            enabled_patterns: List of pattern names to enable. 
                              If None, all default patterns are enabled.
            custom_patterns: Dict of additional custom patterns to add.
        """
        self.enabled_patterns = enabled_patterns or list(self.PATTERNS.keys())
        
        # Create active patterns dict
        self.active_patterns: Dict[str, re.Pattern] = {
            name: pattern for name, pattern in self.PATTERNS.items()
            if name in self.enabled_patterns
        }
        
        # Add custom patterns
        if custom_patterns:
            self.active_patterns.update(custom_patterns)
    
    def detect(self, content: str) -> List[DetectionResult]:
        """Detect secrets in content without modifying it.
        
        Args:
            content: The content to scan for secrets.
            
        Returns:
            List of DetectionResult objects for each detected secret.
        """
        detections = []
        
        # Also check for line numbers by splitting content
        lines = content.split('\n')
        
        for secret_type, pattern in self.active_patterns.items():
            matches = pattern.finditer(content)
            for match in matches:
                # For credentials_markdown, apply heuristic to reduce false positives
                if secret_type == 'credentials_markdown':
                    captured_value = match.group(1) if match.lastindex else match.group(0)
                    if not self._looks_like_password(captured_value):
                        continue  # Skip false positive
                
                # Calculate line number
                line_number = content[:match.start()].count('\n') + 1
                
                detection = DetectionResult(
                    type=secret_type,
                    pattern=match.group(0)[:30] + ('...' if len(match.group(0)) > 30 else ''),
                    position=match.start(),
                    line_number=line_number,
                    redacted_value=self._get_redaction_placeholder(secret_type),
                )
                detections.append(detection)
        
        # Sort by position
        return sorted(detections, key=lambda d: d.position)
    
    def redact(self, content: str) -> RedactionResult:
        """Redact secrets and return redacted content + list of detections.
        
        Args:
            content: The content to scan and redact.
            
        Returns:
            RedactionResult containing redacted content and detection list.
        """
        detections = self.detect(content)
        redacted = content
        modified = False
        
        # Process detections in reverse order to maintain correct positions
        for detection in reversed(detections):
            match = self._find_match_at_position(content, detection.position)
            if match:
                placeholder = self._get_redaction_placeholder(detection.type)
                redacted = redacted[:match.start()] + placeholder + redacted[match.end():]
                modified = True
        
        return RedactionResult(
            original_content=content,
            redacted_content=redacted,
            detections=detections,
            was_modified=modified,
        )
    
    def redact_async(self, content: str) -> RedactionResult:
        """Async-compatible redact (for consistency with pipeline interface).
        
        Args:
            content: The content to scan and redact.
            
        Returns:
            RedactionResult containing redacted content and detection list.
        """
        return self.redact(content)
    
    def _find_match_at_position(self, content: str, position: int) -> Optional[re.Match]:
        """Find the match that starts at the given position."""
        for pattern in self.active_patterns.values():
            match = pattern.match(content, position)
            if match and match.start() == position:
                return match
        return None
    
    def _get_redaction_placeholder(self, secret_type: str) -> str:
        """Get the redaction placeholder for a secret type."""
        return f"[REDACTED_{secret_type.upper()}]"
    
    @staticmethod
    def _looks_like_password(value: str) -> bool:
        """Heuristic to determine if a value looks like a password.
        
        Passwords typically contain mixed character classes:
        - Letters + digits
        - Letters + special chars
        - Digits + special chars
        
        This reduces false positives for phrases like "user / preferences".
        
        Args:
            value: The value to check.
            
        Returns:
            True if the value looks like a password.
        """
        has_letter = any(c.isalpha() for c in value)
        has_digit = any(c.isdigit() for c in value)
        has_special = any(not c.isalnum() for c in value)
        return sum([has_letter, has_digit, has_special]) >= 2
    
    def should_block(self, content: str, threshold: int = 5) -> Tuple[bool, str]:
        """Check if content should be blocked due to too many secrets.
        
        Args:
            content: Content to check.
            threshold: Maximum number of secrets allowed.
            
        Returns:
            Tuple of (should_block, reason).
        """
        detections = self.detect(content)
        
        if len(detections) >= threshold:
            return True, f"Too many secrets detected ({len(detections)}), possible data leak"
        
        return False, ""
    
    def get_security_report(self, content: str) -> Dict[str, any]:
        """Get a detailed security report for the content.
        
        Args:
            content: Content to analyze.
            
        Returns:
            Dict with security analysis results.
        """
        detections = self.detect(content)
        
        # Group by type
        by_type: Dict[str, int] = {}
        for d in detections:
            by_type[d.type] = by_type.get(d.type, 0) + 1
        
        return {
            "total_detections": len(detections),
            "by_type": by_type,
            "has_secrets": len(detections) > 0,
            "should_block": len(detections) >= 3,
            "recommendation": "block" if len(detections) >= 3 else "review" if len(detections) > 0 else "safe",
        }


# Module-level singleton for convenience
_default_redactor: Optional[SecretsRedactor] = None


def get_default_redactor() -> SecretsRedactor:
    """Get the default SecretsRedactor instance."""
    global _default_redactor
    if _default_redactor is None:
        _default_redactor = SecretsRedactor()
    return _default_redactor


def redact_secrets(content: str) -> RedactionResult:
    """Convenience function to redact secrets using default redactor."""
    return get_default_redactor().redact(content)


def detect_secrets(content: str) -> List[DetectionResult]:
    """Convenience function to detect secrets using default redactor."""
    return get_default_redactor().detect(content)