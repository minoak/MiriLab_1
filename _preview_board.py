# -*- coding: utf-8 -*-
"""Standalone policy board runner.

Run:
    streamlit run _preview_board.py

The board source now lives under standalone_board/ to avoid conflicts with
app.py, ui/tab_board.py, and board_engine.py while other teammates work there.
"""

from standalone_board.app import main


if __name__ == "__main__":
    main()
