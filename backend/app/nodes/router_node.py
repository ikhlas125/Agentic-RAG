from app.core.graph_state import State
from langsmith import traceable
from app.llm.provider_registry import get_model
import json
from app.core.config import MANIFEST_PATH, settings
from app.helper.helper import load_json

@traceable
def Router_Agent(state: State):

    data_manifest = load_json(MANIFEST_PATH)

    router = get_model(settings.ROUTER_MODEL)

    

