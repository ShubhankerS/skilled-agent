from typing import List, Dict, Any
import litellm
from qdrant_client import QdrantClient
from qdrant_client.http.models import PointStruct, VectorParams, Distance
from app.core.config import settings

class RAGPipeline:
    """
    Handles document embedding, indexing, and retrieval from Qdrant.
    """
    def __init__(self, collection_name: str = "agent_knowledge"):
        self.client = QdrantClient(url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY)
        self.collection_name = collection_name
        self.vector_size = 1536 # Default for text-embedding-3-small or Gemini equivalents
        self._ensure_collection()

    def _ensure_collection(self):
        """Creates the collection if it doesn't exist."""
        try:
            self.client.get_collection(self.collection_name)
        except Exception:
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(size=self.vector_size, distance=Distance.COSINE),
            )

    async def embed_and_store(self, texts: List[str], metadata: List[Dict[str, Any]]):
        """Converts text to vectors and stores them in Qdrant."""
        responses = litellm.embedding(
            model="text-embedding-3-small", # Or Gemini embedding model
            input=texts
        )
        embeddings = [r['embedding'] for r in responses['data']]
        
        points = [
            PointStruct(id=i, vector=emb, payload=meta)
            for i, (emb, meta) in enumerate(zip(embeddings, metadata))
        ]
        self.client.upsert(collection_name=self.collection_name, points=points)

    async def query(self, query_text: str, limit: int = 3) -> List[Dict[str, Any]]:
        """Searches for relevant context based on user query."""
        response = litellm.embedding(model="text-embedding-3-small", input=[query_text])
        query_vector = response['data'][0]['embedding']

        results = self.client.search(
            collection_name=self.collection_name,
            query_vector=query_vector,
            limit=limit
        )
        return [hit.payload for hit in results]
