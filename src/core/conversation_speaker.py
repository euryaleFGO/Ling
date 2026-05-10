# -*- coding: utf-8 -*-
"""
Speaker recognition integration for AsyncConversationManager.

Provides the SpeakerRecognitionMixin that hooks into the conversation loop
to identify speakers and handle passive registration of unknown speakers.
"""

import re
import logging
from typing import TYPE_CHECKING

import numpy as np

from core.log import log

if TYPE_CHECKING:
    from core.conversation_manager_async import AsyncConversationManager

logger = logging.getLogger(__name__)


class SpeakerRecognitionMixin:
    """Speaker identification and passive registration for conversation loop."""

    # -- Name extraction ---------------------------------------------------

    @staticmethod
    def _is_unknown_speaker(speaker_id: str) -> bool:
        """Check if speaker_id represents an unknown/unregistered speaker."""
        if not speaker_id:
            return True
        return speaker_id == "unknown" or speaker_id.startswith("unknown_")

    @staticmethod
    def _extract_name_from_response(text: str) -> tuple:
        """Extract speaker name from an introduction response.

        Matches patterns like "我是xxx", "我叫xxx", "我名字是xxx".
        Handles ASR quirks like extra words before "我是".
        Returns (name, remaining_text).
        """
        if not text or not text.strip():
            return "", ""

        text = text.strip()

        # Patterns: try "我是/我叫" anywhere in text (ASR may add words before)
        patterns = [
            # "我是xxx" with trailing punctuation
            r'我(?:名字)?[是叫]\s*(.{1,6}?)(?:啊|呢|呀|哦|的|嘛)?[，,。.\s]',
            # "我是xxx" at end of string
            r'我(?:名字)?[是叫]\s*(.{1,6}?)(?:啊|呢|呀|哦|的|嘛)?$',
        ]

        for pattern in patterns:
            m = re.search(pattern, text)
            if m:
                name = m.group(1).strip()
                rest = text[m.end():].strip().lstrip('，,。. ')
                # Filter out garbage names
                if name and len(name) >= 1 and not name.startswith('是'):
                    return name, rest

        # Fallback: only if text is short AND looks like a Chinese name
        # (no ASR noise words, all Chinese characters)
        clean = re.sub(r'[，,。.！!？?\s]', '', text)
        _noise_words = {'是', '的', '了', '吗', '呢', '啊', '呀', '哦', '嘛', '吧', '好', '不', '我', '你', '他', '她', '这', '那', '得', '到', '在'}
        if 1 <= len(clean) <= 4 and all('\u4e00' <= c <= '\u9fff' for c in clean):
            # Reject if any single char is a common noise word
            if len(clean) <= 2 and any(c in _noise_words for c in clean):
                return "", text
            return clean, ""

        return "", text

    # -- Speaker identification --------------------------------------------

    def _identify_speaker_from_embedding(
        self: "AsyncConversationManager", embedding: np.ndarray
    ) -> str:
        """Match an embedding against the voiceprint database.

        Returns speaker_id ('unknown' if no match).
        """
        if not self._speaker_manager:
            return "unknown"

        try:
            speaker_id, score = self._speaker_manager.identify(embedding)
            log.debug(f"[speaker] identified: {speaker_id} (score={score:.3f})")
            return speaker_id
        except Exception as e:
            log.warn(f"[speaker] identification failed: {e}")
            return "unknown"

    # -- Passive registration handling -------------------------------------

    def _handle_passive_registration(
        self: "AsyncConversationManager",
        user_text: str,
        speaker_id: str,
        embedding: np.ndarray,
    ) -> tuple:
        """Handle speaker identification in the conversation loop.

        Returns:
            (effective_text, should_continue, prompt_to_speak)
            prompt_to_speak is non-empty when the caller should speak it.
        """
        if not self._speaker_manager:
            return user_text, True, ""

        speaker_recog_cfg = getattr(self.config, 'speaker_recognition', None)
        if not speaker_recog_cfg or not getattr(speaker_recog_cfg, 'passive_registration', False):
            return user_text, True, ""

        # Not in registration mode and speaker is known
        if not self._pending_registration and not self._is_unknown_speaker(speaker_id):
            return user_text, True, ""

        # Unknown speaker, start registration
        if not self._pending_registration and speaker_id == "unknown":
            self._pending_registration = True
            self._last_unknown_embedding = embedding.copy()
            self._pending_user_text = user_text  # 保存原话，注册后补发
            prompt = getattr(speaker_recog_cfg, 'passive_prompt', '你好，我好像不认识你，请问你是谁呀？')
            log.info(f"[speaker] unknown speaker, asking: {prompt}")
            return "", False, prompt

        # In registration mode: try to extract name
        if self._pending_registration:
            self._pending_registration = False
            name, rest = self._extract_name_from_response(user_text)

            if name and self._last_unknown_embedding is not None:
                success = self._speaker_manager.register_embedding(
                    name, self._last_unknown_embedding
                )
                if success:
                    log.info(f"[speaker] registered new speaker: '{name}'")
                    # Notify GUI if available
                    if hasattr(self, '_on_speaker_change_callback') and self._on_speaker_change_callback:
                        try:
                            self._on_speaker_change_callback(name, 1.0)
                        except Exception:
                            pass
                else:
                    log.warn(f"[speaker] failed to register: '{name}'")
            else:
                log.debug("[speaker] no name extracted, skipping registration")

            self._last_unknown_embedding = None
            # 补发被丢弃的原话
            pending_text = getattr(self, '_pending_user_text', '') or ''
            self._pending_user_text = ''
            if rest:
                return rest, True, ""
            if pending_text:
                return pending_text, True, ""
            return "", False, ""

        return user_text, True, ""
