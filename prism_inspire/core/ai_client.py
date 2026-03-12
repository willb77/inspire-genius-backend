import os
from openai import AsyncOpenAI, OpenAI, api_key
from google.genai import client as GenAIClient
from prism_inspire.core.config import settings
from langchain_openai import OpenAIEmbeddings
from prism_inspire.core.log_config import logger
from langchain_google_genai import GoogleGenerativeAIEmbeddings

openai = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
openai_client = OpenAI(api_key=settings.OPENAI_API_KEY)
genai_client = GenAIClient.Client(
    api_key=settings.GEMINI_API_KEY,
)

embeddings_client = OpenAIEmbeddings(
    dimensions=512,
    openai_api_key=settings.OPENAI_API_KEY,
    model="text-embedding-3-small"
)

embeddings_client_google = GoogleGenerativeAIEmbeddings(
    google_api_key=settings.GEMINI_API_KEY,
    model="models/gemini-embedding-001",
)


logger.info("AI Clients have been initialized successfully.")