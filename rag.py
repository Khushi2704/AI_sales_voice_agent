"""
rag.py - Retrieval for RAG (Retrieval-Augmented Generation).

Idea: before the LLM answers a factual question, we FIND the relevant part of
our knowledge base (kb.md) and give it to the LLM. The LLM then answers from
real company facts instead of guessing (this reduces "hallucination").

How we find the relevant part: TF-IDF.
  - Split kb.md into chunks (one per "## " section).
  - Turn every chunk into a vector of word weights. Words that are frequent in
    one chunk but rare across all chunks get a high weight ("subsidy", "EMI").
  - Turn the question into the same kind of vector.
  - Cosine similarity = how much two vectors point the same way (0..1).
  - Return the top-k most similar chunks.

Production upgrade: replace TF-IDF with neural embeddings (e.g. OpenAI
text-embedding-3-small) stored in a vector DB (pgvector / Pinecone / Qdrant).
Only this file would change.
"""
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

KB_FILE = "kb.md"
MIN_SCORE = 0.05   # below this, we treat the result as "not found"


def load_chunks(path=KB_FILE):
    """Split the markdown file into sections. Each chunk = heading + its text."""
    text = open(path, encoding="utf-8").read()
    chunks = []
    for part in text.split("\n## ")[1:]:           # [0] is the title + comment
        title, _, body = part.partition("\n")
        chunks.append({"title": title.strip(), "text": body.strip()})
    return chunks


# Build the index once when the server starts.
CHUNKS = load_chunks()
# token_pattern keeps English words AND whole Hindi (Devanagari) words.
VECTORIZER = TfidfVectorizer(lowercase=True, token_pattern=r"(?u)[\wऀ-ॿ]+",
                             stop_words="english")
MATRIX = VECTORIZER.fit_transform([c["title"] + " " + c["text"] for c in CHUNKS])


def search(query, k=2):
    """Return the k best matching chunks as a list of {title, text, score}."""
    if not query or not query.strip():
        return []
    scores = cosine_similarity(VECTORIZER.transform([query]), MATRIX)[0]
    best = scores.argsort()[::-1][:k]                 # indexes of highest scores
    return [{"title": CHUNKS[i]["title"], "text": CHUNKS[i]["text"], "score": round(float(scores[i]), 3)}
            for i in best if scores[i] >= MIN_SCORE]


if __name__ == "__main__":     # quick manual test:  python rag.py
    for q in ["how much is the subsidy?", "EMI options", "सब्सिडी कितनी है", "warranty on panels"]:
        print(q, "->", [(r["title"], r["score"]) for r in search(q)])
