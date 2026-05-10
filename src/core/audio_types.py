# -*- coding: utf-8 -*-
"""Shared audio type definitions."""

from collections import namedtuple

StreamingChunk = namedtuple('StreamingChunk', ['audio', 'segment_idx', 'total_segments', 'visemes'])
