'''
utility functions supporting deployment
'''
import logging


def setup_logging(verbose: bool = False) -> None:
    '''
    Configure the root logger with timestamp, filename, and function name.
    All modules that use logging.getLogger(__name__) inherit this config.

    Args:
        verbose: if True, sets level to DEBUG; otherwise WARNING
    '''
    level = logging.INFO if verbose else logging.ERROR
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(filename)s::%(funcName)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        force=True,
    )

    # silence the supabase logger.info() logs  
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    # the Gemini SDK logs "AFC is enabled..." at INFO on every single call
    logging.getLogger("google_genai").setLevel(logging.WARNING)