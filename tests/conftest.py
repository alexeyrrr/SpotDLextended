# -*- coding: utf-8 -*-
"""Pytest root config: ensures the tests directory is importable as a package."""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
