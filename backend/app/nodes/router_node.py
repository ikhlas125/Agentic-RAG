from backend.app.core.graph_state import State
from langsmith import traceable
from backend.app.llm.provider_registry import get_model
import json
from  backend.app.core.config import MANIFEST_PATH, settings
from backend.app.helper.helper import load_json

@traceable
def Router_Agent(state: State):

    data_manifest = load_json(MANIFEST_PATH)

    router = get_model(settings.ROUTER_MODEL)

    

