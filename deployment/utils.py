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
    level = logging.DEBUG if verbose else logging.ERROR
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(filename)s::%(funcName)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        force=True,
    )
    if not verbose:
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)

def print_welcome_message() -> None:
    '''
    print the welcome message at the program entry for users
    '''
    print("=" * 60)
    print("       Welcome to Advising Bot")
    print("=" * 60)
    print()
    print("I'm here to help you with questions about Stony Brook")
    print("University, including courses, requirements, programs,")
    print("policies, and more.")
    print()
    print("  - Type your question and press Enter to get a response.")
    print("  - Type 'e', 'exit', or 'quit' to leave the program.")
    print()
    print("=" * 60)
    print()


def print_goodbye_message() -> None:
    '''
    print the goodbye message when the user exits the program
    '''
    print()
    print("=" * 60)
    print("          Thank you for using Advising Bot!")
    print("=" * 60)
    print()
    print("We hope your questions were answered. Good luck with")
    print("your studies at Stony Brook University!")
    print()
    print("=" * 60)
    print()


if __name__ == "__main__":
    print_goodbye_message()
