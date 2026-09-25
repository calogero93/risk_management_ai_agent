import os

from chromadb import Client
from sentence_transformers import SentenceTransformer

class Embedder():
  """
  La classe che si occupa di generare gli embedding, sia per chunks che per query, operando in batch con default 32
  """
  def __init__(self, batch: int = 32):
    self.embedder = SentenceTransformer(os.environ.get("EMBEDDING_MODEL"))
    self.vector_size = self.embedder.get_sentence_embedding_dimension()
    self.batch = batch

  def embed_chunks_dense(self, chunks: list[str], prefix: str = "passage"):
    """
    Unico metodo che grazie al prefisso permette di embeddare i vari chunks o le query in maniera corretta per l'embedding model scelto
    in modo da aumentarne la qualità
    Args:
      chunks: list[str] = la lista dei soli chunks di testo senza metadata
      prefix: str = default 'passage', si può scegliere tra 'passage' e 'query' per embeddare in maniera più coerente il tipo di dato, se chunk o query
    Output:
      lista di tutti gli embeddings sia chunk o eventualmente query
    """
    if not chunks:
      return []

    # l'uso del prefix in intfloat/multilingual-e5-small migliora la qualità dell'embedding perchè il modello è stato addestrato in questo modo
    # con query e passage per cogliere l'asimmetria tra domanda e risposta soprattutto nei casi come il nostro di documenti regolatori
    if prefix not in ("query", "passage"):
        raise ValueError(f"prefix deve essere 'query' o 'passage', ricevuto: {prefix!r}")

    return self.embedder.encode(
      [f"{prefix}: {t}" for t in chunks],
      batch_size=self.batch
    ).tolist()

from langchain_core.documents import Document as LCDocument
from langchain_community.retrievers import BM25Retriever

class ChromaDB():
  """
  La classe che si occupa di indexing e retrieval degli embeddings sia dense che sparse il la ricerca ibrida
  """
  def __init__(self, batch: int = 32):
    self.embedder = Embedder(batch=batch)
    self.client = Client()
    self.bm25_retriever = None
    self.collection = None

  def index(self, chunks: list, collection_name: str = "finsecure"):
    """
    La funzione di indexing se salva si gli embeddings su Chroma che i vettori sparsi nel retriever BM25
    Args:
      chunks: list[dict] = lista completa dei chunks con metadata
      collection_name: str = nome della collezione Chroma
    Output:
      nessun output
    """
    self.collection = self.client.get_or_create_collection(
        name=collection_name,
        metadata={"hnsw:space": "cosine"}
    )

    chunks_payload = [chunk["payload"] for chunk in chunks]
    metadatas = [{k: v for k, v in chunk.items() if k != "payload"} for chunk in chunks]
    dense_vecs = self.embedder.embed_chunks_dense(chunks_payload)
    ids = [f"{chunk['file_name']}_{chunk['chunk_index']}" for chunk in chunks]

    self.collection.upsert(
        documents=chunks_payload,
        embeddings=dense_vecs,
        metadatas=metadatas,
        ids=ids
    )
    lc_documents = [
      LCDocument(
          page_content=chunk["payload"],
          metadata={k: v for k, v in chunk.items() if k != "payload"}
      )
      for chunk in chunks
    ]


    self.bm25_retriever = BM25Retriever.from_documents(lc_documents)
    self.bm25_retriever.k = 4

  def hybrid_search(self, query: str, top_k: int = 4, alpha: float = 0.5, where: dict | None = None) -> list[LCDocument]:
    """
    Funzione che si occupa della ricerca ibrida sia densa che sparsa, fa la fusion dei risultate con RRF e restituisce i migliori top_k chunks
    Args:
      query: str = La richiesta dell'utente
      top_k: int = il numero dei migliori risultati da restituire
      alpha: float = il coefficiente di peso, permette di stabilire se dare più o meno peso ad un metodo di ricerca piuttosto che ad un altro
                      di default 0.5, quindi peso uguale sia per ricerca sparsa che densa
      where: dict = sono gli eventuali filtri sui metadata che si possono inserire per migliorare la ricerca
    """

    query_dense_vector = self.embedder.embed_chunks_dense([query], prefix="query")[0]
    dense_results = self.collection.query(
            query_embeddings=[query_dense_vector],
            n_results=top_k*4,
            where=where
        )

    dense_docs = []
    if dense_results["documents"] and dense_results["documents"][0]:
        for doc_text, meta in zip(dense_results["documents"][0], dense_results["metadatas"][0]):
            dense_docs.append(LCDocument(page_content=doc_text, metadata=meta))


    self.bm25_retriever.k = top_k*4
    sparse_docs = self.bm25_retriever.invoke(query)
    if where:
      sparse_docs = [d for d in sparse_docs if all(d.metadata.get(k) == v for k, v in where.items())]


    rrf_scores = {}
    doc_map = {}
    c = 60

    def get_chunk_id(doc: LCDocument) -> str:
      file_name = doc.metadata.get("file_name", "unknown")
      chunk_idx = doc.metadata.get("chunk_index", "0")
      return f"{file_name}__chunk_{chunk_idx}"

    for rank, doc in enumerate(dense_docs):
      key = get_chunk_id(doc)
      doc_map[key] = doc
      rrf_scores[key] = rrf_scores.get(key, 0.0) + (1 - alpha) * (1 / (c + rank + 1))

    for rank, doc in enumerate(sparse_docs):
      chunk_id = get_chunk_id(doc)
      doc_map.setdefault(chunk_id, doc)
      rrf_scores[chunk_id] = rrf_scores.get(chunk_id, 0.0) + alpha * (1 / (c + rank + 1))

    sorted_ids = sorted(rrf_scores.keys(), key=lambda k: rrf_scores[k], reverse=True)

    hybrid_results = [doc_map[chunk_id] for chunk_id in sorted_ids[:top_k]]

    return hybrid_results
