'''
Lazy registry of compiled graphs, will instantiate with different model selections 
Memory is saved with postgres checkpointer, changing models and advising_graph will not interfere memory 
'''
import logging
import threading

from backend.agent_graph.langgraph import build_advising_graph
from backend.clients.llm.factory import create_model
from backend.config import SELECTABLE_MODELS

logger = logging.getLogger(__name__)


class UnknownModelError(ValueError):
    '''
    the client asked for a model that is not in SELECTABLE_MODELS.
    app.py maps this to a 400 - this module knows nothing about HTTP
    '''
    def __init__(self, model_id: str):
        self.model_id = model_id
        super().__init__(f"Unknown model {model_id!r}")


class GraphRegistry:
    '''
    builds a model and compiles its graph on first use, then caches it for the
    rest of the process. Every graph it hands out shares the one checkpointer
    passed in here, which is what keeps memory common across models.
    '''

    def __init__(self, checkpointer, max_messages: int = 8):
        self._checkpointer = checkpointer
        self._max_messages = max_messages
        self._graphs = {}
        self._lock = threading.Lock()

    def get(self, model_id: str | None):
        '''
        return the compiled graph for model_id, building it if this is the first
        request to select it. None falls back to DEFAULT_MODEL
        '''
        provider = SELECTABLE_MODELS.get(model_id, None) 
        if provider is None:
            raise UnknownModelError(model_id)

        # fast path: already built, so no lock on the common case
        graph = self._graphs.get(model_id)
        if graph is not None:
            return graph

        # /chat is a sync route, so it runs in the threadpool and two first
        # requests for the same model can land together. Build once, under the
        # lock, and let the second caller pick the cached graph up
        with self._lock:
            graph = self._graphs.get(model_id)
            if graph is None:
                logger.info("Compiling graph for model %s (provider %s)", model_id, provider)
                model = create_model(provider=provider)
                graph = build_advising_graph(
                    model=model, max_messages=self._max_messages
                ).compile(checkpointer=self._checkpointer)
                # cache these advising graphs 
                self._graphs[model_id] = graph
        return graph
