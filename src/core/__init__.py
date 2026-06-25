"""Core extraction engine for the DJI frame extractor.

Split out of the former single-file application. UI-agnostic: the pipeline
driver (``process_all``) takes ``log`` / ``set_progress`` callbacks and a
cancel ``threading.Event``, so it can be driven from the PySide6 GUI, the
CLI, or tests without any GUI dependency.
"""
