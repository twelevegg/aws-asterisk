"""
Korean Morpheme Analyzer for Turn Completeness Detection.

Analyzes Korean sentence endings to determine if a turn is complete.
"""

import re
from typing import List, Tuple, Optional

# Korean morpheme analyzer
try:
    from kiwipiepy import Kiwi
    KIWI_AVAILABLE = True
except ImportError:
    KIWI_AVAILABLE = False


class KoreanMorphemeAnalyzer:
    """
    Korean morpheme analyzer for turn completeness detection.

    Uses pattern matching for common endings and Kiwi for detailed analysis.
    """

    # Final endings (EF) - indicate complete sentences
    ENDING_PATTERNS: List[str] = [
        # Formal declarative
        r'습니다$', r'입니다$', r'합니다$', r'됩니다$',
        # Informal declarative
        r'예요$', r'에요$', r'이에요$', r'네요$', r'군요$',
        r'거든요$', r'잖아요$', r'는데요$',
        # Questions
        r'나요\?*$', r'까요\?*$', r'세요\?*$', r'어요\?*$',
        r'습니까\?*$', r'입니까\?*$',
        # Requests/Commands
        r'하세요$', r'주세요$', r'해주세요$', r'드릴게요$',
        # Short responses
        r'^네$', r'^예$', r'^아니요$', r'^아니오$',
        r'^알겠습니다$', r'^감사합니다$', r'^네네$', r'^아$',
        # Past tense endings
        r'었어요$', r'았어요$', r'였어요$',
        r'었습니다$', r'았습니다$', r'였습니다$',
    ]

    # Connecting endings (EC) - indicate incomplete sentences
    CONTINUING_PATTERNS: List[str] = [
        # Conjunctive
        r'는데$', r'인데$', r'은데$',
        r'고$', r'고요$',
        r'며$', r'서$', r'니까$', r'면$',
        r'지만$', r'라서$', r'해서$',
        # Hesitation/Filler
        r'어\.\.\.$', r'음\.\.\.$', r'그\.\.\.$',
        # Incomplete
        r'근데$', r'그래서$', r'그런데$',
    ]

    def __init__(self, use_kiwi: bool = True):
        """
        Initialize morpheme analyzer.

        Args:
            use_kiwi: Use Kiwi for detailed analysis if available
        """
        self._kiwi = Kiwi() if (use_kiwi and KIWI_AVAILABLE) else None
        self._ending_re = [re.compile(p) for p in self.ENDING_PATTERNS]
        self._continuing_re = [re.compile(p) for p in self.CONTINUING_PATTERNS]

    @property
    def kiwi_available(self) -> bool:
        """Check if Kiwi is available."""
        return self._kiwi is not None

    def analyze(self, text: str) -> float:
        """
        Analyze text and return completion score.

        Args:
            text: Korean text to analyze

        Returns:
            Completion score (0.0 ~ 1.0)
            - > 0.8: High confidence complete
            - 0.5~0.8: Possibly complete
            - < 0.5: Likely incomplete
        """
        if not text or not text.strip():
            return 0.5

        text = text.strip()

        # Check ending patterns first (fastest)
        for pattern in self._ending_re:
            if pattern.search(text):
                return 0.95

        # Check continuing patterns
        for pattern in self._continuing_re:
            if pattern.search(text):
                return 0.2

        # Use Kiwi for detailed analysis
        if self._kiwi:
            try:
                kiwi_score = self._analyze_with_kiwi(text)
                if kiwi_score is not None:
                    return kiwi_score
            except Exception:
                pass

        # Default neutral score
        return 0.5

    def _analyze_with_kiwi(self, text: str) -> Optional[float]:
        """
        Analyze using Kiwi morpheme analyzer.

        Args:
            text: Text to analyze

        Returns:
            Completion score or None if analysis fails
        """
        if self._kiwi is None:
            return None
        result = self._kiwi.analyze(text)
        if not result or not result[0][0]:
            return None

        tokens = result[0][0]
        if not tokens:
            return None

        last_token = tokens[-1]
        tag = last_token.tag

        # EF (Final Ending) = complete
        if tag == 'EF':
            return 0.85

        # EC (Connecting Ending) = incomplete
        if tag == 'EC':
            return 0.3

        # SF (Sentence-Final Punctuation)
        if tag == 'SF':
            # Check second-to-last if punctuation
            if len(tokens) >= 2:
                prev_tag = tokens[-2].tag
                if prev_tag == 'EF':
                    return 0.9
                if prev_tag == 'EC':
                    return 0.35

        # NNG, NNP (Nouns) at end - often incomplete
        if tag in ('NNG', 'NNP', 'NP'):
            return 0.4

        # VV, VA (Verbs, Adjectives) without ending - incomplete
        if tag in ('VV', 'VA', 'VX'):
            return 0.3

        return 0.5

    def get_morphemes(self, text: str) -> List[Tuple[str, str]]:
        """
        Get list of morphemes and their tags.

        Args:
            text: Text to analyze

        Returns:
            List of (morpheme, tag) tuples
        """
        if not self._kiwi:
            return []

        try:
            result = self._kiwi.analyze(text)
            if result and result[0][0]:
                return [(t.form, t.tag) for t in result[0][0]]
        except Exception:
            pass

        return []
