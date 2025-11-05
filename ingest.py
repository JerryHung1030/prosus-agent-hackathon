# FILE: ./ingest.py

import os
import shutil
import sys

from langchain_chroma import Chroma
from langchain_community.document_loaders import (
    CSVLoader,
    DirectoryLoader,
    JSONLoader,
    TextLoader,
)
from langchain_openai import OpenAIEmbeddings
from langchain_text_splitters import CharacterTextSplitter

import src.config as _config

_ = _config.OPENAI_API_KEY

# Define constants
DATA_PATH = "data/"
DB_PATH = "db/"

# Map file extensions to their respective loaders
LOADER_MAPPING = {
    ".md": (TextLoader, {"encoding": "utf-8"}),
    ".txt": (TextLoader, {"encoding": "utf-8"}),
    ".csv": (CSVLoader, {"encoding": "utf-8"}),
    ".json": (
        JSONLoader,
        {"jq_schema": ".[].text", "text_content": False},
    ),
}


def build_vector_store():
    """
    Builds a vector store from all supported files in the DATA_PATH.
    This is now modular to handle hackathon data.
    """

    # 1. Clean up old database
    if os.path.exists(DB_PATH):
        print(f"Removing existing database at {DB_PATH}")
        shutil.rmtree(DB_PATH)

    # 2. Load all documents from the data directory
    print(f"Loading documents from {DATA_PATH}...")
    all_documents = []
    for ext, (Loader, kwargs) in LOADER_MAPPING.items():
        # Use DirectoryLoader to find all files with a specific extension
        loader = DirectoryLoader(
            DATA_PATH,
            glob=f"**/*{ext}",
            loader_cls=Loader,
            loader_kwargs=kwargs,
            show_progress=True,
            use_multithreading=True,
        )
        try:
            docs = loader.load()
            if docs:
                print(f"Loaded {len(docs)} documents from {ext} files.")
                all_documents.extend(docs)
        except Exception as e:
            print(f"Warning: Failed to load {ext} files: {e}")

    if not all_documents:
        print("Error: No documents loaded. Did you add data files to the 'data/' folder?")
        sys.exit(1)

    # 3. Split documents
    text_splitter = CharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
    docs = text_splitter.split_documents(all_documents)
    print(f"Total documents loaded: {len(all_documents)}, split into {len(docs)} chunks.")

    # 4. Create and persist vector store
    embeddings = OpenAIEmbeddings()
    print(f"Creating and persisting vector store at {DB_PATH}...")
    Chroma.from_documents(docs, embeddings, persist_directory=DB_PATH)
    print("Vector store created successfully.")


if __name__ == "__main__":
    if not os.path.exists(DATA_PATH):
        print(f"Error: Data directory not found at {DATA_PATH}")
    else:
        build_vector_store()
