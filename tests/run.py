#!/usr/bin/env python3
"""Roda TODA a suíte. Um comando, um veredito.

    python3 tests/run.py

Sai com código 1 se qualquer teste falhar — é o que permite usar isto antes de
compilar o executável e antes de entregar qualquer versão.
"""

import os
import sys
import unittest

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)


def main():
    suite = unittest.defaultTestLoader.discover(AQUI, pattern="test_*.py")
    resultado = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if resultado.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
