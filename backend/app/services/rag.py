import uuid
import logging
from typing import List, Dict, Any
import litellm
from qdrant_client import QdrantClient
from qdrant_client.http.models import PointStruct, VectorParams, Distance
from app.core.config import settings

logger = logging.getLogger(__name__)

class RAGPipeline:
    """
    Handles document embedding, indexing, and retrieval from Qdrant.
    """
    # Embedding model used for both indexing and querying.
    # Must be the same model for both — mixing models produces incompatible vectors.
    EMBEDDING_MODEL = "text-embedding-3-small"

    def __init__(self, collection_name: str = "agent_knowledge"):
        self.client = QdrantClient(url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY)
        self.collection_name = collection_name
        self.vector_size = 1536
        self._ensure_collection()

    def _ensure_collection(self):
        """Creates the Qdrant collection if it doesn't already exist."""
        try:
            self.client.get_collection(self.collection_name)
        except Exception:
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(size=self.vector_size, distance=Distance.COSINE),
            )

    async def embed_and_store(self, texts: List[str], metadata: List[Dict[str, Any]]):
        """Converts texts to vectors and stores them in Qdrant with UUID point IDs.

        Why UUIDs instead of enumerate()?
        enumerate() assigns IDs 0, 1, 2... which collide across uploads.
        Qdrant upserts silently overwrite existing points with the same ID,
        meaning document 2 would destroy document 1's chunks.
        UUIDs are globally unique — no collision across any number of uploads.
        """
        responses = litellm.embedding(model=self.EMBEDDING_MODEL, input=texts)
        embeddings = [r['embedding'] for r in responses['data']]

        points = [
            PointStruct(
                id=str(uuid.uuid4()),  # unique per chunk, per upload, forever
                vector=emb,
                payload=meta,
            )
            for emb, meta in zip(embeddings, metadata)
        ]
        self.client.upsert(collection_name=self.collection_name, points=points)
        logger.info(f"Stored {len(points)} chunks in Qdrant collection '{self.collection_name}'")

    async def query(self, query_text: str, limit: int = 3) -> List[Dict[str, Any]]:
        """Searches for the most semantically relevant document chunks."""
        response = litellm.embedding(model=self.EMBEDDING_MODEL, input=[query_text])
        query_vector = response['data'][0]['embedding']

        results = self.client.search(
            collection_name=self.collection_name,
            query_vector=query_vector,
            limit=limit,
        )
        return [hit.payload for hit in results]
