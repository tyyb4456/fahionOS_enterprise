import logging
from langchain_azure_ai.chat_models import AzureAIOpenAIApiChatModel
from azure.identity import DefaultAzureCredential
from langchain_mistralai import ChatMistralAI

from dotenv import load_dotenv
load_dotenv()

logger = logging.getLogger(__name__)

logger.info("Initializing Azure AI / Mistral models")

kimi = AzureAIOpenAIApiChatModel(
    project_endpoint="https://tyb-pro-resource.services.ai.azure.com/api/projects/tyb-pro",
    model="Kimi-K2.6",
    credential=DefaultAzureCredential(),
)

mistral = ChatMistralAI(
    model="mistral-medium-3-5",
    temperature=0,
    model_kwargs={"reasoning_effort": "high"},
)